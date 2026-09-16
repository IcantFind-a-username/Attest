# Independent font-cache/context review

Baseline: `71f761f`; branch `fix/source-font-cache`. Reviewed the uncommitted three-file diff and both new compatibility protocols, once. Tracked files were read-only.

## Findings

- **P1 — post-import build step restores networking** (`scripts/corpus/swebench_source_runtime.py:156`). The source import executes as root in the disposable stage under `--network=none`, and can modify that stage’s shell or `chmod`. The immediately following shell-form `RUN chmod` runs in that modified stage without `--network=none`. It can therefore execute source-controlled code with default build networking, contradicting the declared network-none preparation boundary. Make this step network-none as well (or perform permission adjustment in the same isolated invocation). This is established by the emitted Dockerfile ordering; no Docker/native escape execution was attempted.
- **P2 — special cache entries pass artifact validation** (`scripts/corpus/swebench_source_runtime.py:187`). Validation rejects links but does not reject entries that are neither regular files nor directories. A cache containing a regular JSON file plus a FIFO passes the count/size checks and records only the JSON digest. The complete cache is nevertheless retained in the image and copied by the launcher, where `shutil.copytree` rejects special files. Reject special entries explicitly so a successful cache record describes the accepted artifact and fails at preparation. Static predicate review; no special-file or Docker reproduction performed.

## Checks and scope

`PYTHONPATH=src {workspace}/.venv/bin/python -m pytest tests/test_original_test_overlay.py -q`: 7 passed. Default overlay remains existing-file-only; creation is explicit to the new arm, ancestor links are refused, identical bytes are applied to both sides, and production anchors remain required. Six-pair/twelve-revision selection and behavioral stop conditions are unchanged. Full integration gates remain the controller’s responsibility.

Diff stat at review: 3 tracked files, 98 insertions, 19 deletions; plus two untracked protocol documents. Reused existing canonical JSON/digest, `apply_wheel`, archive validation, `declared_version_file`, `execute_repro`, and `MPL_SEED_DIR`/launcher seed mechanism. No new utility introduced by the reviewer. Paid/API/remote/Docker actions: none.
