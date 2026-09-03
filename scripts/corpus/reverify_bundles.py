"""Re-verify every evidence bundle on this host and mark the ones that fail.

D-124. ``attest verify --bundle`` answers one bundle; this walks every bundle
under the given roots, asks the same offline verifier, and writes an
``unverifiable_v1.json`` marker beside any bundle it rejects. Nothing is ever
deleted: a bundle that no longer verifies is still the record of what ran, and
the marker says which check refused it and under which code version.

    .venv/bin/python scripts/corpus/reverify_bundles.py --json report.json

By default it walks the workspace only. ``--root`` adds another tree; markers
are written only inside the workspace unless ``--mark-outside`` is given, so a
read-only pass over somebody else's checkout stays read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.types import AcceptedReceipt  # noqa: E402
from attest.review.evidence import BundleRejection, verify_bundle  # noqa: E402

MARKER_NAME = "unverifiable_v1.json"
MARKER_SCHEMA = "attest.unverifiable-bundle.v1"

# The failure families this host's history contains. A bundle is classified by
# the first family whose reason it matches; the raw reasons are kept verbatim.
FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("test_bytes_mismatch", ("test bytes do not match receipt.test_digest",)),
    ("stale_schema_fresh_state", ("did not start from fresh writable state",)),
    ("stale_schema_executor", ("ran under a different executor",)),
    ("stale_schema_provenance", ("provenance digest does not match the receipt body",)),
    ("intent_or_binding", ("intent observation", "binding observation")),
    ("digest_mismatch", ("digest mismatch for", "missing file")),
)


@dataclass
class Row:
    path: Path
    ok: bool
    reasons: tuple[str, ...]
    family: str
    task_id: str
    candidate_id: str
    repository_id: str
    head_sha: str
    test_bytes: int
    test_sha: str
    receipt_test_digest: str


def classify(reasons: tuple[str, ...]) -> str:
    for family, needles in FAMILIES:
        if any(needle in reason for reason in reasons for needle in needles):
            return family
    return "other" if reasons else "verified"


def inspect(directory: Path) -> Row:
    verdict = verify_bundle(directory)
    ok = isinstance(verdict, AcceptedReceipt)
    if isinstance(verdict, BundleRejection):
        reasons = verdict.reasons
    elif ok:
        reasons = ()
    else:
        reasons = tuple(code.value for code in verdict.codes)
    try:
        receipt = json.loads((directory / "receipt.json").read_bytes())
    except (OSError, ValueError):
        receipt = {}
    try:
        test_bytes = (directory / "test_repro.py").read_bytes()
    except OSError:
        test_bytes = b""
    return Row(
        path=directory,
        ok=ok,
        reasons=reasons,
        family=classify(reasons),
        task_id=str(receipt.get("task_id", "")),
        candidate_id=str(receipt.get("candidate_id", "")),
        repository_id=str(receipt.get("repository_id", "")),
        head_sha=str(receipt.get("head_sha", "")),
        test_bytes=len(test_bytes),
        test_sha=hashlib.sha256(test_bytes).hexdigest(),
        receipt_test_digest=str(receipt.get("test_digest", "")),
    )


def code_version() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def mark(row: Row, verifier_sha: str) -> None:
    """Write the marker beside the bundle. It is deliberately *not* in the
    manifest: the bundle's own digests must stay exactly what was written."""
    payload = {
        "schema_version": MARKER_SCHEMA,
        "status": "unverifiable_v1",
        "family": row.family,
        "reasons": list(row.reasons),
        "verifier_commit": verifier_sha,
        "receipt_test_digest": row.receipt_test_digest,
        "bundle_test_sha256": row.test_sha,
        "bundle_test_bytes": row.test_bytes,
    }
    (row.path / MARKER_NAME).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def discover(root: Path) -> list[Path]:
    return sorted({p.parent.resolve() for p in root.rglob(".attest/evidence/*/*/manifest.json")})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[], help="extra tree to walk")
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--no-mark", action="store_true", help="report only, write no markers")
    parser.add_argument(
        "--mark-outside", action="store_true", help="also mark bundles outside the workspace"
    )
    args = parser.parse_args(argv)

    roots = [ROOT] + [Path(r).expanduser().resolve() for r in args.root]
    directories: list[Path] = []
    for root in roots:
        for directory in discover(root):
            if directory not in directories:
                directories.append(directory)

    verifier_sha = code_version()
    rows = [inspect(directory) for directory in directories]
    marked = 0
    for row in rows:
        if row.ok or args.no_mark:
            continue
        inside = row.path.is_relative_to(ROOT)
        if inside or args.mark_outside:
            mark(row, verifier_sha)
            marked += 1

    families = Counter(row.family for row in rows if not row.ok)
    report = {
        "schema_version": "attest.bundle-reverification.v1",
        "verifier_commit": verifier_sha,
        "roots": [str(r) for r in roots],
        "total": len(rows),
        "verified": sum(1 for row in rows if row.ok),
        "unverifiable": sum(1 for row in rows if not row.ok),
        "marked": marked,
        "families": dict(sorted(families.items())),
        "bundles": [
            {
                "path": str(row.path),
                "ok": row.ok,
                "family": row.family,
                "task_id": row.task_id,
                "candidate_id": row.candidate_id,
                "repository_id": row.repository_id,
                "head_sha": row.head_sha,
                "test_bytes": row.test_bytes,
                "test_sha256": row.test_sha,
                "receipt_test_digest": row.receipt_test_digest,
                "reasons": list(row.reasons),
            }
            for row in rows
        ],
    }
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{report['total']} bundles: {report['verified']} verified, "
        f"{report['unverifiable']} unverifiable ({marked} marked)"
    )
    for family, count in sorted(families.items()):
        print(f"  {family}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
