"""D-130, the green level v0: an algorithm finds the repetition and decides the wording."""

from __future__ import annotations

from pathlib import Path

from attest.review.structural import (
    CATEGORY,
    SIMILARITY_THRESHOLD,
    STRUCTURAL_POLICY_VERSION,
    collect,
    describe,
    evidence_sentence,
    find_duplicate_implementations,
    functions_of,
    inadmissible_phrase,
    normalize,
    similarity,
)

ORIGINAL = '''
def summarise_orders(orders, cutoff):
    """Total the orders above the cutoff, per customer."""
    totals = {}
    for order in orders:
        if order.amount <= cutoff:
            continue
        if order.customer not in totals:
            totals[order.customer] = 0
        totals[order.customer] += order.amount
    ranked = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    return ranked[:10]
'''

# the same implementation, every identifier renamed, the docstring rewritten, the
# literals changed: a copy a reviewer would want named
RENAMED_COPY = '''
def tally_invoices(rows, floor):
    """A completely different sentence about invoices."""
    sums = {}
    for row in rows:
        if row.amount <= floor:
            continue
        if row.customer not in sums:
            sums[row.customer] = 0
        sums[row.customer] += row.amount
    ordered = sorted(sums.items(), key=lambda item: item[1], reverse=True)
    return ordered[:25]
'''

# same shape, different calls and attributes: not the same implementation
DIFFERENT_WORK = '''
def render_labels(items, minimum):
    """Shape-alike, but it does something else entirely."""
    labels = {}
    for item in items:
        if item.width <= minimum:
            continue
        if item.slug not in labels:
            labels[item.slug] = ""
        labels[item.slug] += item.caption
    chosen = sorted(labels.items(), key=lambda pair: pair[0], reverse=False)
    return chosen[:10]
'''

SMALL = '''
def add(a, b):
    return a + b
'''


def _units(files: dict[str, str]):
    return [unit for path, text in files.items() for unit in functions_of(path, text)]


def test_a_renamed_copy_is_found_with_both_coordinates_and_a_measure() -> None:
    """The finding is two places and a number, and nothing else."""
    units = _units({"billing/orders.py": ORIGINAL, "billing/invoices.py": RENAMED_COPY})

    findings = find_duplicate_implementations(units, changed_files={"billing/invoices.py"})

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.policy_version, finding.category) == (STRUCTURAL_POLICY_VERSION, CATEGORY)
    assert (finding.path_a, finding.name_a) == ("billing/invoices.py", "tally_invoices")
    assert (finding.path_b, finding.name_b) == ("billing/orders.py", "summarise_orders")
    assert finding.line_a > 0 and finding.line_b > 0
    assert finding.similarity >= SIMILARITY_THRESHOLD
    assert finding.changed_side == "a"
    # the published sentence carries both coordinates and the measure, verbatim
    sentence = evidence_sentence(finding)
    assert "billing/invoices.py:2-" in sentence and "billing/orders.py:2-" in sentence
    assert f"{finding.similarity:.3f}" in sentence
    assert inadmissible_phrase(sentence) is None


def test_the_same_shape_doing_different_work_is_not_a_finding() -> None:
    """Identifiers are erased; attribute and callee names are not. Two functions
    that merely rhyme structurally must not be published as a repetition."""
    units = _units({"a.py": ORIGINAL, "b.py": DIFFERENT_WORK})

    assert find_duplicate_implementations(units, changed_files={"b.py"}) == ()
    assert similarity(normalize_of(ORIGINAL), normalize_of(DIFFERENT_WORK)) < SIMILARITY_THRESHOLD


def normalize_of(source: str) -> tuple[str, ...]:
    import ast

    function = next(
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)
    )
    return tuple(normalize(function))


def test_a_finding_needs_a_changed_file_and_a_body_worth_naming() -> None:
    """A review speaks about the change in front of it, and never about two
    three-line helpers."""
    units = _units({"a.py": ORIGINAL, "b.py": RENAMED_COPY})
    assert find_duplicate_implementations(units, changed_files={"untouched.py"}) == ()

    tiny = _units({"a.py": SMALL, "b.py": SMALL.replace("add", "plus")})
    assert tiny == []  # below the size floor, so there is nothing to compare at all


def test_the_wording_adjudicator_refuses_a_hedge_wherever_it_comes_from() -> None:
    """The rule is the mainline's: the algorithm decides whether it may speak. A
    model that hedges is dropped and the deterministic sentence stands alone."""
    units = _units({"a.py": ORIGINAL, "b.py": RENAMED_COPY})
    finding = find_duplicate_implementations(units, changed_files={"b.py"})[0]

    hedged, refusal = describe(
        finding, say=lambda _evidence: "This may be duplicated; consider refactoring it."
    )
    assert refusal is not None and "hedged" in refusal
    assert hedged == evidence_sentence(finding)
    assert inadmissible_phrase(hedged) is None

    kept, refusal = describe(
        finding,
        say=lambda _evidence: (
            "`tally_invoices` is `summarise_orders` with the names changed. Delete it and "
            "call `summarise_orders(rows, floor)` from billing/invoices.py:2."
        ),
    )
    assert refusal is None and "summarise_orders(rows, floor)" in kept
    assert kept.startswith(evidence_sentence(finding))

    failed, refusal = describe(finding, say=lambda _evidence: (_ for _ in ()).throw(TimeoutError()))
    assert failed == evidence_sentence(finding)
    assert refusal is not None and "TimeoutError" in refusal


def test_no_model_is_called_before_the_evidence_holds(tmp_path: Path) -> None:
    """Detection is pure: `collect` and `find_duplicate_implementations` take no
    provider and cannot reach one. The single call is in `describe`, after."""
    calls: list[str] = []
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "orders.py").write_text(ORIGINAL, encoding="utf-8")
    (tmp_path / "pkg" / "invoices.py").write_text(RENAMED_COPY, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_copy.py").write_text(RENAMED_COPY, encoding="utf-8")

    units = collect(tmp_path)
    findings = find_duplicate_implementations(units, changed_files={"pkg/invoices.py"})

    assert calls == []
    assert {unit.path for unit in units} == {"pkg/orders.py", "pkg/invoices.py"}  # tests excluded
    assert len(findings) == 1

    describe(findings[0], say=lambda evidence: calls.append(evidence) or "Named and placed.")
    assert len(calls) == 1  # exactly once, and only after the finding existed


def test_the_detector_is_order_invariant_and_deterministic() -> None:
    files = {"a.py": ORIGINAL, "b.py": RENAMED_COPY, "c.py": DIFFERENT_WORK, "d.py": SMALL}
    units = _units(files)
    changed = {"b.py", "c.py"}

    first = find_duplicate_implementations(units, changed_files=changed)
    reversed_order = find_duplicate_implementations(list(reversed(units)), changed_files=changed)

    assert first == reversed_order
    assert first == find_duplicate_implementations(units, changed_files=changed)
