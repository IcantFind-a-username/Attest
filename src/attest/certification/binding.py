"""Claim/diff binding observations and the versioned policy that reads them (V-02).

A differential result alone proves that *something* in the change alters the
test's outcome; it does not prove the test exercised the changed code. The
binding observation records which changed lines of the anchored file the head
runs executed. Policy ``attest.binding.changed-line-coverage.v1`` requires at
least one executed changed line on every head run and DEFERs otherwise. Pure:
values in, verdict out.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

BINDING_POLICY_VERSION = "attest.binding.changed-line-coverage.v1"


@dataclass(frozen=True)
class BindingObservation:
    policy_version: str
    path: str
    changed_lines: tuple[int, ...]
    executed_changed_lines: tuple[int, ...]  # executed on every head run
    head_runs_observed: int

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def binding_verdict(observation: BindingObservation) -> str | None:
    """None when bound; otherwise the reason the run buys no regression evidence."""
    if observation.policy_version != BINDING_POLICY_VERSION:
        return "unknown binding policy"
    if observation.head_runs_observed < 1:
        return "no head run observed"
    if not observation.changed_lines:
        return f"{observation.path} has no changed lines to bind to"
    if not observation.executed_changed_lines:
        return f"the reproduction exercises none of the changed lines of {observation.path}"
    return None
