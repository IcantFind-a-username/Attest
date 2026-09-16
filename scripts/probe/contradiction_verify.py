"""P-05b: re-check one recorded contradiction by replaying only the tests that produced it.

An audit that cannot be re-checked is an opinion. For each contradiction the audit recorded --
a function, the return type its own signature declares, the types it returned, and the test
nodes that called it -- this replays **those nodes only**, with the monitor narrowed to that one
site, and reports whether the same contradiction appears again.

    .venv/bin/python scripts/probe/contradiction_verify.py --audit audit.json --out verified.json

The record carries the library's revision, the site, the declared type, the observed types and a
digest over them, so a reader can run the same command and compare. No model, no spend, no
product change; the corpus is only read and returned to the revision it was on.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "probe"))

from contradiction_audit import CORPUS, PLUGIN  # noqa: E402

TIMEOUT_S = 900.0


def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def replay(
    venv: Path, repo: Path, package: str, where: str, nodes: list[str],
    plugin_dir: Path, out: Path,
) -> dict[str, Any]:
    environment = {
        "PATH": f"{venv / 'bin'}:/usr/bin:/bin", "HOME": str(plugin_dir),
        "PYTHONPATH": str(plugin_dir), "ATTEST_PACKAGE": package,
        "ATTEST_AUDIT_OUT": str(out), "ATTEST_ONLY": where,
    }
    if out.exists():
        out.unlink()
    try:
        completed = subprocess.run(
            [str(venv / "bin" / "python"), "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", "-o", "addopts=", "-W", "ignore",
             "-p", "attest_audit", *nodes],
            cwd=repo, capture_output=True, text=True, timeout=TIMEOUT_S, env=environment,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout"}
    record: dict[str, Any] = {"outcome": "ran", "exit": completed.returncode}
    if out.is_file():
        record |= json.loads(out.read_text(encoding="utf-8"))
    else:
        record["outcome"] = "no record"
        record["tail"] = ((completed.stdout or "") + (completed.stderr or ""))[-300:]
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--library", default="")
    args = parser.parse_args(argv)
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))

    findings: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="contradiction-verify-") as tmp:
        plugin_dir = Path(tmp)
        (plugin_dir / "attest_audit.py").write_text(PLUGIN, encoding="utf-8")
        for row in audit["rows"]:
            if args.library and row.get("library") != args.library:
                continue
            for contradiction in row.get("contradictions", []):
                nodes = contradiction.get("nodes") or []
                if not nodes:
                    findings.append({
                        "library": row["library"], "where": contradiction["where"],
                        "reproduced": None,
                        "reason": "the audit recorded no test node for this site",
                    })
                    continue
                repo = CORPUS / row["library"] / "repo"
                venv = CORPUS / row["library"] / ".venv"
                at = subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=True,
                ).stdout.strip()
                replayed = replay(
                    venv, repo, row["package"], contradiction["where"], nodes,
                    plugin_dir, plugin_dir / "replay.json",
                )
                observed = next(
                    (v for v in replayed.get("violations", [])
                     if v["where"] == contradiction["where"]),
                    None,
                )
                body = {
                    "library": row["library"], "revision": row["revision"],
                    "where": contradiction["where"], "declared": contradiction["expected"],
                    "observed": sorted((observed or {}).get("got", {})),
                    "nodes": nodes,
                }
                findings.append({
                    **body,
                    "recorded_types": sorted(contradiction["got"]),
                    # the record keeps at most five nodes, so a replay can reproduce the
                    # contradiction without reproducing every type the audit saw
                    "reproduced": (
                        "no" if not observed
                        else "exactly" if sorted(observed.get("got", {}))
                        == sorted(contradiction["got"])
                        else "in part"
                    ),
                    "replay_exit": replayed.get("exit"),
                    "replayed_at": at,
                    "same_revision": at == row["revision"],
                    "digest": digest(body),
                    "command": (
                        f"cd {repo} && ATTEST_ONLY='{contradiction['where']}' "
                        f"ATTEST_PACKAGE={row['package']} ../.venv/bin/python -m pytest -q "
                        f"-p attest_audit {' '.join(nodes)}"
                    ),
                })
                print(json.dumps({
                    "where": contradiction["where"],
                    "reproduced": findings[-1]["reproduced"],
                    "observed": findings[-1]["observed"],
                }), flush=True)

    summary = {
        "probe": "P-05b contradiction verification",
        "audit_digest": digest({"rows": [r.get("library") for r in audit["rows"]],
                                "contradictions": audit.get("contradictions")}),
        "findings": len(findings),
        "reproduced_exactly": sum(1 for f in findings if f.get("reproduced") == "exactly"),
        "reproduced_in_part": sum(1 for f in findings if f.get("reproduced") == "in part"),
        "not_reproduced": sum(1 for f in findings if f.get("reproduced") == "no"),
        "rows": findings,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("findings", "reproduced_exactly", "reproduced_in_part",
                       "not_reproduced")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
