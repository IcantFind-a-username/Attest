# Support matrix (L-01)

Read the first table before installing: it is the environment attest runs *in*. The second
is what it can review. Every "how it fails" cell is copy a user actually meets — no row here
fails as a traceback, and none of them fails as a silence that reads *nothing found*.

## Where attest itself runs

| dimension | supported | how it fails when unsupported |
|---|---|---|
| runner platform | **GitHub-hosted `ubuntu-*` runners only.** This is the declared CI platform and the only one the red-team matrix and the isolation backend are exercised on | `macos-*` and `windows-*` runners are **not supported**: they have no Docker daemon the action can use, so every candidate DEFERs with `isolation backend unavailable` and the review publishes nothing. A self-hosted Linux runner with Docker is untested — it is neither supported nor blocked |
| CI integration | **A GitHub Action plus a repository Secret, and nothing else** (mainline §1.2). No hosted service, no proxy, no key upload | any other integration is out of scope; the product never holds a customer key |
| interpreter attest runs on | the Action pins **3.12.8** in its own virtualenv, isolated from the reviewed project. The package declares `requires-python >= 3.11` | an older interpreter fails at `pip install`, before any review starts |
| Docker | **required in production.** The reproduction runs in `linux-container-v1`; there is no production fallback to the host | `unsupported: docker is not available here, and Attest runs head code only inside a container; nothing was verified.` — one line, exit 0 |
| fork pull requests | **not reviewed.** Two independent gates: the workflow's `if:` guard, and `scripts/action-gate.sh` inside the action. No `pull_request_target` anywhere in this repository | the job is skipped before any credential enters a runner step. **No comment, no check annotation, no artifact** — nothing that could read as *reviewed, nothing found* |
| network from the controller | the model API and the GitHub API only | — |

## What attest can review

| dimension | supported | how it fails when unsupported |
|---|---|---|
| language | Python projects; the changed file must be `.py` | candidate classified ineligible before any paid generation (`unsupported anchor language`) |
| test runner | pytest, run from the tree under review with its own `conftest.py` honoured | collection DEFER: `pytest collection/import/syntax or infrastructure failure` |
| repository layout | flat packages, `src/` layouts, and multi-package trees (`services/*/src`) discovered by `pyproject.toml`/`setup.py`/`setup.cfg` at depth ≤ 4; each project's `tests/` importable by module name | the anchored module imported from outside the tree is a typed `UNBOUND` DEFER naming the origin |
| dependencies | installed at image build time from the tree's manifests (`pip install <project>`; `requirements*.txt` best-effort) | `environment bootstrap failed: …` in the run status; nothing is certified |
| **no lock file** | **supported, and the common case.** A lock file is never required: the image installs the project from its own manifests, and the lock is read only for an interpreter *floor* (`uv.lock`, `poetry.lock`, `Pipfile`). With none present the floor is whatever `requires-python` says, or the primary 3.12 | not a refusal. The lock files that *are* read must at least parse: an unparsable one is `unsupported: this repository's dependency lock file cannot be parsed …`, decided before anything is spent |
| **a project that versions itself from the repository** (`setuptools_scm`, `hatch-vcs`) | supported: the tree is copied without `.git`, so the build is given `SETUPTOOLS_SCM_PRETEND_VERSION` from the committed `_version.py`, or `0.0.1` when that file is gitignored (D-176) | before D-176 a `hatch-vcs` project failed the whole image build; measured on `tenacity` |
| interpreter | **3.10–3.13**: the highest supported `python:3.X-slim` the tree's own declaration allows — a `Programming Language :: Python :: 3.X` classifier is the ceiling, and the strictest floor from `requires-python` **or a lock file** (`uv.lock`'s `requires-python`, `poetry.lock`'s `python-versions`, `Pipfile`'s `python_version`) is the floor. A tree that declares nothing usable gets the **primary, 3.12** (D-162) | a project declaring a range outside 3.10–3.13 gets the primary and may fail to import; that is a bootstrap or collection DEFER, never a finding. Since D-186 a run that collects **no test at all** in such a tree is a stated refusal — *this project declares Python outside 3.10-3.13* — rather than a missing-artifact message that reads as a broken host (D-185). 3.9 is no longer offered |
| isolation (production) | `linux-container-v1`: Docker/OCI, `--network none`, read-only root, uid 65534, no capabilities, tmpfs scratch, pid limit, `RLIMIT_NPROC` 0 | production DEFERs every candidate with `isolation backend unavailable`; it never falls back to the host |
| isolation (local `attest review`) | the container when Docker is present; otherwise the host adapter (language guards only, no OS boundary), stated in the ledger | — |
| subprocesses, threads, network from head code | not supported: the run is marked and DEFERs | `reproduction attempted to create a child process` / `… a thread` / `… a network connection` |
| writes outside the outputs/scratch directories | not supported: marked and DEFERs | `reproduction attempted to write outside its work directory` |
| new code (no merge-base definition) | recorded as `new_code_candidate`, never priced or published | typed abstention |
| non-Python changes | not reviewed | ineligible |
| platforms tested | macOS with Docker Desktop (Linux VM daemon) for local `attest review`; GitHub-hosted `ubuntu-latest` for everything else. The nine-class red-team matrix has run on a GitHub-hosted runner ([report](../acceptance/2026-09-07-redteam-nine.md)) | `G-SEC-002`'s **external observer** condition is still open: the harness's own claims are corroborated by an audit record on one run, not on the matrix (roadmap) |
