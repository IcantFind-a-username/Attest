"""A torn delivery journal is sealed, not left to abort every later review (D-154).

A review killed between its last delivery settlement and its journal
finalization leaves a journal no run will ever close. Every later
reconciliation refuses it, and the refusal is not a refused publication --
it is `attest review` aborting at startup, because the alpha-tightening
projection reconciles the journal before a single candidate is read. The
repository becomes unreviewable for good.

The repair is a second terminator with the same binding a finalization has:
one signed abort record appended by the next review, sealing the torn rows
exactly as they stand. Nothing already written is edited, and the digest is
over the sealed rows, so tampering with them -- or with the seal -- is still
refused.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from attest.review.ci import (
    DELIVERY_ABORT_KIND,
    build_delivery_transcript,
    reconcile_delivery_rows,
    seal_unterminated_delivery_journals,
    unterminated_delivery_task_ids,
)
from attest.review.config import ReviewConfig
from attest.review.ledger import Ledger
from attest.review.proposer import MockProvider
from attest.review.run import run_review

TASK = "20260906-101500-c0ffee01"
FINDING = "aa11bb22cc"
REASON = "an earlier review ended before it finalized this journal"


def _canonical(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _intent(task_id: str = TASK) -> dict:
    body = {
        "body": "<!-- attest:status -->\nReview complete.\n"
        f"- <!-- attest:finding-id:{FINDING} --> [red] Finding ID: {FINDING}; "
        "a.py:1 — the guard is gone. (receipt 3253ada5eff4)\nSpend $0.03."
    }
    members = [{"finding_id": FINDING, "placement": "inline"}]
    request = {
        "method": "POST",
        "path": "/repos/o/r/issues/1/comments",
        "repository": "o/r",
        "pull_request_number": 1,
        "head_sha": "a" * 40,
        "channel": "status_summary",
        "members": members,
        "body": body,
        "terminal_status": "completed",
        "deadline_s": 60.0,
        "attempt_ordinal": 0,
    }
    request_sha256 = _canonical(request)
    return {
        "ts": "2026-09-06T10:15:00+0800",
        "kind": "delivery_attempt_intent",
        "task_id": task_id,
        "attempt_id": hashlib.sha256(f"{task_id}:0:{request_sha256}".encode()).hexdigest(),
        "attempt_ordinal": 0,
        "repository": "o/r",
        "pull_request_number": 1,
        "head_sha": "a" * 40,
        "channel": "status_summary",
        "members": members,
        "terminal_status": "completed",
        "request": request,
        "body_sha256": _canonical(body),
        "request_sha256": request_sha256,
        "deadline_s": 60.0,
    }


def _settlement(intent: dict) -> dict:
    return {
        "ts": "2026-09-06T10:15:03+0800",
        "kind": "delivery_attempt_settlement",
        "task_id": intent["task_id"],
        "attempt_id": intent["attempt_id"],
        "outcome": "succeeded",
        "remote_response_id": "1234567890",
        "delivered_at_s": 3.0,
    }


def _torn_ledger(tmp_path) -> Ledger:
    """A settled attempt whose run died before it wrote its finalization."""
    ledger = Ledger(tmp_path)
    ledger.append(
        {
            "kind": "ci_final",
            "task_id": TASK,
            "decisions": [
                {
                    "finding_id": FINDING,
                    "action": "surface",
                    "placement": "inline",
                    "wealth_final": 42.0,
                }
            ],
            "spend_usd": 0.03,
        }
    )
    intent = _intent()
    ledger.append(intent)
    ledger.append(_settlement(intent))
    return ledger


def test_a_torn_journal_is_refused_until_it_is_sealed(tmp_path) -> None:
    ledger = _torn_ledger(tmp_path)

    with pytest.raises(ValueError, match="requires one exact finalization"):
        reconcile_delivery_rows(ledger.entries(), TASK)

    assert unterminated_delivery_task_ids(ledger.entries()) == (TASK,)


def test_sealing_appends_one_abort_and_makes_the_repository_reviewable(tmp_path) -> None:
    ledger = _torn_ledger(tmp_path)
    before = ledger.entries()

    sealed = seal_unterminated_delivery_journals(ledger, reason=REASON)

    assert len(sealed) == 1 and sealed[0].task_id == TASK
    rows = ledger.entries()
    # nothing already written was touched; exactly one row was added
    assert rows[: len(before)] == before
    assert len(rows) == len(before) + 1
    assert rows[-1]["kind"] == DELIVERY_ABORT_KIND and rows[-1]["reason"] == REASON

    publications, _tasks = reconcile_delivery_rows(rows, TASK)
    # what actually settled is still recorded as published -- sealing is not
    # an erasure of what the killed run really did
    assert [event.outcome for event in publications] == ["succeeded"]
    assert unterminated_delivery_task_ids(rows) == ()
    # and the projection that aborts startup now runs
    assert ledger.surfaced_finding_ids(rows) == (FINDING,)


def test_a_tampered_abort_record_is_refused(tmp_path) -> None:
    ledger = _torn_ledger(tmp_path)
    seal_unterminated_delivery_journals(ledger, reason=REASON)
    rows = ledger.entries()

    forged = {**rows[-1], "transcript_sha256": "f" * 64}
    with pytest.raises(ValueError, match="transcript mismatch"):
        reconcile_delivery_rows([*rows[:-1], forged], TASK)

    no_reason = {key: value for key, value in rows[-1].items() if key != "reason"}
    with pytest.raises(ValueError, match="invalid field set"):
        reconcile_delivery_rows([*rows[:-1], no_reason], TASK)


def test_sealed_rows_cannot_be_edited_afterwards(tmp_path) -> None:
    """The seal binds the torn rows, so changing one of them is detected."""
    ledger = _torn_ledger(tmp_path)
    seal_unterminated_delivery_journals(ledger, reason=REASON)
    rows = ledger.entries()

    edited = {**rows[2], "outcome": "failed"}
    with pytest.raises(ValueError):
        reconcile_delivery_rows([rows[0], rows[1], edited, rows[3]], TASK)


def test_nothing_may_be_appended_to_a_sealed_journal(tmp_path) -> None:
    ledger = _torn_ledger(tmp_path)
    seal_unterminated_delivery_journals(ledger, reason=REASON)
    rows = ledger.entries()

    with pytest.raises(ValueError, match="after its physical finalization"):
        reconcile_delivery_rows([*rows, _intent()], TASK)
    with pytest.raises(ValueError, match="cannot build a transcript after finalization"):
        build_delivery_transcript(rows, TASK)


def test_sealing_is_idempotent_and_leaves_finalized_journals_alone(tmp_path) -> None:
    ledger = _torn_ledger(tmp_path)
    seal_unterminated_delivery_journals(ledger, reason=REASON)
    count = len(ledger.entries())

    assert seal_unterminated_delivery_journals(ledger, reason=REASON) == ()
    assert len(ledger.entries()) == count


def test_a_killed_review_does_not_make_the_repository_unreviewable(tmp_path) -> None:
    """The end-to-end shape of D-154: kill a review after its last settlement
    and the next `attest review` used to abort at startup, before a candidate
    was read, for every review that repository would ever get again."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text(
        "def total(items):\n    return sum(items)\n\n\ndef average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    _torn_ledger(tmp_path)

    payload = json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "app.py", "line": 5},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and observe the exception",
                }
            ]
        }
    )
    run = run_review(
        tmp_path,
        None,
        ReviewConfig(probe_generation=False, k_samples=1, tier0_commands=[]),
        MockProvider([payload]),
    )

    assert len(run.results) == 1
    assert any("sealed 1 unfinished delivery journal" in note for note in run.notes)
    rows = Ledger(tmp_path).entries()
    assert [row["kind"] for row in rows].count(DELIVERY_ABORT_KIND) == 1
    assert unterminated_delivery_task_ids(rows) == ()
