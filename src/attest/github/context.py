"""Pull-request context derived from GitHub Actions event payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PullRequestContext:
    repository: str
    number: int
    base_sha: str
    head_sha: str
    is_fork: bool


def load_pull_request_context(event_path: Path) -> PullRequestContext:
    """Load the pull-request fields the action can safely operate on."""
    event = json.loads(event_path.read_text(encoding="utf-8"))
    if not isinstance(event, dict):
        raise ValueError("GitHub event must be an object")
    return _context_from_event(event)


def _context_from_event(event: dict[str, Any]) -> PullRequestContext:
    try:
        repository = str(event["repository"]["full_name"])
        number = int(event["number"])
        pull_request = event["pull_request"]
        base_sha = str(pull_request["base"]["sha"])
        head_sha = str(pull_request["head"]["sha"])
        head_repository = str(pull_request["head"]["repo"]["full_name"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("GitHub event is missing pull-request context") from exc
    return PullRequestContext(
        repository=repository,
        number=number,
        base_sha=base_sha,
        head_sha=head_sha,
        is_fork=head_repository != repository,
    )
