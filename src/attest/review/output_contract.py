"""The output contract: one line per finding, and an algorithm decides (D-142).

Mainline §1 condition 7. Every author-visible line this product writes is **one
line** carrying four things and nothing else:

    <level marker>  <file:line>  <one sentence of fact>  <evidence>

and the evidence is either a link a reader can open (a receipt digest, a bundle
path, a test node) or a second coordinate the claim is about. What is banned is
everything a reviewer skips: an opening pleasantry, a restatement of the pull
request, an unlocated "may/might/consider", an evaluation of the author's taste,
and a disclaimer about the tool's own reliability.

This module is the **format adjudicator**. It calls no model, it is the
generalisation of the green level's wording rule (D-133), and it is applied to
the assembled line rather than to a fragment: a bare sentence like "this drops
the last row" carries no coordinate, but the line it is rendered into does, and
the line is what an author reads.

**Format non-conformance is not publication.** A line that fails is never
softened, never truncated into shape and never posted; the caller either
substitutes a deterministic line built from its own evidence -- which is what the
red and green channels do, so that a certified finding is never silenced by a
model's phrasing -- or it says nothing.

When everything is silent the product still owes exactly one line, and it names
how many change units it read: a silence over 1 of 13 units and a silence over 13
of 13 are different claims and a reader cannot tell them apart from a bare
"nothing found".
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

CONTRACT_VERSION = "attest.output-contract.v1"

# The level markers. Text rather than emoji: they survive every terminal, every
# GitHub surface and every `grep`, and they are the same token in the ledger as
# in the comment.
LEVEL_MARKERS: dict[str, str] = {
    "red": "[red]",
    "gate": "[gate]",
    "yellow": "[yellow]",
    "green": "[green]",
}
SILENCE_MARKER = "[silent]"
MARKERS = frozenset(LEVEL_MARKERS.values()) | {SILENCE_MARKER}

# One line means one line. The cap is generous because a green measurement
# legitimately states two coordinates and three numbers; it exists to refuse the
# paragraph, not to golf the sentence.
MAX_LINE_CHARS = 400

# `path/to/file.py:123`, the coordinate a reader can open. Deliberately strict
# about the line number: "TypeError: 3 arguments" must not read as a coordinate.
COORDINATE = re.compile(r"(?<![\w:])[\w./\\-]+\.[A-Za-z0-9_]+:\d+")
# Evidence a reader can follow that is not a coordinate.
EVIDENCE_TOKEN = re.compile(
    r"(?:receipt\s+[0-9a-f]{8,})"
    r"|(?:bundle\s+\S+)"
    r"|(?:https?://\S+)"
    r"|(?:\S+::\w+)"  # a pytest node id
    # D-218: a shadow-level note's evidence is the ledger row it was written
    # from. A drawered differential has no receipt -- that is what drawered
    # means -- so a line that ended in one would be naming something that does
    # not exist; the note's digest is a thing an operator finds by grep.
    r"|(?:note\s+[0-9a-f]{8,})",
    re.IGNORECASE,
)

# Each entry is (category, phrase). The category is what a refusal says, because
# "banned phrase" is not a reason anyone can act on.
BANNED_PHRASES: tuple[tuple[str, str], ...] = (
    # a hedge without a coordinate is the absence of a level (mainline §1.1)
    ("hedge", "may"),
    ("hedge", "maybe"),
    ("hedge", "might"),
    ("hedge", "possibly"),
    ("hedge", "probably"),
    ("hedge", "perhaps"),
    ("hedge", "seems"),
    ("hedge", "appears to"),
    ("hedge", "could be"),
    ("hedge", "potentially"),
    ("hedge", "likely"),
    ("hedge", "consider"),
    ("hedge", "we recommend"),
    ("hedge", "it is recommended"),
    ("hedge", "you should probably"),
    ("hedge", "可能"),
    ("hedge", "也许"),
    ("hedge", "或许"),
    ("hedge", "大概"),
    ("hedge", "似乎"),
    ("hedge", "建议"),
    ("hedge", "考虑"),
    # an opening pleasantry
    ("preamble", "hi"),
    ("preamble", "hello"),
    ("preamble", "thanks for"),
    ("preamble", "thank you for"),
    ("preamble", "great work"),
    ("preamble", "nice work"),
    ("preamble", "good catch"),
    ("preamble", "i took a look"),
    ("preamble", "i noticed"),
    ("preamble", "just a quick note"),
    ("preamble", "overall"),
    ("preamble", "首先"),
    ("preamble", "感谢"),
    # restating what the pull request does back to its author
    ("restatement", "this pr"),
    ("restatement", "this pull request"),
    ("restatement", "in this change"),
    ("restatement", "the changes in"),
    ("restatement", "this commit adds"),
    ("restatement", "this patch"),
    ("restatement", "本次改动"),
    # an evaluation of the author rather than a statement about the code
    ("evaluation", "elegant"),
    ("evaluation", "messy"),
    ("evaluation", "ugly"),
    ("evaluation", "poorly"),
    ("evaluation", "sloppy"),
    ("evaluation", "unfortunately"),
    ("evaluation", "code smell"),
    ("evaluation", "best practice"),
    ("evaluation", "bad practice"),
    ("evaluation", "anti-pattern"),
    # a disclaimer about the tool itself
    ("disclaimer", "i'm not sure"),
    ("disclaimer", "i am not sure"),
    ("disclaimer", "please verify"),
    ("disclaimer", "please double-check"),
    ("disclaimer", "double-check"),
    ("disclaimer", "as an ai"),
    ("disclaimer", "automatically generated"),
    ("disclaimer", "this may not be accurate"),
    ("disclaimer", "仅供参考"),
)

def _pattern(phrase: str) -> re.Pattern[str]:
    """Word boundaries for a language that has words.

    `may` must not fire inside `dismay`, so an alphabetic phrase is matched
    between non-word characters. CJK is written without spaces and every
    character is a word character to `re`, so the same assertion would make
    `建议` unmatchable inside `建议重构` -- exactly the phrase green refused
    before this list existed. Those match as plain substrings."""
    if any(character.isascii() and character.isalpha() for character in phrase):
        return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    return re.compile(re.escape(phrase))


_COMPILED: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (category, phrase, _pattern(phrase)) for category, phrase in BANNED_PHRASES
)


@dataclass(frozen=True)
class ContractVerdict:
    """Admitted, or refused with the reason a person can act on."""

    admitted: bool
    reason: str | None = None
    category: str | None = None

    def __bool__(self) -> bool:  # `if check(line):` reads the way it means
        return self.admitted


ADMITTED = ContractVerdict(True)


def banned_phrase(text: str) -> tuple[str, str] | None:
    """The first `(category, phrase)` this text is refused for, or None."""
    for category, phrase, pattern in _COMPILED:
        if pattern.search(text):
            return category, phrase
    return None


def has_coordinate(text: str) -> bool:
    """Does this line name a place a reader can open?"""
    return COORDINATE.search(text) is not None


def has_evidence(text: str) -> bool:
    """Beyond the first coordinate: a second coordinate, a receipt, a bundle, a
    test node or a link. A claim whose only content is a claim is not admissible
    at any level -- that is the whole architecture in one predicate."""
    return len(COORDINATE.findall(text)) >= 2 or EVIDENCE_TOKEN.search(text) is not None


def check(line: str) -> ContractVerdict:
    """Adjudicate one assembled author-visible line. No model, no exceptions."""
    if not line.strip():
        return ContractVerdict(False, "the line is empty", "empty")
    if "\n" in line.strip():
        return ContractVerdict(False, "a finding is one line and this one is not", "multiline")
    if len(line) > MAX_LINE_CHARS:
        return ContractVerdict(
            False,
            f"the line is {len(line)} characters, over the {MAX_LINE_CHARS} the contract allows",
            "length",
        )
    if not any(marker in line for marker in MARKERS):
        return ContractVerdict(False, "the line carries no level marker", "unmarked")
    if SILENCE_MARKER in line:
        return _check_silence(line)
    if not has_coordinate(line):
        return ContractVerdict(False, "the line names no file:line coordinate", "uncoordinated")
    if not has_evidence(line):
        return ContractVerdict(
            False,
            "the line carries no evidence: no receipt, bundle, test node, link or second "
            "coordinate",
            "unevidenced",
        )
    found = banned_phrase(line)
    if found is not None:
        category, phrase = found
        return ContractVerdict(False, f"{category}: {phrase!r}", category)
    return ADMITTED


# --- the refusal verdict (D-190) -------------------------------------------
# A refusal is the product saying *why it did not look*, and until D-190 it said
# so only in the ledger and inside a collapsed block. On the line an author
# reads it owes three things and no more: its own **name**, one sentence of
# **fact**, and a **link** to the evidence — the run whose artifact holds the
# ledger. Nothing else may travel: the reasons a backend gives can quote a build
# log, a traceback or a runner path, so the line carries a fixed sentence chosen
# by the name and never the reason itself.
#
# Both variable parts are bounded *before* assembly rather than after, because
# D-142 forbids truncating a line into shape: a fact that does not fit is a
# defect in the product's own copy and raises where it is written, and a link
# that does not fit is dropped whole — a truncated URL is a broken link, which
# is worse than none.
REFUSAL_FACT_LIMIT = 180
LEDGER_URL_LIMIT = 100
REFUSAL_NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")
# https only, and only the characters a URL is made of: the value arrives from
# the runner's environment, and this line is published.
_LEDGER_URL = re.compile(r"https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+\Z")


def ledger_link(url: str) -> str:
    """The evidence link a refusal line may carry, or `""` when it cannot.

    Omission is the failure mode on purpose. A link the reader cannot open, or
    one assembled from something that is not a URL, is worse on an author's
    screen than a line that simply does not have one."""
    if type(url) is not str:
        return ""
    text = url.strip()
    if not text or len(text) > LEDGER_URL_LIMIT or not _LEDGER_URL.fullmatch(text):
        return ""
    return text


# The five verdicts a silent review may reach, and nothing else. D-142 says a
# line that does not conform is not published, so this pattern has to admit
# every line `silence_line` can produce -- it did not admit D-161's
# budget-ceiling verdict, which meant the product's own adjudicator refused a
# line the product emits (found in the 2026-09-09 release-readiness acceptance).
_SILENCE_VERDICT = (
    r"(?:nothing met an adjudicator's bar"
    r"|the budget ceiling was reached; \d+ candidate\(s\) were not verified"
    r"|executor unavailable: .+?; \d+ candidate\(s\) not verified"
    r"|refused \(" + REFUSAL_NAME.pattern + r"\): .+?"
    # D-201: an ordinary verification deferral, in the same shape a refusal
    # takes. Before it, this line was bare `DEFER: ...` prose that the
    # adjudicator below refuses -- and published anyway, because nothing
    # adjudicated it.
    r"|deferred \(" + REFUSAL_NAME.pattern + r"\): .+?)"
)
_SILENCE_SHAPE = re.compile(
    "^"
    + re.escape(SILENCE_MARKER)
    + r" read \d+ of \d+ units; "
    + _SILENCE_VERDICT
    # a refusal and a deferral may point at the run whose artifact holds the
    # ledger; an ordinary silence has nothing to point at (D-190, D-201)
    + r"(?:; ledger: https://\S+)?"
    + r"; \$\d+\.\d{4}, \d+\.\d+s\.$"
)


def _check_silence(line: str) -> ContractVerdict:
    if _SILENCE_SHAPE.match(line.strip()):
        return ADMITTED
    return ContractVerdict(
        False, "the silence line does not have the contract's fixed shape", "silence_shape"
    )


def claim_line(
    level: str,
    *,
    path: str,
    line: int,
    fact: str,
    evidence: str,
    prefix: str = "",
) -> str:
    """Assemble one line in the contract's shape. Assembling does not admit it:
    the caller adjudicates the result and substitutes its own deterministic
    sentence when a model's does not pass."""
    if level not in LEVEL_MARKERS:
        raise ValueError(f"unknown level: {level!r}")
    marker = LEVEL_MARKERS[level]
    body = f"{marker} {path}:{line} — {_one_line(fact)} — {_one_line(evidence)}"
    return f"{prefix}{body}" if prefix else body


# D-161: a silence bought out by the ceiling is a different claim from a silence
# where every candidate was judged, and the reader cannot act on the first
# without knowing how many were never looked at.
BUDGET_REASON_MARKERS = ("budget", "预算")


def budget_unverified(reasons: Mapping[str, str] | None) -> int:
    """How many candidates were left unverified because the budget ran out."""
    if not reasons:
        return 0
    return sum(
        1
        for reason in reasons.values()
        if type(reason) is str
        and any(marker in reason.lower() for marker in BUDGET_REASON_MARKERS)
    )


def silence_line(
    *,
    units_read: int,
    units_planned: int,
    spend_usd: float,
    elapsed_s: float,
    unverified: int = 0,
    executor_unavailable: str = "",
    refusal: tuple[str, str] | None = None,
    deferral: tuple[str, str] | None = None,
    ledger_url: str = "",
) -> str:
    """The one line a wholly silent review owes, in a fixed shape (D-142).

    It names the units read because a silence over 1 of 13 units and a silence
    over 13 of 13 are different claims. When the budget ceiling is what stopped
    the run it says so, and how many candidates it stopped (D-161) -- a silence
    that means *nothing was wrong* and a silence that means *nobody looked* are
    not the same answer.

    A third verdict outranks both: when the **host cannot run the executor at
    all**, no candidate was judged, and `nothing met an adjudicator's bar` then
    claims a clean bill of health for code nothing looked at. The reason and the
    number of candidates it stopped are what the operator can act on, so they
    come first and the budget count is not shown -- an executor that never ran
    spent nothing on verification (D-177).

    A **refusal** outranks all three (D-190). `no docker` *is* an unavailable
    executor and a budget truncation *is* a silence, and in both cases the
    refusal's own name says more than the verdict it displaces: it tells the
    author which of the five things happened, and the link says where the
    ledger for it is. The fact is the product's own fixed sentence, chosen by
    the name -- never the backend's reason, which can quote a build log, a
    traceback or a runner path."""
    planned = units_planned or units_read
    if refusal is not None or deferral is not None:
        # a refusal outranks a deferral: `no docker` is why verification never
        # started, and the author is owed the name that says more
        word = "refused" if refusal is not None else "deferred"
        name, fact = refusal if refusal is not None else deferral  # type: ignore[misc]
        fact = _one_line(fact)
        if not REFUSAL_NAME.fullmatch(name) or not fact:
            raise ValueError(f"not a {word[:-1]} this line can carry: {name!r}")
        if len(fact) > REFUSAL_FACT_LIMIT:
            # D-142: a line is never truncated into shape, so copy that does not
            # fit fails where it is written rather than on an author's screen
            raise ValueError(
                f"{word[:-1]} {name!r} states {len(fact)} characters of fact, over the "
                f"{REFUSAL_FACT_LIMIT} one line allows"
            )
        # the link belongs to the refusal and to nothing else: an ordinary
        # silence has no evidence to point at, and adding one to every line
        # would be a second change to copy this decision did not ask for
        link = ledger_link(ledger_url)
        return (
            f"{SILENCE_MARKER} read {units_read} of {planned} units; "
            f"{word} ({name}): {fact}"
            + (f"; ledger: {link}" if link else "")
            + f"; ${spend_usd:.4f}, {elapsed_s:.1f}s."
        )
    if executor_unavailable:
        verdict = (
            f"executor unavailable: {_one_line(executor_unavailable)}; "
            f"{unverified} candidate(s) not verified"
        )
    elif unverified > 0:
        verdict = f"the budget ceiling was reached; {unverified} candidate(s) were not verified"
    else:
        verdict = "nothing met an adjudicator's bar"
    return (
        f"{SILENCE_MARKER} read {units_read} of {planned} units; "
        f"{verdict}; ${spend_usd:.4f}, {elapsed_s:.1f}s."
    )


# --- the action clause (D-178) ---------------------------------------------
# A finding an author cannot act on costs them the same attention as one they
# can, so every author-visible comment owes **one** line saying what to do next,
# in that level's own currency:
#
#   red    reproduce it: the command, then the bundle to verify offline
#   gate   the reachable path and the input that triggers it
#   yellow the affected caller's coordinate, and the two things that close it
#          -- add a test that names it, or change the caller
#   green  the two coordinates and where the one surviving copy should live
#
# The clause is adjudicated, not requested: `check_comment` refuses a comment
# without one, exactly as `check` refuses a line without evidence. It is never
# a model's sentence -- every clause is assembled from coordinates the level
# already holds.
#
# **What that does and does not buy.** A *certified* finding is never gated on
# this at all: `inline_comments` appends red's clause and does not adjudicate,
# so no wording can suppress a receipt. The green and yellow builders *are*
# gated, so for them the honest statement is narrower -- the only text the
# adjudicator reads is text the product wrote, because `collapsed` neutralises
# the block delimiters a model would need to reach it.
ACTION_PREFIX = "Action:"

# What makes an action clause actionable: something to run, open or change.
_ACTIONABLE = re.compile(
    r"(?:`[^`]+`)"  # a command or a symbol to run or look for
    r"|(?:[\w./\\-]+\.[A-Za-z0-9_]+:\d+)"  # a coordinate
    r"|(?:[\w./\\-]+/[\w./\\-]+)"  # a path
)


# The collapsed block is a model's free text and is explicitly **not part of the
# claim**. It is therefore not part of the adjudication either: a paragraph that
# happened to begin a line with "Action:" would otherwise make two clauses out of
# one and drop the whole note for a word the model chose.
_COLLAPSED_BLOCK = re.compile(r"<details>.*?</details>", re.DOTALL | re.IGNORECASE)


def action_clause(text: str) -> str | None:
    """The comment's action clause, or None. Exactly one line may carry it: two
    next steps is no next step. Lines inside a collapsed block do not count."""
    claimed = _COLLAPSED_BLOCK.sub("", text)
    found = [
        line.strip()
        for line in claimed.splitlines()
        if line.strip().startswith(ACTION_PREFIX)
    ]
    return found[0] if len(found) == 1 else None


def has_action(text: str) -> bool:
    """Does this comment tell the reader something concrete to do?"""
    clause = action_clause(text)
    if clause is None:
        return False
    body = clause[len(ACTION_PREFIX) :].strip()
    return bool(body) and _ACTIONABLE.search(body) is not None


def claim_of(body: str) -> str | None:
    """A comment's claim line: the first line that is neither blank nor one of
    the HTML markers the delivery journal writes to identify it."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        return stripped
    return None


def check_comment(body: str) -> ContractVerdict:
    """Adjudicate one whole author-visible comment (D-142, extended by D-178).

    Two conditions, both decided without a model: its **claim line** conforms to
    the one-line contract, and it carries exactly one **action clause**. A
    comment that fails either is not published -- the caller substitutes a
    deterministic comment or says nothing."""
    claim = claim_of(body)
    if claim is None:
        return ContractVerdict(False, "the comment carries no claim line", "empty")
    verdict = check(claim)
    if not verdict:
        return verdict
    if action_clause(body) is None:
        return ContractVerdict(
            False,
            f"the comment carries no single {ACTION_PREFIX!r} line saying what to do next",
            "actionless",
        )
    if not has_action(body):
        return ContractVerdict(
            False,
            "the action clause names nothing to run, open or change",
            "actionless",
        )
    return ADMITTED


# --- the whole summary body (D-204) ------------------------------------------
#
# Condition 7 says an author-visible line is *one line per finding … and nothing
# else. No preamble.* Until D-204 the summary body opened with `Review
# complete.` and, when nothing certified, a second line saying so -- both
# preamble, both published on every review, and **never adjudicated**: `check`
# was applied to the lines inside the body and never to the body itself. The
# census of 2026-09-13 found the header on every review that published a note.
#
# A summary body is now: contract lines, the section headings the product owns,
# collapsed blocks, and one spend footer. Nothing else, and the adjudicator
# below is what makes that true rather than intended.

SUMMARY_HEADINGS = frozenset(
    {
        "Verified findings (each backed by a reproduction receipt):",
        "Structural observations — measured, not reproduced; no defect is claimed:",
        "Impact scope — counted over the call graph; no defect is claimed and no "
        "coverage was measured:",
    }
)
SPEND_FOOTER = re.compile(r"^Spend \$\d+\.\d{4}; \d+\.\d+s\.$")
_STATUS_MARKER_LINE = re.compile(r"^<!--\s*attest:[a-z:]*\s*-->$", re.IGNORECASE)
# a line inside a collapsed block is the block's business, not the contract's
_BLOCK_OPEN = re.compile(r"<\s*details\b", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(r"</\s*details\s*>", re.IGNORECASE)


def check_summary(body: str) -> ContractVerdict:
    """Adjudicate a whole summary body, not only the lines inside it.

    Every non-blank line outside a collapsed block must be a contract line, a
    heading the product owns, the spend footer, or the status marker. A line
    that is none of those is **preamble** and the body is refused -- which is
    what makes condition 7 a property of the surface rather than of the lines
    that happen to be checked.
    """
    if not body.strip():
        return ContractVerdict(False, "the summary body is empty", "empty")
    depth = 0
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        opens = len(_BLOCK_OPEN.findall(line))
        closes = len(_BLOCK_CLOSE.findall(line))
        if depth > 0 or opens:
            depth = max(0, depth + opens - closes)
            continue
        depth = max(0, depth - closes)
        if _STATUS_MARKER_LINE.match(line) or line in SUMMARY_HEADINGS:
            continue
        if SPEND_FOOTER.match(line):
            continue
        candidate = line[2:].strip() if line.startswith("- ") else line
        if check(candidate):
            continue
        return ContractVerdict(
            False,
            f"the summary body carries a line the contract does not admit: {line[:80]!r}",
            "summary_preamble",
        )
    return ADMITTED


COLLAPSED_SUMMARY = "Suggested fix — written by a model, not part of the claim"


# The block's own delimiters, neutralised wherever they appear in a body. The
# block is the only thing that marks model prose as *not part of the claim*, so
# text that could close it early would render as product copy and would be read
# by `action_clause` as if the product had written it (independent review of
# 2026-09-09, finding 2). `\u200b` is a zero-width space: the tag stops being a
# tag and the words still read.
_BLOCK_DELIMITERS = re.compile(r"</?\s*(details|summary)\b", re.IGNORECASE)


def _neutralise_delimiters(body: str) -> str:
    return _BLOCK_DELIMITERS.sub(lambda m: m.group(0).replace("<", "<\u200b", 1), body)


def collapsed(body: str, *, summary: str = COLLAPSED_SUMMARY, trusted: bool = False) -> str:
    """The model's fix suggestion, collapsed by default.

    `<details>` renders closed on every GitHub surface, so advice costs the
    reader one line of screen and is there when it is wanted. Nothing inside is
    part of what the product claims, and dropping the whole block changes no
    claim -- which is the reason a model is allowed near the output at all.

    **The body's own `<details>`/`<summary>` tags are neutralised on the way in**,
    so nothing a model writes can close the block early and reappear outside it
    as product copy. `trusted=True` is the opt-out, for a body this product built
    itself and whose nested block is meant to be one -- today that is the
    evidence renderer's own "Full logs" section, and nothing else. The default is
    the safe direction on purpose: a level added later that forgets the flag
    renders a tag as text, which is ugly; one that forgets to neutralise
    publishes a model's markup as its own."""
    inner = body.strip() if trusted else _neutralise_delimiters(body.strip())
    return f"<details>\n<summary>{summary}</summary>\n\n{inner}\n\n</details>"


def _one_line(value: str) -> str:
    return " ".join(value.split())
