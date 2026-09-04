"""D-133: the green level as an author-visible channel (owner decision 4 of 2026-09-05).

Green says something *structurally so*; it never claims a defect. Three rules
make that safe to put in front of an author:

  * the claim line states **only coordinates and the measure**, and is
    deterministic -- the model's paragraph is a separate, labelled paragraph and
    can be dropped without changing what is claimed;
  * a model sentence that names **no coordinate** is refused, exactly as a hedge
    is. D-130's adjudicator was a denylist, which stops a hedge and does not stop
    a fluent sentence about nothing;
  * at most **two** green notes reach one pull request, and they are rendered in
    their own section, marked `structural`, never mixed with the red findings.
"""

from __future__ import annotations

from attest.github.presentation import (
    MAX_STRUCTURAL_COMMENTS,
    STRUCTURAL_HEADING,
    STRUCTURAL_MARKER_PREFIX,
    STRUCTURAL_PREFIX,
    render_complete,
    structural_comments,
)
from attest.review.structural import (
    describe,
    evidence_sentence,
    find_duplicate_implementations,
    functions_of,
    structural_note,
)

ORIGINAL = '''
def summarise_orders(rows, floor):
    total = 0
    seen = set()
    for row in rows:
        if row.amount < floor:
            continue
        seen.add(row.customer_id)
        total += row.amount * row.quantity
    average = total / max(len(seen), 1)
    return {"total": total, "customers": len(seen), "average": average}
'''
RENAMED_COPY = '''
def tally_invoices(records, minimum):
    running = 0
    people = set()
    for record in records:
        if record.amount < minimum:
            continue
        people.add(record.customer_id)
        running += record.amount * record.quantity
    mean = running / max(len(people), 1)
    return {"total": running, "customers": len(people), "average": mean}
'''


def _findings():
    units = [
        unit
        for path, source in (("billing/orders.py", ORIGINAL), ("billing/invoices.py", RENAMED_COPY))
        for unit in functions_of(path, source)
    ]
    return find_duplicate_implementations(units, changed_files={"billing/invoices.py"})


def test_a_fluent_sentence_that_names_no_coordinate_is_refused() -> None:
    """The denylist's blind spot, closed: no hedge, no coordinate, no place to
    look. Green's whole claim is that a reader can go and see it."""
    finding = _findings()[0]

    nowhere, refusal = describe(
        finding,
        say=lambda _evidence: (
            "These two functions do exactly the same work, so one of them is dead weight "
            "and should be deleted."
        ),
    )

    assert refusal is not None and "coordinate" in refusal
    assert nowhere == evidence_sentence(finding)


def test_a_sentence_naming_one_coordinate_is_kept() -> None:
    """The false-positive control: naming either function or either file is
    enough, and the check is not a second hedge rule."""
    finding = _findings()[0]

    kept, refusal = describe(
        finding,
        say=lambda _evidence: (
            "`tally_invoices` is `summarise_orders` with the names changed. Delete it and "
            "call the original."
        ),
    )

    assert refusal is None
    assert kept.startswith(evidence_sentence(finding))


def test_the_note_keeps_the_claim_and_the_advice_apart() -> None:
    """The claim line is the deterministic sentence and nothing else; the model's
    words are advice, in their own field, and never part of what is claimed."""
    finding = _findings()[0]

    note = structural_note(
        finding,
        say=lambda _evidence: "Delete `tally_invoices` and call `summarise_orders`.",
    )

    assert note.evidence == evidence_sentence(finding)
    assert note.advice == "Delete `tally_invoices` and call `summarise_orders`."
    assert note.refusal is None
    # nothing the model said leaked into the claim
    assert "Delete" not in note.evidence

    silent = structural_note(finding, say=lambda _evidence: "This might be a problem.")
    assert silent.evidence == evidence_sentence(finding)
    assert silent.advice == ""
    assert silent.refusal is not None


def test_at_most_two_green_notes_reach_one_pull_request() -> None:
    finding = _findings()[0]
    notes = [structural_note(finding) for _ in range(5)]

    comments = structural_comments(notes)

    assert len(comments) == MAX_STRUCTURAL_COMMENTS == 2
    for comment in comments:
        body = str(comment["body"])
        assert body.startswith(f"{STRUCTURAL_MARKER_PREFIX}billing/invoices.py:2|")
        assert STRUCTURAL_PREFIX in body
        assert comment["path"] == finding.path_a


def test_green_is_rendered_in_its_own_section_and_never_as_a_finding() -> None:
    """Partitioned: the red section says what was reproduced, the green section
    says what was measured, and the green section never uses the word the red
    one owns."""
    note = structural_note(_findings()[0])

    body = render_complete([], spend_usd=0.0, elapsed_s=1.0, structural=[note])

    assert "No finding was verified by a reproduction; abstained." in body
    red, heading, green = body.partition(STRUCTURAL_HEADING)
    assert heading and green, "the green section is missing"
    assert "no defect is claimed" in heading
    assert "Verified findings" not in green and "receipt" not in green.lower()
    assert STRUCTURAL_PREFIX in green and note.evidence in green
    # and the red section is untouched by green's presence
    assert STRUCTURAL_PREFIX not in red
