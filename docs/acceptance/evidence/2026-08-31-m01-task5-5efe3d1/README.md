# M-01 Task 5 dual-Python Gate evidence

Status: **FAILED ENVIRONMENT — host volume returned `ENOSPC`; this is not a code Gate
PASS.**

- Candidate: `5efe3d1c046fef04d197542cc8abe3f413a92d56` (tree
  `a2909b5ef345d56ba0f95f8283a847c1309956d1`).
- `origin/main`: `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c`, verified as an ancestor.
- Python 3.11.5: the only full-pytest invocation reached 97%, then exited 120 after
  `ENOSPC`; no final count or coverage report exists.
- Python 3.12.8: the only full-pytest invocation reached about 99%, then exited 120 after
  `ENOSPC`; no final count or total/core coverage result exists.
- Both environments subsequently passed Ruff, Mypy (49 source files), `pip check`, source
  provenance, clean/detached checkout, diff, and frozen-v1 digest checks.
- No retry, paid provider call, remote write, factory change, or repository mutation occurred
  in either validation environment.

The raw streams, commands, exits, environment names, provenance, and post-failure checks are
preserved under `python-3.11/` and `python-3.12/`. Verify them offline from this directory:

```bash
(cd python-3.11 && shasum -a 256 -c ARTIFACTS.sha256)
(cd python-3.12 && shasum -a 256 -c ARTIFACTS.sha256)
```

Manifest SHA-256 values:

- Python 3.11: `7b07e92e4f4a5c1eaba81a4d6e68a1b5b8b8543403d2a5bf169f7238b09da6f3`
- Python 3.12: `7d0982bc9adbf9973055039035e0d56f36dae1f8fb848db039044457f42d60ba`

Before a separately authorized fresh Task 5 validation, require at least 8 GiB available:

```bash
df -Pk /private/tmp | awk 'NR == 2 { print $4; exit !($4 >= 8388608) }'
```
