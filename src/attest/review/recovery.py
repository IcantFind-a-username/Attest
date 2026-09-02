"""Precommitted structured-output recovery for proposal samples (R-02).

A proposal sample that stops at the output bound is a truncated JSON
document. Two recoveries are allowed, both declared here before any sample is
bought and both blind to behavioural outcomes (proposals precede every
execution):

1. deterministic local salvage — the complete finding objects that precede
   the cut are kept, the partial tail is dropped, and the sample is marked
   ``salvaged:<n>``; no model call is made;
2. one preregistered model repair attempt per sample slot when nothing is
   salvageable — the same prompt is sampled again under the same bound.

Every attempt is cached under an immutable digest of its inputs and attempt
index, so a repeated run replays the recorded attempts in order instead of
buying new ones, and no run can pick the best of several. The number of
repair attempts is a constant, never a parameter.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RECOVERY_SCHEMA_VERSION = "attest.recovery.v1"
MODEL_REPAIR_ATTEMPTS = 1  # per sample slot; preregistered, not configurable

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Salvage:
    findings: list[dict[str, Any]]
    status: str  # "intact" | "salvaged:<n>" | "empty" | "unrecoverable"


def salvage_findings(text: str) -> Salvage:
    """Deterministically recover the complete findings from a proposal payload."""
    stripped = text.strip()
    fenced = _FENCE_RE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        findings = payload.get("findings", [])
        if isinstance(findings, list):
            return Salvage(findings, "intact" if findings else "empty")
        return Salvage([], "unrecoverable")
    # truncated document: walk the findings array object by object
    start = stripped.find('"findings"')
    if start < 0:
        return Salvage([], "unrecoverable")
    array_start = stripped.find("[", start)
    if array_start < 0:
        return Salvage([], "unrecoverable")
    decoder = json.JSONDecoder()
    position = array_start + 1
    complete: list[dict[str, Any]] = []
    while True:
        while position < len(stripped) and stripped[position] in " \t\r\n,":
            position += 1
        if position >= len(stripped) or stripped[position] != "{":
            break
        try:
            value, end = decoder.raw_decode(stripped, position)
        except json.JSONDecodeError:
            break  # the partial tail
        if isinstance(value, dict):
            complete.append(value)
        position = end
    if not complete:
        return Salvage([], "unrecoverable")
    return Salvage(complete, f"salvaged:{len(complete)}")


def attempt_digest(
    system: str,
    prompt: str,
    schema: dict[str, Any],
    max_tokens: int,
    slot: int,
    attempt: int,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Immutable identity of one paid attempt: inputs, sample slot, attempt
    index and, since 2026-09-03, the model call parameters (model id and the
    thinking/effort arguments), so a changed call is a new attempt rather than
    a replay of an old response."""
    material = json.dumps(
        {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "system": system,
            "prompt": prompt,
            "schema": schema,
            "max_tokens": max_tokens,
            "slot": slot,
            "attempt": attempt,
            "parameters": parameters or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedAttempt:
    text: str | None  # None: the response carried no text block
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    content_types: tuple[str, ...] = ("text",)
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class AttemptCache:
    """Immutable-digest cache of paid sample attempts under ``.attest/cache``."""

    def __init__(self, root: Path | None) -> None:
        self.directory = None if root is None else root / ".attest" / "cache" / "attempts"

    def _path(self, digest: str) -> Path | None:
        return None if self.directory is None else self.directory / f"{digest}.json"

    def get(self, digest: str) -> CachedAttempt | None:
        path = self._path(digest)
        if path is None or not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != RECOVERY_SCHEMA_VERSION:
            return None
        try:
            content_types = raw.get("content_types")
            return CachedAttempt(
                text=None if raw.get("text") is None else str(raw["text"]),
                input_tokens=int(raw["input_tokens"]),
                output_tokens=int(raw["output_tokens"]),
                stop_reason=(None if raw.get("stop_reason") is None else str(raw["stop_reason"])),
                content_types=(
                    ("text",)
                    if not isinstance(content_types, list)
                    else tuple(str(item) for item in content_types)
                ),
                cache_creation_input_tokens=int(raw.get("cache_creation_input_tokens") or 0),
                cache_read_input_tokens=int(raw.get("cache_read_input_tokens") or 0),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, digest: str, attempt: CachedAttempt) -> None:
        path = self._path(digest)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return  # first record wins; attempts are never rewritten
        path.write_text(
            json.dumps(
                {
                    "schema_version": RECOVERY_SCHEMA_VERSION,
                    "digest": digest,
                    "text": attempt.text,
                    "input_tokens": attempt.input_tokens,
                    "output_tokens": attempt.output_tokens,
                    "stop_reason": attempt.stop_reason,
                    "content_types": list(attempt.content_types),
                    "cache_creation_input_tokens": attempt.cache_creation_input_tokens,
                    "cache_read_input_tokens": attempt.cache_read_input_tokens,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
