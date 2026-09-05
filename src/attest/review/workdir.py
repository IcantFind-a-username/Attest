"""Where a reproduction actually runs (D-138).

Every execution path the product owns -- the generated test, the controller's
inputs and outputs mounts, and the two throwaway ``git worktree`` trees --
used to live under ``<repo>/.attest/repro``. On macOS with Docker Desktop that
put a bind mount source inside the user's home directory, and on 2026-09-05 a
Docker Desktop fault made **every** bind mount of a path under ``/Users/franz``
hang indefinitely while the same mount of ``/private/tmp`` returned in a
second. The whole window's execution was blocked behind it.

So the working directory moves out of the repository tree: one session
subdirectory under ``tempfile.gettempdir()``, keyed by the repository so two
repositories reviewed by one process never share a path. **Only** the durable
record -- the evidence bundle, the ledger, the receipt, the candidate file,
the attempt cache -- is still written under ``<repo>/.attest``.

The session component is minted once per process. A review is one process, so
every reproduction of one run lands under one root and one ``rmtree`` at the
end of the process would clear the lot; each differential still removes its own
trees, as it did before.

``ATTEST_WORK_ROOT`` overrides the parent directory (tests, and any host whose
temporary directory the container runtime cannot share).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
from pathlib import Path

ENV_WORK_ROOT = "ATTEST_WORK_ROOT"
WORK_PREFIX = "attest-work"

# One per process, minted at import: the pid alone collides after a pid wrap,
# and a bare token would give a resumed process a different root.
_SESSION = f"{os.getpid()}-{secrets.token_hex(4)}"


def session_id() -> str:
    """The session component of this process's working root."""
    return _SESSION


def work_parent() -> Path:
    """The temporary directory the working root is placed in.

    ``realpath`` matters: on macOS ``gettempdir()`` returns a path under
    ``/var``, which is a symlink to ``/private/var``, and a container runtime
    is given the resolved path or refuses the mount.
    """
    override = os.environ.get(ENV_WORK_ROOT, "").strip()
    if override:
        return Path(os.path.realpath(override))
    return Path(os.path.realpath(tempfile.gettempdir()))


def repo_key(repo: Path) -> str:
    """A stable, filesystem-safe name for a repository path.

    The basename is kept for a human reading ``ps`` or a stale directory; the
    digest is what makes it unique, because two clones of the same project sit
    side by side in this corpus under the same name.
    """
    resolved = os.path.realpath(repo)
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
    name = Path(resolved).name or "repo"
    safe = "".join(
        character if character.isalnum() or character in "-_." else "-" for character in name
    )
    return f"{safe[:40]}-{digest}"


def work_root(repo: Path) -> Path:
    """This process's working root for ``repo``. Never inside the repository."""
    return work_parent() / f"{WORK_PREFIX}-{_SESSION}" / repo_key(repo)


def repro_root(repo: Path, task_id: str, finding_id: str) -> Path:
    """The working directory of one candidate's reproduction."""
    return work_root(repo) / "repro" / task_id / finding_id


def gate_root(repo: Path, task_id: str, finding_id: str) -> Path:
    """The working directory of one candidate's gate-level observation (D-137)."""
    return work_root(repo) / "gate" / task_id / finding_id


def inside(path: Path, root: Path) -> bool:
    """Is ``path`` at or below ``root``, both resolved? (the RED test's predicate)"""
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(root)))
    except ValueError:
        return False
    return True
