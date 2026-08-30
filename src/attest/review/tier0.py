"""Tier-0 static corroboration: cheap deterministic signals near the anchor.

Runs available linters over changed files and collects diagnostics whose line
overlaps a finding's anchor (+/- slack). Signals are corroboration only — they
feed the T channel's capped LR; absence of tooling just means no signal.

This module also hosts the identifier-existence signal, which is neither a
channel nor a gate: it buys no evidence, multiplies no wealth, and discards
nothing. It reports which symbols a finding names that the anchored file does
not contain, and callers record that observation without acting on it.
"""

from __future__ import annotations

import ast
import builtins
import json
import keyword
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from attest.review.schema import Finding

ANCHOR_SLACK = 2


@dataclass
class Tier0Signal:
    tool: str
    file: str
    line: int
    message: str


def run_ruff(repo: Path, files: list[str]) -> list[Tier0Signal]:
    exe = shutil.which("ruff")
    py_files = [f for f in files if f.endswith(".py") and (repo / f).is_file()]
    if not exe or not py_files:
        return []
    proc = subprocess.run(
        [exe, "check", "--output-format", "json", "--exit-zero", *py_files],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo,
    )
    try:
        diags = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for d in diags:
        try:
            out.append(
                Tier0Signal(
                    tool="ruff",
                    file=str(Path(d["filename"]).as_posix()),
                    line=int(d["location"]["row"]),
                    message=f"{d.get('code', '?')}: {d.get('message', '')}",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def collect_signals(repo: Path, files: list[str], commands: list[str]) -> list[Tier0Signal]:
    signals: list[Tier0Signal] = []
    if "ruff" in commands:
        signals.extend(run_ruff(repo, files))
    return signals


def signals_near(signals: list[Tier0Signal], file: str, line: int) -> list[Tier0Signal]:
    """Signals overlapping the anchor. Path match requires a component
    boundary: tests/utils.py must NOT corroborate utils.py."""
    norm = file.replace("\\", "/")
    out = []
    for s in signals:
        sf = s.file.replace("\\", "/")
        if (sf == norm or sf.endswith("/" + norm)) and abs(s.line - line) <= ANCHOR_SLACK:
            out.append(s)
    return out


# --- identifier-existence signal -------------------------------------------
#
# THIS IS A SIGNAL COLLECTOR, NOT A GATE. It vetoes nothing, buys no evidence,
# and multiplies no wealth. Callers record what it returns; they must not drop
# a finding on the strength of it.
#
# Promoting it to a veto is an OWNER DECISION and requires measured
# false-veto-rate data first, because a false veto silently destroys a TRUE
# finding — the tool being wrong while claiming to be careful, which is the
# worst failure this project has. Two facts keep it unpriced for now:
#   - hallucinated symbols are already stopped downstream for free: a
#     reproduction test naming a symbol that exists nowhere fails on HEAD with
#     a symbol-absent signature on head, which the classifier excludes and so can never
#     buy V evidence;
#   - resolution consults ONLY the anchored file, so a correct reference to a
#     helper defined elsewhere looks identical to an invented one.
# So the check buys cost savings, not safety, against a novel silent-recall
# risk. Measure first.
#
# The dominant hallucination in model-written code review is a reference to a
# symbol that does not exist. Anchor validation cannot catch it: a finding can
# sit squarely inside a diff hunk and still invent the function it accuses.
# The extraction below is therefore narrow, the filtering generous, and every
# failure mode returns "nothing unresolved".

_MIN_IDENTIFIER_LEN = 3

# Only three shapes count as a code reference. Prose that merely happens to
# contain an English word never qualifies.
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
# no \s* before the paren: `frobnicate(` is a call, `called (see below)` is not
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\(")
_DOTTED_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# a dotted token ending in one of these names a FILE, not an attribute
_FILE_SUFFIX_TEXT = """
    c cfg cpp css csv go h hpp html ini java js json jsx lock log md pyi py rb
    rs rst sh sql toml ts tsx txt xml yaml yml
    """
_FILE_SUFFIXES = frozenset(_FILE_SUFFIX_TEXT.split())

# English that survives the shapes above (mostly via backticks). Deliberately
# over-inclusive: every word here is a hallucination we agree to let through
# rather than a true finding we risk killing.
_COMMON_WORD_TEXT = """
    above add after again against all allow allowed allows already also always and another any
    append are argument arguments around array as assert assign assigned at attribute attributes
    back bad be because been before behavior below between block body bool boolean both branch
    break bug build but by
    call callable called caller calling calls can cannot case cases catch caught cause causes
    change changed changes check checked checking checks class classes clean clear client close
    closed code column columns comment comments commit compare comparison condition
    configuration connect connection constant construct constructor contains content context
    control convert copy correct could count counter crash create created current
    data database default defaults defined definition delete deleted dependency
    description detail details dict dictionary different directly directory disable do does done
    down during
    each early edge effect either element elements else empty enable end ensure entry enum equal
    error errors even event every exact example except exception exceptions execute exists exit
    expect expected explicit expression extra
    fail failed fails failure failures false field fields file files filter final find first fix
    fixed flag float flow follow following for force form format found from full function
    functions further
    get given global goes good got greater group guard
    handle handled handler handles happen happens has have header help here high hold hook how
    however
    identifier if ignore ignored implement implementation import in include included index
    indexes info information initial initialize input inputs insert inside instance instead
    integer interface internal into invalid is issue it item items iterate iteration
    just
    keep key keys kind
    label large last later layer lead leak least leave left length less let level library
    like limit line lines list lists load loaded local lock log logic long look loop lower
    main major make makes many map match matches max maximum may mean memory merge message
    messages method methods might min minimum miss missing mode model module more most move
    multiple must
    name names need needs negative never new next no node none normal not note nothing now null
    number numbers
    object objects occur occurs of off offset on once one only open operation option options or
    order original other otherwise out output outside over overflow overwrite own
    package page parameter parameters parent parse parsed parser part particular pass passed
    path paths pattern payload per perform place point pointer position positive possible
    prevent previous print prior probably problem process produce program property provide push
    put
    queue quote
    race raise raised raises random range rather raw read reader reading real reason receive
    record recursion reduce ref reference references refers register related release remain
    remove removed rename replace report request require required requires reset resolve
    resource response rest result results retry return returned returns reuse revert review
    right root round row rows run running runs
    safe same save scenario schema scope search second section see select self send sent
    sequence serialize server service session set sets setting settings several shape share
    short should show side signal silent similar simple since single size skip slice slow small
    so some something sort source space spec special specific split stack start state statement
    status step still stop storage store stored string strings struct structure sub submit
    subset such support sure switch symbol syntax system
    table tag take taken target task team tell temp template term test tests text than that the
    their them then there these they thing this those though thread three through throw thus
    time timeout times to token tokens too tool top total trace track transaction tree trigger
    true truncate try turn two type types typical
    unable under unexpected unique unit unless unlike until up update updated upper usage use
    used user users uses using usually
    valid validate validation value values variable verify version very via view visit
    wait want warning was way well were what when where whether which while who whole why will
    window with within without word work works would wrap write writer writing written wrong
    yield
    zero
    """
_COMMON_WORDS = frozenset(_COMMON_WORD_TEXT.split())

_BUILTIN_NAMES = frozenset(dir(builtins))


def _ident_candidates(text: str) -> list[str]:
    """Code-shaped tokens in prose, split into the segments worth resolving.

    `foo.bar()` yields both `foo` (the base name) and `bar` (the attribute),
    because either half can be the invented one.
    """
    raw: list[str] = []
    for span in _BACKTICK_RE.findall(text):
        raw.extend(_TOKEN_RE.findall(span))
    raw.extend(_CALL_RE.findall(text))
    raw.extend(_DOTTED_RE.findall(text))

    segments: list[str] = []
    for token in raw:
        parts = token.split(".")
        if len(parts) > 1 and parts[-1].lower() in _FILE_SUFFIXES:
            continue  # a path like app.py names no symbol
        segments.append(parts[0])
        if len(parts) > 1:
            segments.append(parts[-1])
    return segments


def _ident_is_noise(name: str) -> bool:
    """True for anything we refuse to hold a finding accountable for."""
    return (
        len(name) < _MIN_IDENTIFIER_LEN
        or name.startswith("__")
        or name in _BUILTIN_NAMES
        or keyword.iskeyword(name)
        or keyword.issoftkeyword(name)
        or name.lower() in _COMMON_WORDS
    )


def _ident_defined_names(tree: ast.Module) -> set[str]:
    """Every name the file binds or mentions: definitions, targets, imports,
    arguments, and any attribute accessed anywhere."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg | ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.update(node.name.split("."))
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            names.update(node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.update(node.module.split("."))
    return names


def unresolved_identifiers(repo: Path, finding: Finding) -> list[str]:
    """Code-shaped names in the finding's prose that the anchored file does not
    contain — in its AST or anywhere in its raw text.

    An OBSERVATION, not a verdict: a non-empty result is recorded, never acted
    on. See the section comment above before wiring it into any decision.

    Zero cost: no model call, no process, no network. Fails OPEN — a file that
    cannot be read or parsed yields nothing, because infrastructure trouble must
    never be allowed to silence a true finding.
    """
    try:
        source = (repo / finding.file).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, ValueError, SyntaxError, RecursionError):
        return []

    # Belt and braces, and the two halves do different jobs. The AST pass is
    # the structural one — parsing is what makes a non-Python or broken file
    # fail open above, and it states the resolution contract explicitly. Every
    # name it binds also appears literally in the source, so it is the raw-text
    # pass that actually rescues a name living only in a docstring, a comment,
    # or a string literal.
    known = _ident_defined_names(tree)
    mentioned = set(_WORD_RE.findall(source))

    unresolved: list[str] = []
    prose = f"{finding.claim}\n{finding.failure_scenario}"
    for name in _ident_candidates(prose):
        if _ident_is_noise(name) or name in known or name in mentioned:
            continue
        if name not in unresolved:
            unresolved.append(name)
    return unresolved
