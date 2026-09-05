"""The delivery journal reads rows written under every past line shape (D-149).

A journal row records what was published **when it was written**. The validator
that reconciles those rows runs today, over a ledger that may hold rows from
before today's presentation rules existed, so a presentation token cannot be
made mandatory here without retroactively invalidating history -- and the
failure mode is not a refused publication, it is `attest review` aborting at
startup, because the alpha-tightening projection reconciles the journal before
a single candidate is read.

D-142 added the `[red]` level marker to the summary finding line and made it
mandatory in this check too. These tests pin the two properties that must both
hold: a pre-D-142 row still reconciles, and the binding the journal actually
owns -- body findings are exactly the declared members -- still refuses a
mismatch.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from attest.review.ci import build_delivery_transcript

TASK = "20260906-000000-deadbeef"
FINDING = "f9d26dc62d"


def _canonical(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _summary_intent(summary_line: str, *, members: tuple[str, ...] = (FINDING,)) -> dict:
    """One `status_summary` delivery intent, built the way the journal writes it."""
    body = {"body": "<!-- attest:status -->\nReview complete.\n" + summary_line + "\nSpend $0.03."}
    member_rows = [{"finding_id": finding, "placement": "inline"} for finding in members]
    request = {
        "method": "POST",
        "path": "/repos/o/r/issues/1/comments",
        "repository": "o/r",
        "pull_request_number": 1,
        "head_sha": "a" * 40,
        "channel": "status_summary",
        "members": member_rows,
        "body": body,
        "terminal_status": "completed",
        "deadline_s": 60.0,
        "attempt_ordinal": 0,
    }
    request_sha256 = _canonical(request)
    return {
        "ts": "2026-09-06T00:00:00+0800",
        "kind": "delivery_attempt_intent",
        "task_id": TASK,
        "attempt_id": hashlib.sha256(f"{TASK}:0:{request_sha256}".encode()).hexdigest(),
        "attempt_ordinal": 0,
        "repository": "o/r",
        "pull_request_number": 1,
        "head_sha": "a" * 40,
        "channel": "status_summary",
        "members": member_rows,
        "terminal_status": "completed",
        "request": request,
        "body_sha256": _canonical(body),
        "request_sha256": request_sha256,
        "deadline_s": 60.0,
    }


PRE_D142 = (
    f"- <!-- attest:finding-id:{FINDING} --> Finding ID: {FINDING}; "
    "requests/models.py:389 — the header is set unconditionally. (receipt 3253ada5eff4)"
)
CURRENT = (
    f"- <!-- attest:finding-id:{FINDING} --> [red] Finding ID: {FINDING}; "
    "requests/models.py:389 — the header is set unconditionally. (receipt 3253ada5eff4)"
)


@pytest.mark.parametrize("summary_line", (PRE_D142, CURRENT), ids=("pre-d142", "current"))
def test_a_summary_row_reconciles_whatever_line_shape_it_was_written_under(
    summary_line: str,
) -> None:
    transcript = build_delivery_transcript([_summary_intent(summary_line)], TASK)

    assert transcript.task_id == TASK
    assert transcript.expected_attempt_count == 1


def test_the_binding_the_journal_owns_still_refuses_a_body_that_is_not_its_members() -> None:
    """The check is about identifiers, and that half is untouched: a body naming
    one finding cannot be declared as the publication of another."""
    intent = _summary_intent(PRE_D142, members=("0123456789",))

    with pytest.raises(ValueError, match="publication body does not match declared members"):
        build_delivery_transcript([intent], TASK)
