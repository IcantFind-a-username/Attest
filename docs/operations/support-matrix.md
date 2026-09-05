# Executor support matrix (L-01)

| dimension | supported | how it fails when unsupported |
|---|---|---|
| language | Python projects; the changed file must be `.py` | candidate classified ineligible before any paid generation (`unsupported anchor language`) |
| test runner | pytest, run from the tree under review with its own `conftest.py` honoured | collection DEFER: `pytest collection/import/syntax or infrastructure failure` |
| repository layout | flat packages, `src/` layouts, and multi-package trees (`services/*/src`) discovered by `pyproject.toml`/`setup.py`/`setup.cfg` at depth ≤ 4; each project's `tests/` importable by module name | the anchored module imported from outside the tree is a typed `UNBOUND` DEFER naming the origin |
| dependencies | installed at image build time from the tree's manifests (`pip install <project>`; `requirements*.txt` best-effort) | `environment bootstrap failed: …` in the run status; nothing is certified |
| interpreter | **3.10–3.13**: the highest supported `python:3.X-slim` the tree's own declaration allows — a `Programming Language :: Python :: 3.X` classifier is the ceiling, and the strictest floor from `requires-python` **or a lock file** (`uv.lock`'s `requires-python`, `poetry.lock`'s `python-versions`, `Pipfile`'s `python_version`) is the floor. A tree that declares nothing usable gets the **primary, 3.12** (D-162) | a project declaring a range outside 3.10–3.13 gets the primary and may fail to import; that is a bootstrap or collection DEFER, never a finding. 3.9 is no longer offered |
| isolation (production) | `linux-container-v1`: Docker/OCI, `--network none`, read-only root, uid 65534, no capabilities, tmpfs scratch, pid limit, `RLIMIT_NPROC` 0 | production DEFERs every candidate with `isolation backend unavailable`; it never falls back to the host |
| isolation (local `attest review`) | the container when Docker is present; otherwise the host adapter (language guards only, no OS boundary), stated in the ledger | — |
| subprocesses, threads, network from head code | not supported: the run is marked and DEFERs | `reproduction attempted to create a child process` / `… a thread` / `… a network connection` |
| writes outside the outputs/scratch directories | not supported: marked and DEFERs | `reproduction attempted to write outside its work directory` |
| new code (no merge-base definition) | recorded as `new_code_candidate`, never priced or published | typed abstention |
| non-Python changes | not reviewed | ineligible |
| platforms tested | macOS with Docker Desktop (Linux VM daemon); GitHub-hosted Linux runners are the declared CI platform | `G-SEC-002`'s full red-team matrix on the CI platform is still open (roadmap) |
