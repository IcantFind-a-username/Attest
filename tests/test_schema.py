from attest.review.diffs import parse_diff
from attest.review.schema import validate_finding

DIFF = parse_diff(
    """\
--- a/app.py
+++ b/app.py
@@ -5,3 +5,4 @@
 context
+risky = 1 / n
 context
 context
"""
)


def _raw(**overrides: object) -> dict:
    base: dict = {
        "claim": "Division by zero when n is 0.",
        "anchor": {"file": "app.py", "line": 6},
        "failure_scenario": "n == 0 at startup",
        "falsification_plan": "call f(0) and observe",
    }
    base.update(overrides)
    return base


def test_valid_finding() -> None:
    f, reason = validate_finding(_raw(), DIFF)
    assert f is not None and reason == ""
    assert f.file == "app.py" and f.line == 6
    assert len(f.finding_id) == 10


def test_missing_piece_voids() -> None:
    for key in ("claim", "anchor", "failure_scenario", "falsification_plan"):
        f, reason = validate_finding(_raw(**{key: ""}), DIFF)
        assert f is None
        assert key in reason


def test_three_sentence_claim_voids() -> None:
    f, reason = validate_finding(_raw(claim="One. Two. Three sentences here."), DIFF)
    assert f is None
    assert "2 sentences" in reason


def test_anchor_outside_hunk_voids() -> None:
    f, reason = validate_finding(_raw(anchor={"file": "app.py", "line": 99}), DIFF)
    assert f is None
    assert "not inside" in reason


def test_anchor_wrong_file_voids() -> None:
    f, _ = validate_finding(_raw(anchor={"file": "nope.py", "line": 6}), DIFF)
    assert f is None


def test_malformed_anchor_voids() -> None:
    f, _ = validate_finding(_raw(anchor={"file": "app.py"}), DIFF)
    assert f is None
    f, _ = validate_finding(_raw(anchor={"file": "app.py", "line": "x"}), DIFF)
    assert f is None


def test_anchor_path_normalized() -> None:
    f, _ = validate_finding(_raw(anchor={"file": "./app.py", "line": 6}), DIFF)
    assert f is not None and f.file == "app.py"
