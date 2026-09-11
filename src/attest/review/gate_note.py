"""The gate level's yellow line (owner instruction 5 of 2026-09-11, §16 item 2).

`docs/design/gate-level.md` §5: a different claim needs a different shape, or
the reader will hear "regression". The gate has **no base revision** -- it
reports that new code, reached through a caller the diff did not add, raised an
uncaught exception on an input the reproduction entered with, N times out of N,
in an image where a pre-existing test of the same caller passes. That is a
fact with coordinates and it is said at yellow: no receipt, no likelihood
ratio, no severity, and no word that means *broke*.

Only the **through-caller** grade speaks (§1). A `direct` witness -- the
reproduction called the new symbol itself -- stays a ledger row: its
reachability is argued from an annotation rather than seen in a trace.

The line is rendered from the `gate_shadow` ledger row, not from the stage's
objects, so the presentation path imports nothing that executes code. Rows
written before schema v2 carry no `entry` and render no line.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from attest.review.output_contract import ContractVerdict, check, claim_line

GATE_NOTE_POLICY_VERSION = "attest.gate-note.v1"
THROUGH_CALLER = "through_caller"
# design §5: at most one gate line per pull request
GATE_MAX_PER_REVIEW = 1


@dataclass(frozen=True)
class GateNote:
    policy_version: str
    call_site: str  # "path:line" of the caller the reproduction entered at
    caller: str  # the definition that call sits inside
    path: str  # the file of the added line
    origin_line: int
    exception_type: str
    entry: str  # the call the reproduction made, as written
    runs: int
    repeats: int
    task_id: str
    finding_id: str

    def note_id(self) -> str:
        body = "|".join(
            (self.call_site, self.path, str(self.origin_line), self.exception_type, self.entry)
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]

    @property
    def caller_path(self) -> str:
        return self.call_site.rsplit(":", 1)[0]

    @property
    def caller_line(self) -> int:
        return int(self.call_site.rsplit(":", 1)[1])

    def sentence(self) -> str:
        return (
            f"new code at {self.path}:{self.origin_line} raises {self.exception_type} on "
            f"{self.entry} ({self.runs}/{self.repeats} runs), reached through {self.caller}"
        )


def render(note: GateNote) -> str:
    """`[yellow] <caller file:line> — new code at <file:line> raises <E> on
    <input> (3/3 runs), reached through <caller> — gate <id>`."""
    return claim_line(
        "yellow",
        path=note.caller_path,
        line=note.caller_line,
        fact=note.sentence(),
        evidence=f"gate note {note.note_id()}",
    )


def admitted(note: GateNote) -> ContractVerdict:
    """The contract's verdict, with the entry call -- a measured literal, the
    reproduction's own text -- exempt from the banned-phrase rule."""
    return check(render(note), measured=(note.entry,))


def note_from_row(row: Mapping[str, object]) -> GateNote | None:
    """One `gate_shadow` row as a note, or None: not a would-publish row, not a
    through-caller witness, or a row too old to carry the entry call."""
    if row.get("kind") != "gate_shadow" or not row.get("would_publish"):
        return None
    if row.get("reachability") != THROUGH_CALLER:
        return None
    call_site = row.get("call_site")
    entry = row.get("entry")
    if not isinstance(call_site, str) or ":" not in call_site or not isinstance(entry, str):
        return None
    if not entry:
        return None
    try:
        repeats = _as_int(row.get("repeats"))
        return GateNote(
            policy_version=GATE_NOTE_POLICY_VERSION,
            call_site=call_site,
            caller=str(row.get("caller") or ""),
            path=str(row["path"]),
            origin_line=_as_int(row["origin_line"]),
            exception_type=str(row["exception_type"]),
            entry=entry,
            runs=repeats if row.get("runs_agreeing") else 0,
            repeats=repeats,
            task_id=str(row.get("task_id") or ""),
            finding_id=str(row.get("finding_id") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("not an integer field")
    return int(value)


def note_from_observation(observation: object, *, task_id: str, finding_id: str) -> GateNote | None:
    """The same rule, applied to a live observation through its own row."""
    row = observation.to_ledger_row(task_id, finding_id)  # type: ignore[attr-defined]
    return note_from_row(row)


def visible(notes: list[GateNote]) -> list[GateNote]:
    """The gate lines an author may see: admitted by the contract, and at most
    `GATE_MAX_PER_REVIEW` per pull request (design §5)."""
    return [note for note in notes if admitted(note).admitted][:GATE_MAX_PER_REVIEW]
