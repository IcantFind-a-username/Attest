"""Re-verify every stored evidence bundle with the code this script sits next to.

D-255 changed the intent rule's record shape for contracts (two fields, v6.1 only) and the
verifier's contract-field check. A bundle written before it must verify exactly as it did:
run this once from a checkout of the earlier commit and once from the new one, and compare.

    .venv/bin/python scripts/corpus/bundle_reverify.py --out after.jsonl

Reads bundles under `.attest/corpora/` of the repository given by `--repo` (default: this
checkout); writes nothing into them. No key: the seal is reported, not required.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.evidence import verify_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    corpora = Path(args.repo) / ".attest" / "corpora"
    rows = []
    for manifest in sorted(corpora.glob("**/.attest/evidence/*/*/manifest.json")):
        bundle = manifest.parent
        intent = bundle / "intent.json"
        policy = ""
        if intent.is_file():
            try:
                record = json.loads(intent.read_text(encoding="utf-8"))
                policy = str(record.get("policy_version", ""))
            except (OSError, ValueError):
                policy = "<unreadable>"
        result = verify_bundle(bundle)
        rows.append({
            "bundle": bundle.relative_to(corpora).as_posix(),
            "intent_policy": policy,
            "result": type(result).__name__,
            "reasons": list(getattr(result, "reasons", ()) or ()),
        })
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                              encoding="utf-8")
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["intent_policy"], r["result"])
        counts[key] = counts.get(key, 0) + 1
    for (policy, result), n in sorted(counts.items()):
        print(f"{policy or '<no intent>':24} {result:18} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
