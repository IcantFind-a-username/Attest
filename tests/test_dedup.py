from attest.review.dedup import merge_findings
from attest.review.schema import Finding


def _f(claim: str, file: str = "a.py", line: int = 10, **kw: object) -> Finding:
    return Finding(
        claim=claim,
        file=file,
        line=line,
        failure_scenario=str(kw.get("failure_scenario", "boom")),
        falsification_plan=str(kw.get("falsification_plan", "check")),
    )


def test_same_defect_merges_and_counts_votes() -> None:
    a = _f("Division by zero when count is empty")
    b = _f("Division by zero if count list is empty", line=11)
    merged = merge_findings([[a], [b]])
    assert len(merged) == 1
    assert merged[0].votes == 2
    assert merged[0].sample_ids == [0, 1]


def test_far_lines_do_not_merge() -> None:
    a = _f("Division by zero when count is empty")
    b = _f("Division by zero when count is empty", line=20)
    merged = merge_findings([[a], [b]])
    assert len(merged) == 2


def test_different_claims_do_not_merge() -> None:
    a = _f("Division by zero when count is empty")
    b = _f("SQL injection through unsanitized user input parameter")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 2


def test_repeat_mention_same_sample_not_double_voted() -> None:
    a1 = _f("Division by zero when count is empty")
    a2 = _f("Division by zero when the count is empty", line=11)
    merged = merge_findings([[a1, a2]])
    assert len(merged) == 1
    assert merged[0].votes == 1


def test_merge_keeps_longer_details() -> None:
    a = _f("Null deref on missing user", failure_scenario="short")
    b = _f(
        "Null deref on a missing user",
        failure_scenario="much longer and more specific scenario",
        falsification_plan="a considerably more detailed plan",
    )
    merged = merge_findings([[a], [b]])
    assert merged[0].failure_scenario.startswith("much longer")
    assert merged[0].falsification_plan.startswith("a considerably")


def test_three_samples_three_votes() -> None:
    fs = [[_f("Buffer overflow in parse loop")] for _ in range(3)]
    merged = merge_findings(fs)
    assert merged[0].votes == 3
