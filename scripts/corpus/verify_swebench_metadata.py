"""Verify the frozen metadata against an immutable dataset Parquet revision."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pyarrow
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json  # noqa: E402

STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
WORK = ROOT / ".attest/corpora/swebench-independent-v1-metadata"
FIELDS = ("instance_id", "repo", "base_commit", "created_at", "version")


def main() -> None:
    access = json.loads((STUDY / "metadata-access.json").read_bytes())
    revision = access["dataset_revision_after"]
    dataset = access["dataset"]
    destination = WORK / "pinned-data.parquet"
    if destination.exists():
        raise ValueError("pinned verification artifact already exists")
    url = f"https://huggingface.co/api/datasets/{dataset}/revision/{revision}"
    with urllib.request.urlopen(url, timeout=90) as response:
        description = json.loads(response.read())
    assert description["sha"] == revision
    files = [r["rfilename"] for r in description["siblings"] if r["rfilename"].endswith(".parquet")]
    if len(files) != 1:
        raise ValueError("expected one complete dataset Parquet")
    with urllib.request.urlopen(
        f"https://huggingface.co/datasets/{dataset}/resolve/{revision}/{files[0]}", timeout=120
    ) as response:
        payload = response.read()
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(payload)
    projected = pq.read_table(destination, columns=list(FIELDS)).to_pylist()
    earlier = json.loads((WORK / "metadata.json").read_bytes())
    identity = lambda row: row["instance_id"]  # noqa: E731
    equal = sorted(projected, key=identity) == sorted(earlier, key=identity)
    result = {
        "revision": revision,
        "parquet_path": files[0],
        "parquet_sha256": sha256_bytes(payload),
        "parquet_bytes": len(payload),
        "projection_columns": FIELDS,
        "row_count": len(projected),
        "all_projected_metadata_equal": equal,
        "earlier_metadata_sha256": sha256_bytes((WORK / "metadata.json").read_bytes()),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "pyarrow_version": pyarrow.__version__,
        "python": sys.version,
        "hidden_columns_read_by_arrow_or_shown_to_model": False,
        "raw_parquet_location": destination.relative_to(ROOT).as_posix(),
        "raw_parquet_mode": oct(destination.stat().st_mode & 0o777),
        "actual_model_api_spend_usd": 0,
    }
    write_canonical_json(STUDY / "pinned-metadata-check.json", result)
    if not equal or len(projected) != 500:
        raise ValueError("pinned metadata drift: existing freeze cannot advance")
    print("all 500 metadata projections match immutable revision", revision)


if __name__ == "__main__":
    main()
