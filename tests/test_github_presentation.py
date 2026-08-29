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


def test_complete_status_names_only_surfaced_results_and_keeps_overflow_visible() -> None:
    from attest.github.presentation import render_complete

    first = _result(claim="Surface one.", wealth=30.0)
    overflow = _result(claim="Surface two.", wealth=15.0)
    drawer = _result(
        claim="Drawer claim.",
        file="secret.py",
        line=99,
        scenario="Drawer scenario.",
        plan="Drawer plan.",
        wealth=2.0,
        decision=None,
    )
    discarded = _result(
        claim="Discarded claim.",
        file="discarded.py",
        line=101,
        scenario="Discarded scenario.",
        plan="Discarded plan.",
        wealth=0.1,
        decision=0,
    )

    complete = render_complete([drawer, overflow, discarded, first], 0.0125, 3.2)

    assert "Surface one." in complete
    assert "Surface two." in complete
    assert "Drawer claim." not in complete
    assert "secret.py" not in complete
    assert "99" not in complete
    assert "Drawer scenario." not in complete
    assert "Drawer plan." not in complete
    assert "Discarded claim." not in complete
    assert "$0.0125" in complete
    assert "3.2s" in complete


def test_inline_comments_reject_non_surfaced_results_and_keep_right_anchors() -> None:
    from attest.github.presentation import inline_comments

    drawer = _result(decision=None)
    with pytest.raises(ValueError, match="surfaced"):
        inline_comments([drawer])

    comments = inline_comments(
        [
            _result(claim="Third.", wealth=10.0, file="c.py", line=3),
            _result(claim="First.", wealth=30.0, file="a.py", line=1),
            _result(claim="Second.", wealth=20.0, file="b.py", line=2),
            _result(claim="Fourth.", wealth=5.0, file="d.py", line=4),
        ]
    )

    assert [comment["path"] for comment in comments] == ["a.py", "b.py", "c.py"]
    assert [comment["line"] for comment in comments] == [1, 2, 3]
    assert all(comment["side"] == "RIGHT" for comment in comments)
    assert "First." in str(comments[0]["body"])
    assert "A request omits its payload." in str(comments[0]["body"])
    assert "Call serialize with None." in str(comments[0]["body"])
    assert "wealth 30.0" in str(comments[0]["body"])
    assert "V x20.00 (reproduced)" in str(comments[0]["body"])
    assert "Finding ID: fdc3624e36" in str(comments[0]["body"])
