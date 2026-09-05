"""The same duplicated pair is told once, not on every pull request (D-160).

Green states something structurally so: this implementation appears in two
places, here and here. That fact does not change because someone edited a third
file, so a repository whose duplicated pair is still duplicated and still
unchanged does not need to be told again, and being told again is how a level
teaches its readers to skip it.

What makes a note "the same note" is the two coordinates **and the source of
both spans**. Either side moving brings the note back, because the claim is
then about different code.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from attest.review.ci import structural_notes
from attest.review.ledger import Ledger
from attest.review.structural import (
    STRUCTURAL_NOTE_SCHEMA_VERSION,
    collect,
    find_duplicate_implementations,
    structural_fingerprint,
)

BODY = """def {name}(rows, key):
    seen = {{}}
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        bucket = seen.setdefault(value, [])
        bucket.append(row)
    ordered = sorted(seen.items())
    return [(name, len(items)) for name, items in ordered]
"""


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "one.py").write_text(BODY.format(name="group_one"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "two.py").write_text(BODY.format(name="group_two"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "the duplicate arrives")
    return tmp_path, base, git("rev-parse", "HEAD")


def _notes(repo: Path, base: str, head: str, task_id: str = ""):
    return structural_notes(
        repo=repo,
        base_sha=base,
        head_sha=head,
        provider=None,  # type: ignore[arg-type]
        budget=None,  # type: ignore[arg-type]
        task_id=task_id,
    )


def _record(repo: Path, notes, task_id: str) -> None:
    """What `run_ci` writes when a green note is published."""
    ledger = Ledger(repo)
    for note in notes:
        ledger.append(
            {
                "kind": "structural_note",
                "schema_version": STRUCTURAL_NOTE_SCHEMA_VERSION,
                "task_id": task_id,
                "policy_version": note.finding.policy_version,
                "note_id": "x",
                "fingerprint": structural_fingerprint(repo, note.finding),
                "similarity": note.finding.similarity,
                "advice_published": False,
                "refusal": None,
            }
        )


def test_the_second_review_of_an_unchanged_pair_is_silent(tmp_path: Path) -> None:
    repo, base, head = _repo(tmp_path / "dedup")

    first = _notes(repo, base, head, task_id="t1")
    assert len(first) == 1, "the fixture did not produce a duplicate"
    _record(repo, first, "t1")

    second = _notes(repo, base, head, task_id="t2")
    assert second == []


def test_a_change_to_either_span_brings_the_note_back(tmp_path: Path) -> None:
    repo, base, head = _repo(tmp_path / "changed")
    _record(repo, _notes(repo, base, head, task_id="t1"), "t1")
    assert _notes(repo, base, head, task_id="t2") == []

    text = (repo / "two.py").read_text(encoding="utf-8")
    (repo / "two.py").write_text(text.replace("ordered = sorted", "ordered = list"), "utf-8")

    assert len(_notes(repo, base, head, task_id="t3")) == 1


def test_the_run_that_wrote_the_row_is_not_silenced_by_its_own_row(tmp_path: Path) -> None:
    """A review must never suppress itself: the exclusion is by task id."""
    repo, base, head = _repo(tmp_path / "selfsame")
    notes = _notes(repo, base, head, task_id="t1")
    _record(repo, notes, "t1")

    assert len(_notes(repo, base, head, task_id="t1")) == 1


def test_the_fingerprint_covers_the_source_of_both_spans(tmp_path: Path) -> None:
    repo, _base, _head = _repo(tmp_path / "fp")
    finding = find_duplicate_implementations(
        collect(repo), changed_files={"two.py"}
    )[0]
    before = structural_fingerprint(repo, finding)

    # a change outside both spans does not change the fingerprint
    (repo / "three.py").write_text("unrelated = 1\n", encoding="utf-8")
    assert structural_fingerprint(repo, finding) == before

    # a change inside one of them does
    text = (repo / "one.py").read_text(encoding="utf-8")
    (repo / "one.py").write_text(text.replace("seen = {}", "seen = dict()"), encoding="utf-8")
    assert structural_fingerprint(repo, finding) != before


def test_a_row_written_before_fingerprints_existed_suppresses_nothing(tmp_path: Path) -> None:
    """D-149's lesson: a row records what was known when it was written."""
    repo, base, head = _repo(tmp_path / "legacy")
    Ledger(repo).append(
        {
            "kind": "structural_note",
            "schema_version": "attest.structural-note.v1",
            "task_id": "old",
            "policy_version": "attest.structural.duplicate-implementation.v1",
            "note_id": "one.py:1|two.py:1",
            "similarity": 1.0,
            "advice_published": False,
            "refusal": None,
        }
    )
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["schema_version"] == "attest.structural-note.v1"
    assert len(_notes(repo, base, head, task_id="t2")) == 1
