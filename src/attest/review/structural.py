"""The green level, v0: repeated implementation, decided by an algorithm (D-130).

Mainline §1.1 gives green one job: state something **structurally so**, with at
least two concrete coordinates, computed without a model. This module does one
class of that and nothing else -- *the same implementation appears in two or more
places* -- and it is the first level built on the rule the mainline states:

    the LLM thinks; an algorithm decides whether it may speak.

Here the algorithm decides twice. It decides **whether there is a finding**: two
function bodies normalise to token sequences whose similarity clears a fixed
threshold, both are large enough to be worth naming, and at least one of them is
in a file this change touched. And it decides **whether the sentence may be
said**: any prose -- the model's included -- that carries a hedge instead of a
coordinate is refused, and the deterministic sentence is published in its place.
A model is never asked whether the finding is real; it is asked, once and only
after the evidence already holds, to say it in a sentence a person wants to read
and to propose a fix.

Normalisation erases identifiers and constant values but keeps attribute and
callee names, so a renamed copy matches and two functions that merely share a
shape do not. Docstrings are not read: a copied docstring is not a copied
implementation. Test modules are excluded -- duplicated test bodies are a fact of
life and not a claim worth making.

Pure and bounded: file reads and ``ast``, a cap on files, on bytes and on the
comparisons any one run may make. No execution, no network, no model call in the
detection path at all.
"""

from __future__ import annotations

import ast
import hashlib
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath

from attest.review.output_contract import banned_phrase

# v2 (2026-09-08): a bare call keeps its callee name. v1's docstring said it
# did and the code did not -- only *attribute* callees survived normalisation --
# so `charge(a, b, i)` and `refund(a, b, i)` normalised identically and two
# bodies doing opposite things measured 1.000.
STRUCTURAL_POLICY_VERSION = "attest.structural.duplicate-implementation.v2"
CATEGORY = "structural"

# D-133: the one prompt the level ever uses, held here so the review path and the
# offline validation ask the model the same question. It is deliberately silent
# about the wording rule: the adjudicator's job is to hold against a model that
# was not told, and a prompt that begs the answer measures nothing.
WORDING_SYSTEM = (
    "You are reviewing a colleague's pull request. You will be given one finding "
    "that a static analysis already established. Write the finding for the author "
    "in plain language, in at most three sentences, and propose a concrete fix."
)
WORDING_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}, "fix": {"type": "string"}},
    "required": ["sentence", "fix"],
    "additionalProperties": False,
}
WORDING_MAX_TOKENS = 500

MIN_TOKENS = 40  # a body smaller than this is not worth two coordinates
MIN_STATEMENTS = 4
SIMILARITY_THRESHOLD = 0.92
LENGTH_TOLERANCE = 0.15  # only compare bodies of comparable size
MAX_FILES = 5_000
MAX_FILE_BYTES = 1_000_000
MAX_FUNCTIONS = 20_000
MAX_COMPARISONS = 2_000_000
MAX_PAIRS_REPORTED = 50

SKIPPED_DIRS = frozenset(
    {
        ".git",
        ".attest",
        ".attest-repro",
        # an agent scratch directory: it holds stale copies of the repository
        # itself, and every copy is a "duplicate" of everything in it
        ".claude",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        "site-packages",
    }
)
TEST_DIRS = frozenset({"tests", "test", "testing"})

# Coordinate-free hedging. A green finding either names where and how much, or it
# is not said. These are refused wherever they appear in the published sentence.
# D-133's original list, kept as the record of what green refused before the
# contract existed. `inadmissible_phrase` reads the contract's list (D-142); this
# one is a superset check in the tests, never a second policy.
LEGACY_BANNED_PHRASES = (
    "may ",
    "might ",
    "possibly",
    "probably",
    "perhaps",
    "seems",
    "appears to",
    "consider ",
    "you should probably",
    "could be",
    "potentially",
    "it is recommended",
    "we recommend",
    "likely ",
    "可能",
    "似乎",
    "建议重构",
    "或许",
    "大概",
)


@dataclass(frozen=True)
class FunctionUnit:
    """One function body of one file, reduced to what a clone check compares."""

    path: str
    name: str
    line: int
    end_line: int
    statements: int
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateImplementation:
    """Two coordinates and the measure that binds them. Nothing else is claimed."""

    policy_version: str
    category: str
    path_a: str
    name_a: str
    line_a: int
    end_line_a: int
    path_b: str
    name_b: str
    line_b: int
    end_line_b: int
    similarity: float  # rounded to three places; deterministic
    tokens_a: int
    tokens_b: int
    changed_side: str  # "a", "b" or "both": which coordinate this change touched


def is_test_path(relative: Path) -> bool:
    name = relative.name
    return (
        name == "conftest.py"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or any(part in TEST_DIRS for part in relative.parts[:-1])
    )


def normalize(node: ast.AST) -> list[str]:
    """The token sequence a clone check compares.

    Identifiers and constant values are erased -- a renamed copy is still a copy
    -- while attribute names and callee names are kept, because two functions
    that call different things are not the same implementation. A callee is kept
    whichever way it is written: `obj.charge(...)` as `ATTR:charge` and
    `charge(...)` as `CALLEE:charge`. Everything the call *passes* is normalised
    as usual, so renaming the arguments still leaves a copy a copy. Docstrings
    are dropped before the walk.
    """
    tokens: list[str] = []

    def visit(current: ast.AST) -> None:
        if (
            isinstance(current, ast.Expr)
            and isinstance(current.value, ast.Constant)
            and isinstance(current.value.value, str)
        ):
            return  # a bare string statement is a docstring or a comment
        if isinstance(current, ast.Call):
            tokens.append("Call")
            # the callee is what the body *does*; its arguments are not
            if isinstance(current.func, ast.Name):
                tokens.append(f"CALLEE:{current.func.id}")
            else:
                visit(current.func)
            for argument in current.args:
                visit(argument)
            for keyword in current.keywords:
                visit(keyword)
            return
        if isinstance(current, ast.Name):
            tokens.append("NAME")
            return
        if isinstance(current, ast.arg):
            tokens.append("ARG")
            return
        if isinstance(current, ast.Attribute):
            tokens.append(f"ATTR:{current.attr}")
            visit(current.value)
            return
        if isinstance(current, ast.Constant):
            tokens.append(f"CONST:{type(current.value).__name__}")
            return
        tokens.append(type(current).__name__)
        for child in ast.iter_child_nodes(current):
            visit(child)

    body = getattr(node, "body", [])
    statements = body[1:] if _has_docstring(node) else body
    for statement in statements:
        visit(statement)
    return tokens


def _has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", [])
    return bool(
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


def _statement_count(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, ast.stmt))


def functions_of(relative: str, source: str) -> list[FunctionUnit]:
    """Every function and method of one module, large enough to be worth naming."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    found: list[FunctionUnit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        tokens = normalize(node)
        statements = _statement_count(node) - 1  # the def itself is not a statement of it
        if len(tokens) < MIN_TOKENS or statements < MIN_STATEMENTS:
            continue
        found.append(
            FunctionUnit(
                path=relative,
                name=node.name,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                statements=statements,
                tokens=tuple(tokens),
            )
        )
    return found


def collect(root: Path, *, include_tests: bool = False) -> list[FunctionUnit]:
    """Every comparable function under ``root``, in a deterministic order."""
    units: list[FunctionUnit] = []
    files = 0
    base = root.resolve()
    for current, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIPPED_DIRS)
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = Path(current) / filename
            try:
                relative = path.relative_to(base)
            except ValueError:
                continue
            if not include_tests and is_test_path(relative):
                continue
            files += 1
            if files > MAX_FILES:
                return units
            try:
                if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
                    continue
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            units.extend(functions_of(relative.as_posix(), source))
            if len(units) > MAX_FUNCTIONS:
                return units
    return units


def similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """The measure the finding carries: the token-sequence ratio, to three places.
    Deterministic and symmetric -- `SequenceMatcher` with autojunk disabled, so a
    common token cannot be dropped because a body happens to be long."""
    matcher = SequenceMatcher(None, list(left), list(right), autojunk=False)
    return round(matcher.ratio(), 3)


def find_duplicate_implementations(
    units: Iterable[FunctionUnit],
    *,
    changed_files: Iterable[str] = (),
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[DuplicateImplementation, ...]:
    """The findings the evidence supports, in a deterministic order.

    A pair is reported when both bodies clear the size floor, their lengths are
    within `LENGTH_TOLERANCE` of each other, their similarity clears `threshold`,
    and **at least one of the two is in a file this change touched** -- a review
    speaks about the change in front of it, not about the repository at large.
    """
    changed = {path for path in changed_files}
    ordered = sorted(units, key=lambda unit: (unit.path, unit.line, unit.name))
    findings: list[DuplicateImplementation] = []
    comparisons = 0
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if left.path == right.path and left.line == right.line:
                continue
            if changed and left.path not in changed and right.path not in changed:
                continue
            shorter, longer = sorted((len(left.tokens), len(right.tokens)))
            if longer == 0 or shorter / longer < 1.0 - LENGTH_TOLERANCE:
                continue
            comparisons += 1
            if comparisons > MAX_COMPARISONS:
                return tuple(findings[:MAX_PAIRS_REPORTED])
            ratio = similarity(left.tokens, right.tokens)
            if ratio < threshold:
                continue
            in_a, in_b = left.path in changed, right.path in changed
            findings.append(
                DuplicateImplementation(
                    policy_version=STRUCTURAL_POLICY_VERSION,
                    category=CATEGORY,
                    path_a=left.path,
                    name_a=left.name,
                    line_a=left.line,
                    end_line_a=left.end_line,
                    path_b=right.path,
                    name_b=right.name,
                    line_b=right.line,
                    end_line_b=right.end_line,
                    similarity=ratio,
                    tokens_a=len(left.tokens),
                    tokens_b=len(right.tokens),
                    changed_side="both" if in_a and in_b else ("a" if in_a else "b"),
                )
            )
    findings.sort(
        key=lambda f: (-f.similarity, -min(f.tokens_a, f.tokens_b), f.path_a, f.line_a)
    )
    return tuple(findings[:MAX_PAIRS_REPORTED])


def evidence_sentence(finding: DuplicateImplementation) -> str:
    """What the product says when no model is available, and the floor under what
    it says when one is. Every clause is a coordinate or a number."""
    return (
        f"{finding.path_a}:{finding.line_a}-{finding.end_line_a} `{finding.name_a}` and "
        f"{finding.path_b}:{finding.line_b}-{finding.end_line_b} `{finding.name_b}` normalise "
        f"to token sequences of {finding.tokens_a} and {finding.tokens_b} tokens whose "
        f"token-sequence similarity is {finding.similarity:.3f} "
        f"(threshold {SIMILARITY_THRESHOLD:.2f}), not semantic equivalence; "
        f"identifiers and literal values erased, attribute and callee names kept."
    )


def inadmissible_phrase(text: str) -> str | None:
    """The first banned phrase in ``text``, or None. This is the wording
    adjudicator: it runs on the model's sentence exactly as it runs on ours.

    D-142: the list it reads is now the **output contract's**, not this module's.
    Green's wording rule was the first instance of a rule every level owes, so it
    was generalised rather than duplicated, and this function stays as the name
    the green path already calls."""
    found = banned_phrase(text)
    return None if found is None else found[1]


def names_a_coordinate(text: str, finding: DuplicateImplementation) -> bool:
    """Does this prose name a place the reader can open -- either file, by full
    path or by base name, or either function?

    D-133: the denylist alone has a blind spot, and a real model walked into it
    only in the sense that it could have. *"These two functions do exactly the
    same work, so one of them is dead weight"* carries no banned phrase and no
    place to look. Green's entire claim is that a reader can go and see it, so
    prose that names nowhere is refused exactly as a hedge is.
    """
    return any(
        token and token in text
        for token in (
            finding.path_a,
            finding.path_b,
            PurePosixPath(finding.path_a).name,
            PurePosixPath(finding.path_b).name,
            finding.name_a,
            finding.name_b,
        )
    )


def describe(
    finding: DuplicateImplementation,
    *,
    say: Callable[[str], str] | None = None,
) -> tuple[str, str | None]:
    """(the sentence to publish, why the model's sentence was refused).

    The evidence sentence is always the first line and is never generated. A
    model, when one is supplied, is called **once** and only here -- after the
    finding already exists -- to add a readable line and a fix. Its answer is
    subject to the same wording rules as ours: a hedge is dropped, and so is
    prose that names no coordinate, with the reason recorded rather than hidden.
    """
    evidence = evidence_sentence(finding)
    if say is None:
        return evidence, None
    try:
        prose = say(evidence).strip()
    except Exception as error:  # a model failure is silence, never a hedge
        return evidence, f"the model call failed: {type(error).__name__}"
    if not prose:
        return evidence, "the model returned nothing"
    banned = inadmissible_phrase(prose)
    if banned is not None:
        return evidence, f"the model's sentence hedged ({banned!r}) instead of naming a place"
    if not names_a_coordinate(prose, finding):
        return evidence, "the model's sentence named no coordinate a reader could open"
    return f"{evidence}\n\n{prose}", None


@dataclass(frozen=True)
class StructuralNote:
    """One green note, with what is *claimed* and what is merely *advised* kept
    in separate fields (D-133).

    ``evidence`` is deterministic and states only coordinates and the measure;
    ``advice`` is the model's paragraph and may be empty. Dropping ``advice``
    never changes what the note claims -- which is the whole reason a model is
    allowed anywhere near this level.
    """

    finding: DuplicateImplementation
    evidence: str
    advice: str
    refusal: str | None


STRUCTURAL_NOTE_SCHEMA_VERSION = "attest.structural-note.v2"


def structural_fingerprint(repo: Path, finding: DuplicateImplementation) -> str:
    """What makes this note the same note as one already reported (D-160).

    The two coordinates **and the source of both spans**. A repository whose
    duplicated pair is still duplicated, unchanged, does not need to be told
    again on every pull request that touches either file; a repository where
    one of the two spans moved does, because the claim is now about different
    code. Unreadable source digests as its own absence, so a note whose spans
    cannot be read is never suppressed.
    """
    digest = hashlib.sha256()
    digest.update(f"{finding.policy_version}\n{finding.category}\n".encode())
    for path, name, start, end in (
        (finding.path_a, finding.name_a, finding.line_a, finding.end_line_a),
        (finding.path_b, finding.name_b, finding.line_b, finding.end_line_b),
    ):
        digest.update(f"{path}\n{name}\n".encode())
        try:
            lines = (repo / path).read_text(errors="replace").splitlines()
        except OSError:
            digest.update(b"<unreadable>\n")
            continue
        span = "\n".join(lines[max(0, start - 1) : end])
        digest.update(span.encode("utf-8", errors="replace") + b"\n")
    return digest.hexdigest()[:16]


def reported_fingerprints(entries: list[dict[str, object]], *, exclude_task: str = "") -> set[str]:
    """Every structural fingerprint this repository has already been told."""
    seen: set[str] = set()
    for row in entries:
        if row.get("kind") != "structural_note":
            continue
        if exclude_task and row.get("task_id") == exclude_task:
            continue
        value = row.get("fingerprint")
        if type(value) is str and value:
            seen.add(value)
    return seen


def structural_note(
    finding: DuplicateImplementation,
    *,
    say: Callable[[str], str] | None = None,
) -> StructuralNote:
    """The publishable form of one finding: claim, advice, and why advice is
    missing when it is."""
    published, refusal = describe(finding, say=say)
    evidence = evidence_sentence(finding)
    advice = published[len(evidence) :].strip() if refusal is None else ""
    return StructuralNote(finding=finding, evidence=evidence, advice=advice, refusal=refusal)
