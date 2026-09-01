# M-01 Task 5 dual-Python recovery Gate evidence

Status: **PASS — `G-CODE-001` recovery evidence for M-01 / `G-MEASURE-001`.**

- Candidate: `5efe3d1c046fef04d197542cc8abe3f413a92d56` (tree
  `a2909b5ef345d56ba0f95f8283a847c1309956d1`).
- Authoritative `origin/main` at recovery: `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c`;
  it is an ancestor of the candidate. `ff0e638` changes only documentation/evidence relative
  to the candidate over the code/Gate scope.
- Python 3.11.5: one full-pytest invocation, 1543/1543 passed; total coverage
  12373/13728 (90.129662%); core coverage 428/429 (99.766900%); Ruff, Mypy,
  `pip check`, provenance, clean/diff, and frozen-v1 hashes passed.
- Python 3.12.8: the same test and coverage results; all corresponding static,
  provenance, clean/diff, and frozen-v1 checks passed.
- No paid/provider call, remote write, factory-statistics change, pricing change, Gate
  relaxation, or product-code mutation occurred.

The earlier exact-SHA attempts remain immutable failed-environment evidence: both reached
the end of their suites but the host returned `ENOSPC` before usable totals existed. After
reclaiming reconstructible temporary checkouts and requiring at least 8 GiB free, this
separately authorized recovery task ran each interpreter serially and invoked full pytest
once per interpreter. It does not relabel the earlier attempts as passes.

An old delegated task resumed while the Python 3.12 post-Gate manifest was being sealed and
added duplicate logs to that temporary evidence root. It was stopped before any repository
write; 87 precisely identified foreign files were excluded, the remaining file set stayed
stable, and the final manifest below was rebuilt and verified. The retained removal-name
inventory is `python-3.12/foreign-files-removed.txt`; no Gate was rerun.

Verify the raw evidence offline from this directory:

```bash
(cd python-3.11 && shasum -a 256 -c ARTIFACTS.sha256)
(cd python-3.12 && shasum -a 256 -c ARTIFACTS.sha256)
shasum -a 256 -c ARTIFACTS.sha256
```

Child manifest SHA-256 values:

- Python 3.11: `902d895b312d9b1fa8ce930e9a7212e025432049fe2fd2ee73fae37316003f02`
- Python 3.12: `02d94476ad00633c8d8e350048bb76a296b3ad7a7a8fdc859fd66f03a66f467a`

The Python 3.11 local clone recorded that clone's local `main` ref (`6293aab`) in its
summary. `SOURCE_PROVENANCE.txt` separately binds the authoritative source worktree's
fetched `origin/main` (`1f6f73e`) and its successful ancestor/scoped-diff checks; the
Python 3.12 environment records the same authoritative ref directly.
