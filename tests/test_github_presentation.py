from __future__ import annotations

import json
from pathlib import Path

import pytest

from attest.review.channels import ChannelPurchase
from attest.review.gate import GateResult
from attest.review.schema import Finding


def _result(
    *,
    claim: str = "Null input reaches the serializer.",
    file: str = "src/service.py",
    line: int = 24,
    scenario: str = "A request omits its payload.",
    plan: str = "Call serialize with None.",
    wealth: float = 20.0,
    decision: int | None = 1,
) -> GateResult:
    return GateResult(
        finding=Finding(
            claim=claim,
            file=file,
            line=line,
            failure_scenario=scenario,
            falsification_plan=plan,
        ),
        wealth=wealth,
        purchases=[ChannelPurchase("V", 20.0, "reproduced")],
        decision=decision,
    )


def test_load_pull_request_context_reads_same_repository_event(tmp_path: Path) -> None:
    from attest.github.context import load_pull_request_context

    event = {
        "number": 42,
        "repository": {"full_name": "octo/widgets"},
        "pull_request": {
            "base": {"sha": "base-sha"},
            "head": {"sha": "head-sha", "repo": {"full_name": "octo/widgets"}},
        },
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")

    context = load_pull_request_context(path)

    assert context.repository == "octo/widgets"
    assert context.number == 42
    assert context.base_sha == "base-sha"
    assert context.head_sha == "head-sha"
    assert context.is_fork is False


def test_load_pull_request_context_identifies_fork_event(tmp_path: Path) -> None:
    from attest.github.context import load_pull_request_context

    event = {
        "number": 7,
        "repository": {"full_name": "octo/widgets"},
        "pull_request": {
            "base": {"sha": "base"},
            "head": {"sha": "fork-head", "repo": {"full_name": "contributor/widgets"}},
        },
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")

    assert load_pull_request_context(path).is_fork is True


def test_running_status_never_names_unverified_candidate_details() -> None:
    from attest.github.presentation import render_running

    running = render_running(candidate_count=2)

    for private_detail in (
        "Null input reaches the serializer.",
        "src/service.py",
        "24",
        "A request omits its payload.",
        "Call serialize with None.",
    ):
        assert private_detail not in running
    assert "2" in running


def test_deferred_status_contains_only_its_reason() -> None:
    from attest.github.presentation import render_deferred

    assert render_deferred("verification timed out") == "verification timed out"


def test_complete_status_names_only_certified_findings(certified_factory) -> None:
    from attest.github.presentation import render_complete

    first = certified_factory(claim="Surface one.")
    overflow = certified_factory(claim="Surface two.", path="src/other.py", line=8)

    complete = render_complete([first, overflow], 0.0125, 3.2)

    assert "Verified findings (each backed by a reproduction receipt):" in complete
    assert "Surface one." in complete
    assert "Surface two." in complete
    first_id = first.accepted_receipt.receipt.candidate_id
    overflow_id = overflow.accepted_receipt.receipt.candidate_id
    assert f"Finding ID: {first_id}" in complete
    assert f"Finding ID: {overflow_id}" in complete
    assert "$0.0125" in complete
    assert "3.2s" in complete
    # D-142: a wholly silent review is exactly the contract's silence line
    from attest.review.output_contract import silence_line

    assert render_complete([], 0.0, 1.0, units=(4, 9)) == silence_line(
        units_read=4, units_planned=9, spend_usd=0.0, elapsed_s=1.0
    )

    # anything that is not a validator-built CertifiedFinding is refused,
    # including the legacy wealth-gated result type
    with pytest.raises(TypeError, match="CertifiedFinding"):
        render_complete([_result(claim="Forged.", wealth=99.0)], 0.0, 1.0)  # type: ignore[list-item]


def test_inline_comments_keep_caller_order_anchors_and_receipt(certified_factory) -> None:
    from attest.github.presentation import inline_comments

    with pytest.raises(TypeError, match="CertifiedFinding"):
        inline_comments([_result(decision=1)])  # type: ignore[list-item]

    findings = [
        certified_factory(claim="First.", path="a.py", line=1),
        certified_factory(claim="Second.", path="b.py", line=2),
        certified_factory(claim="Third.", path="c.py", line=3),
        certified_factory(claim="Fourth.", path="d.py", line=4),
    ]
    comments = inline_comments(findings)

    assert [comment["path"] for comment in comments] == ["a.py", "b.py", "c.py"]
    assert [comment["line"] for comment in comments] == [1, 2, 3]
    assert all(comment["side"] == "RIGHT" for comment in comments)
    body = str(comments[0]["body"])
    receipt = findings[0].accepted_receipt.receipt
    assert "First." in body
    assert f"Finding ID: {receipt.candidate_id}" in body
    assert "Verified: the generated test failed on head in 3/3 runs" in body
    assert f"Receipt: {receipt.provenance_digest}" in body
    assert "wealth" not in body.lower()


def test_the_value_comment_shows_how_the_call_was_built() -> None:
    """D-241: the collapsed block carries the imports, the setup and the
    expression as one runnable block, so the author can reproduce the call."""
    from attest.certification.intent import INTENT_POLICY_VERSION, IntentObservation
    from attest.github.presentation import value_comments
    from attest.review.value_note import note_from

    intent = IntentObservation(
        policy_version=INTENT_POLICY_VERSION,
        path="pkg/money.py",
        changed_lines=(40, 41, 42),
        origin_line=0,
        origin_statement="",
        exception_type="",
        new_rejection=False,
        rejected_inputs=(),
        witnesses=(),
        head_runs_observed=3,
        value_mismatch=True,
        pinned_values=("Decimal('1.05')",),
        failing_assertion_line=5,
        anchored_symbols=("rate",),
        added_lines=(41,),
    )
    note = note_from(
        intent=intent,
        expression="money.rate('EUR')",
        base_kind="value",
        base_detail="Decimal('1.05')",
        head_kind="value",
        head_detail="Decimal('1.10')",
        head_runs=3,
        base_runs=3,
        reason="intent: value change confirmed, intent unknown: the base tree does not specify it",
        candidate_id="cafe1234ab",
        anchor_line=41,
        imports="import money",
        setup="money.configure(precision=2)",
    )
    assert note is not None

    (comment,) = value_comments([note], {"pkg/money.py": {41}})

    body = str(comment["body"])
    built = "```python\nimport money\n\nmoney.configure(precision=2)\n\nmoney.rate('EUR')\n```"
    assert built in body
