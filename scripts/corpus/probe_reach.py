#!/usr/bin/env python3
"""Can a derived probe reach a real project's tests at all?

D-211 measured D-206 on the held-out corpus and found it was **never chosen**:
25 probe observations, every one `source: "model"`, `source: "derived"` zero
times. A derived probe existed for 2 of 25 candidates, 5 were produced, and all
5 were screened out. That says the mechanism bought nothing; it does not say
*why*, and the two answers have opposite consequences. If the calls are there
and the screening rule discarded them, the screening rule is the work. If the
calls are not there at all, no amount of screening work matters and D-206's
route is closed on projects that look like these.

This answers the second half, for free. It calls no model, executes nothing,
opens no socket and needs no docker: `ast`, the binding index and `git diff`.

`derive_probes` refuses a call for reasons that are written down in
`attest.review.derived_probes` -- every argument must be a literal, and this
version derives module-level functions only, because a method needs a receiver
and a receiver is an object the test built. The hypothesis this tests is that
the eight SWE-bench projects' tests are fixtures, constructed objects and
`parametrize`, so a call site that is a module-level function taking only
literals is close to nonexistent.

**The product's rules are imported, never re-implemented.** The `current`
column calls `derive_probes` itself, so it is the product's own behaviour by
construction. The relaxations are counted here and **nothing under `src/` is
modified**: this is a measurement, not a change.

The relaxations are deliberately **generous** -- see `_RELAXATIONS_ARE_UPPER_BOUNDS`
below. An over-count is the safe direction for the question actually being
asked: if even a generous count of a fully relaxed rule stays in single digits,
the negative result is robust, and if it does not, the honest reading is that
the relaxation is worth building rather than that it is already proven.

    probe_reach.py corpus          # the 39 held-out cases (needs them built)
    probe_reach.py self --limit 20 # this repository, as the control
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from derived_probes import (  # noqa: E402
    _all_literal,
    _calls_at,
    _import_line,
    _is_literal,
    _parse,
    derive_probes,
    probe_sources,
)

from attest.review.binding import _UNPARSABLE  # noqa: E402
from attest.review.impact import CallSite, build_call_graph, is_test_path  # noqa: E402

CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
PLAN = ROOT / ".attest" / "corpora" / "heldout-supported-v1" / "plan.json"

# Why the ladder's numbers are ceilings and not measurements of a built rule.
#
# `current` is exact: it is `derive_probes` itself. Every other column is this
# script's own arithmetic over call sites, and each takes the permissive answer
# wherever proving the strict one would need machinery that does not exist yet:
#
#   +method       counts a method call whose receiver is a literal construction
#                 without proving, through the binding layer, that the call
#                 resolves to *this* class's method. Attribute-call binding is
#                 the thing D-206 avoided; assuming it succeeds is the ceiling.
#   +local        requires the assignment to be in the same function and its
#                 right-hand side to be a literal, but does not check that the
#                 name is not rebound between the assignment and the call.
#   +parametrize  requires every value supplied for the parameter to be a
#                 literal, but does not check indirect parametrisation or
#                 fixtures that shadow the argname.
#
# So a case counted derivable under a relaxation is a case that *might* become
# derivable if that relaxation were built correctly -- never one that is.
_RELAXATIONS_ARE_UPPER_BOUNDS = True

RULES = ("current", "+method", "+local", "+parametrize", "all relaxations")

# The refusal histogram's categories, in the order the report prints them.
R_FIXTURE = "non-literal argument: fixture parameter"
R_LOCAL = "non-literal argument: local variable"
R_CONSTRUCTED = "non-literal argument: constructed object"
R_OTHER_EXPR = "non-literal argument: other expression"
R_METHOD = "method (not derived in this version)"
R_NOT_A_FUNCTION = "anchor is not inside any def"
R_NESTED = "anchor is in a nested function"
R_RELATIVE = "relative import in the test"
R_UNRESOLVED = "binding layer resolves nothing"
R_NO_SITES = "no call site in the test tree"
R_AMBIGUOUS = "definition is absent or ambiguous"
R_UNREADABLE = "anchored file unreadable"
R_DERIVABLE = "derivable now"

ORDER = (
    R_FIXTURE,
    R_LOCAL,
    R_CONSTRUCTED,
    R_OTHER_EXPR,
    R_METHOD,
    R_NESTED,
    R_NOT_A_FUNCTION,
    R_RELATIVE,
    R_UNRESOLVED,
    R_NO_SITES,
    R_AMBIGUOUS,
    R_UNREADABLE,
    R_DERIVABLE,
)


@dataclass
class Anchor:
    """One changed definition, which is what a candidate anchors on."""

    path: str
    line: int
    function: str | None
    kind: str  # "module" | "method" | "nested" | "none"


@dataclass
class CaseReach:
    case: str
    anchors: int = 0
    sites: int = 0
    reasons: Counter = field(default_factory=Counter)
    # rule -> number of call sites that rule would admit
    admitted: Counter = field(default_factory=Counter)
    # rule -> number of *anchors* with at least one admitted call site. A probe
    # is per candidate, so one admitted site is all an anchor needs; counting
    # sites alone would let one heavily-tested function stand in for a corpus.
    anchors_admitted: Counter = field(default_factory=Counter)
    derived_now: int = 0
    error: str = ""

    def derivable_under(self, rule: str) -> bool:
        return self.admitted.get(rule, 0) > 0


# --- anchors: what the diff changed -------------------------------------------


def changed_lines(repo: Path, base: str, head: str) -> dict[str, list[int]]:
    """Head-side changed line numbers per `.py` file, from `git diff -U0`."""
    done = subprocess.run(
        ["git", "-C", str(repo), "diff", "-U0", f"{base}..{head}", "--", "*.py"],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        return {}
    out: dict[str, list[int]] = {}
    path = ""
    for line in done.stdout.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@") and path and path != "/dev/null":
            # @@ -a,b +c,d @@
            try:
                new = line.split("+", 1)[1].split("@@", 1)[0].strip()
                start, _, count = new.partition(",")
                first, n = int(start), int(count or "1")
            except (ValueError, IndexError):
                continue
            if n:
                out.setdefault(path, []).extend(range(first, first + n))
    return out


def anchors_for(repo: Path, changed: dict[str, list[int]]) -> list[Anchor]:
    """One anchor per changed *definition*, not per changed line.

    A candidate anchors on a finding's file and line, and many changed lines sit
    in one function; counting lines would multiply every number below by however
    long the functions happen to be.
    """
    found: dict[tuple[str, str | None], Anchor] = {}
    for path, lines in sorted(changed.items()):
        if is_test_path(path):
            continue
        source = _read(repo / path)
        if source is None:
            continue
        module = _parse(source)
        if module is None:
            continue
        for line in lines:
            name, kind = _enclosing(module, line)
            key = (path, name if name else f"@{line}")
            if key not in found:
                found[key] = Anchor(path=path, line=line, function=name, kind=kind)
    return sorted(found.values(), key=lambda a: (a.path, a.line))


def _enclosing(module: ast.Module, line: int) -> tuple[str | None, str]:
    """The def containing ``line`` and whether it is module-level.

    `derive_probes` refuses everything but a module-level function, and the two
    refusals it collapses into one `None` are worth separating here: a method is
    the population this measurement exists to size.
    """
    best: tuple[str | None, str] = (None, "none")
    for node in ast.walk(module):
        if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.lineno <= line <= (node.end_lineno or node.lineno):
            continue
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and (
                    child.lineno <= line <= (child.end_lineno or child.lineno)
                ):
                    best = (child.name, "method")
            continue
        if best[1] in ("method", "nested"):
            continue
        best = (node.name, "module")
    # a def inside a def: module-level only if it is a direct child of the module
    if best[1] == "module":
        top = {
            n.name
            for n in module.body
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        if best[0] not in top:
            return (best[0], "nested")
    return best


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# --- why one call site cannot be derived ---------------------------------------


def _enclosing_function(module: ast.Module, line: int) -> ast.FunctionDef | None:
    best: ast.FunctionDef | None = None
    for node in ast.walk(module):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.lineno <= line <= (node.end_lineno or node.lineno)
            and (best is None or node.lineno > best.lineno)
        ):
            best = node  # type: ignore[assignment]
    return best


def _fixture_params(fn: ast.FunctionDef | None) -> set[str]:
    if fn is None:
        return set()
    args = fn.args
    return {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}


def _literal_locals(fn: ast.FunctionDef | None) -> set[str]:
    """Names assigned a literal inside this test function (`+local`)."""
    if fn is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and _is_literal(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.add(target.id)
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_literal(node.value)
            and isinstance(node.target, ast.Name)
        ):
            out.add(node.target.id)
    return out


def _parametrized_literals(fn: ast.FunctionDef | None) -> set[str]:
    """Argnames whose every parametrised value is a literal (`+parametrize`)."""
    if fn is None:
        return set()
    out: set[str] = set()
    for decorator in fn.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = ast.unparse(decorator.func)
        if not name.endswith("parametrize") or len(decorator.args) < 2:
            continue
        argnames, argvalues = decorator.args[0], decorator.args[1]
        if isinstance(argnames, ast.Constant) and isinstance(argnames.value, str):
            names = [p.strip() for p in argnames.value.split(",") if p.strip()]
        elif isinstance(argnames, ast.List | ast.Tuple):
            names = [
                e.value
                for e in argnames.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
        else:
            continue
        if not isinstance(argvalues, ast.List | ast.Tuple) or not argvalues.elts:
            continue
        rows: list[list[ast.expr]] = []
        for element in argvalues.elts:
            if len(names) == 1:
                rows.append([element])
            elif isinstance(element, ast.List | ast.Tuple):
                rows.append(list(element.elts))
            else:
                rows = []
                break
        if not rows or any(len(r) != len(names) for r in rows):
            continue
        for index, argname in enumerate(names):
            if all(_is_literal(row[index]) for row in rows):
                out.add(argname)
    return out


def _receiver_is_literal_construction(
    call: ast.Call, fn: ast.FunctionDef | None
) -> bool:
    """`Box().f(1)`, or `b = Box()` two lines up then `b.f(1)` (`+method`)."""
    if not isinstance(call.func, ast.Attribute):
        return False
    receiver = call.func.value
    if isinstance(receiver, ast.Call):
        return _all_literal(receiver)
    if isinstance(receiver, ast.Name) and fn is not None:
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and any(
                    isinstance(t, ast.Name) and t.id == receiver.id for t in node.targets
                )
            ):
                return _all_literal(node.value)
    return False


def _argument_reason(call: ast.Call, fn: ast.FunctionDef | None) -> str:
    """Why `_all_literal` refused this call, by the most specific argument."""
    fixtures = _fixture_params(fn)
    values: list[ast.expr] = [*call.args, *(k.value for k in call.keywords)]
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        k.arg is None for k in call.keywords
    ):
        return R_OTHER_EXPR
    reasons: list[str] = []
    for value in values:
        if _is_literal(value):
            continue
        if isinstance(value, ast.Name) and value.id in fixtures:
            reasons.append(R_FIXTURE)
        elif isinstance(value, ast.Call):
            reasons.append(R_CONSTRUCTED)
        elif isinstance(value, ast.Name):
            reasons.append(R_LOCAL)
        else:
            reasons.append(R_OTHER_EXPR)
    for preferred in (R_FIXTURE, R_CONSTRUCTED, R_LOCAL, R_OTHER_EXPR):
        if preferred in reasons:
            return preferred
    return R_OTHER_EXPR


def _admits(
    call: ast.Call,
    fn: ast.FunctionDef | None,
    *,
    method: bool,
    local: bool,
    parametrize: bool,
) -> bool:
    """Would a rule with these relaxations accept this call's arguments?"""
    if isinstance(call.func, ast.Attribute) and (
        not method or not _receiver_is_literal_construction(call, fn)
    ):
        return False
    allowed: set[str] = set()
    if local:
        allowed |= _literal_locals(fn)
    if parametrize:
        allowed |= _parametrized_literals(fn)
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        k.arg is None for k in call.keywords
    ):
        return False
    for value in (*call.args, *(k.value for k in call.keywords)):
        if _is_literal(value):
            continue
        if isinstance(value, ast.Name) and value.id in allowed:
            continue
        return False
    return True


# --- one case ------------------------------------------------------------------


class _TreeCache:
    """The test tree, read once per repository instead of once per anchor.

    `probe_sources` returns the anchored file plus every test file of the tree,
    and the second half is identical for every anchor of one repository. On
    `sympy` that walk and those reads are the whole cost, so it is done once and
    only the anchored file is swapped. The call graph is cached per anchored
    *file*, because two anchors in one file build the same graph.
    """

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._tests: dict[str, str] | None = None
        self._graphs: dict[str, object] = {}

    def sources(self, path: str) -> dict[str, str]:
        if self._tests is None:
            first = probe_sources(self.repo, path)
            if not first:
                return {}
            self._tests = {r: s for r, s in first.items() if r != path and is_test_path(r)}
            return first
        anchored = _read(self.repo / path)
        if anchored is None:
            return {}
        return {path: anchored, **self._tests}

    def graph(self, path: str, restricted: dict[str, str]) -> object:
        held = self._graphs.get(path)
        if held is None:
            held = build_call_graph(restricted)
            self._graphs[path] = held
        return held


def measure(
    repo: Path, case: str, anchors: list[Anchor], cache: _TreeCache | None = None
) -> CaseReach:
    reach = CaseReach(case=case, anchors=len(anchors))
    cache = cache or _TreeCache(repo)
    for anchor in anchors:
        if anchor.kind == "none":
            reach.reasons[R_NOT_A_FUNCTION] += 1
            continue
        if anchor.kind == "nested":
            reach.reasons[R_NESTED] += 1
            continue

        sources = cache.sources(anchor.path)
        if not sources:
            reach.reasons[R_UNREADABLE] += 1
            continue

        # the product's own answer, by construction
        reach.derived_now += len(
            derive_probes(sources, path=anchor.path, line=anchor.line)
        )

        restricted = {
            rel: src
            for rel, src in sources.items()
            if rel == anchor.path or is_test_path(rel)
        }
        graph = cache.graph(anchor.path, restricted)
        if graph.binding is None:
            reach.reasons[R_UNRESOLVED] += 1
            continue

        name = anchor.function or ""
        wanted = [
            d
            for d in graph.definitions.get(name, ())
            if d.path == anchor.path
            and (d.qualname == name or d.qualname.endswith(f".{name}"))
        ]
        if len(wanted) != 1:
            reach.reasons[R_AMBIGUOUS] += 1
            continue
        definition = wanted[0]

        sites = [s for s in graph.bound_sites(definition) if s.is_test]
        if anchor.kind == "method" and not sites:
            # attribute-call binding is what D-206 avoided; count the written
            # call sites instead, which is the ceiling this ladder admits to.
            sites = [
                s
                for s in graph.sites.get(name, ())
                if s.is_test and s.dotted.split(".")[-1] == name
            ]
        if not sites:
            reach.reasons[R_NO_SITES] += 1
            continue

        for_anchor: set[str] = set()
        for site in sorted(sites, key=lambda s: (s.path, s.line)):
            reach.sites += 1
            for_anchor |= _measure_site(reach, graph, restricted, site, anchor)
        for rule in for_anchor:
            reach.anchors_admitted[rule] += 1
    return reach


def _measure_site(
    reach: CaseReach,
    graph: object,
    restricted: dict[str, str],
    site: CallSite,
    anchor: Anchor,
) -> set[str]:
    binding = graph.binding  # type: ignore[attr-defined]
    facts = binding.facts(site.path)
    module = _parse(restricted.get(site.path, ""))
    if module is None:
        reach.reasons[R_UNRESOLVED] += 1
        return set()
    fn = _enclosing_function(module, site.line)
    calls = _calls_at(module, site)
    if not calls:
        # the site was found by name rather than by resolution (`+method`)
        calls = [
            n
            for n in ast.walk(module)
            if isinstance(n, ast.Call)
            and n.lineno == site.line
            and ast.unparse(n.func).split(".")[-1] == (anchor.function or "")
        ]
    if not calls:
        reach.reasons[R_UNRESOLVED] += 1
        return set()

    if facts is _UNPARSABLE:
        reach.reasons[R_UNRESOLVED] += 1
    elif anchor.kind == "module" and _import_line(facts, site) is None:
        reach.reasons[R_RELATIVE] += 1
    elif anchor.kind == "method":
        reach.reasons[R_METHOD] += 1
    elif any(_all_literal(c) for c in calls):
        reach.reasons[R_DERIVABLE] += 1
    else:
        reach.reasons[_argument_reason(calls[0], fn)] += 1

    admitted: set[str] = set()
    for rule, flags in (
        ("current", (False, False, False)),
        ("+method", (True, False, False)),
        ("+local", (False, True, False)),
        ("+parametrize", (False, False, True)),
        ("all relaxations", (True, True, True)),
    ):
        method, local, parametrize = flags
        # a method anchor is outside every rule but the two that relax methods
        if anchor.kind == "method" and rule in ("current", "+local", "+parametrize"):
            continue
        if any(
            _admits(c, fn, method=method, local=local, parametrize=parametrize)
            for c in calls
        ):
            reach.admitted[rule] += 1
            admitted.add(rule)
    return admitted


# --- the two corpora ------------------------------------------------------------


def corpus_cases() -> list[tuple[str, Path, str, str]]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    out = []
    for case in plan["cases"]:
        instance = case["instance_id"]
        manifest = CASES / instance / "manifest.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        out.append((instance, CASES / instance / "repo", data["base_sha"], data["head_sha"]))
    return out


def self_all_anchors(limit: int) -> list[Anchor]:
    """Every module-level function of this repository, in path order.

    The changed-function control below is the honest analogue of a diff, and it
    inherits whatever the last 40 commits happened to touch. This is the other
    half: the rule's **ceiling** on a repository whose tests were written by the
    people who wrote the rule. A rule that scores zero here is broken; a rule
    that scores well here and zero on the corpus is a rule whose assumptions the
    corpus's test style does not meet, which is a different finding entirely.
    """
    by_file: list[list[Anchor]] = []
    for path in sorted((ROOT / "src" / "attest").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = _read(path)
        if source is None:
            continue
        module = _parse(source)
        if module is None:
            continue
        found = [
            Anchor(path=relative, line=node.lineno, function=node.name, kind="module")
            for node in module.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        if found:
            by_file.append(found)
    # Round robin over files, not path order. Taking the first `limit` anchors in
    # path order samples only the alphabetically-early modules -- a control whose
    # answer would depend on how the package happens to be named.
    anchors: list[Anchor] = []
    for index in range(max((len(f) for f in by_file), default=0)):
        for found in by_file:
            if index < len(found):
                anchors.append(found[index])
                if len(anchors) >= limit:
                    return anchors
    return anchors


def self_anchors(limit: int) -> list[Anchor]:
    """The most recently changed module-level functions of this repository."""
    log = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-40", "--format=%H", "--", "src/attest"],
        capture_output=True,
        text=True,
    ).stdout.split()
    if len(log) < 2:
        # A shallow clone has no parent to diff against, so every commit yields
        # nothing and the arm reports zero anchors -- indistinguishable, in the
        # printed table, from "nothing here is derivable". Say which it is.
        print(
            "REFUSED: this checkout has no history to read "
            f"({len(log)} commit(s) touching src/attest). "
            "The changed-function arm needs `fetch-depth: 0`; measured nothing.",
            file=sys.stderr,
        )
        return []
    anchors: list[Anchor] = []
    seen: set[tuple[str, str | None]] = set()
    for sha in log:
        changed = changed_lines(ROOT, f"{sha}~1", sha)
        for anchor in anchors_for(ROOT, changed):
            if anchor.kind != "module":
                continue
            key = (anchor.path, anchor.function)
            if key in seen:
                continue
            seen.add(key)
            anchors.append(anchor)
            if len(anchors) >= limit:
                return anchors
    return anchors


# --- reporting ------------------------------------------------------------------


def report(rows: list[CaseReach], total_cases: int, label: str) -> None:
    print(f"\n=== {label}: {len(rows)} units measured ===")
    total_anchors = sum(r.anchors for r in rows)
    print(
        f"\n{'rule':<18}{'sites':>8}{'anchors':>10}   units with >=1 derivable"
    )
    for rule in RULES:
        n = sum(r.admitted.get(rule, 0) for r in rows)
        a = sum(r.anchors_admitted.get(rule, 0) for r in rows)
        units = sum(1 for r in rows if r.derivable_under(rule))
        print(f"{rule:<18}{n:>8}{a:>10}        {units} / {total_cases}")
    print(f"(anchors column is out of {total_anchors} changed definitions)")

    print(f"\n{'reason a call site is refused now':<44}{'sites':>8}")
    reasons: Counter = Counter()
    for r in rows:
        reasons.update(r.reasons)
    for name in ORDER:
        if reasons.get(name):
            print(f"{name:<44}{reasons[name]:>8}")
    for name, n in reasons.most_common():
        if name not in ORDER:
            print(f"{name:<44}{n:>8}")

    anchors = sum(r.anchors for r in rows)
    sites = sum(r.sites for r in rows)
    derived = sum(r.derived_now for r in rows)
    print(
        f"\nanchors (changed definitions): {anchors}"
        f"\ncall sites in the test tree: {sites}"
        f"\nprobes `derive_probes` returns today: {derived}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("corpus")
    c.add_argument("--out", type=Path, default=None)
    s = sub.add_parser("self")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument(
        "--all-definitions",
        action="store_true",
        help="anchor on every module-level function, not only recently changed ones",
    )
    s.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    rows: list[CaseReach] = []
    if args.command == "corpus":
        cases = corpus_cases()
        if not cases:
            print(f"no built cases under {CASES}", file=sys.stderr)
            return 1
        for instance, repo, base, head in cases:
            changed = changed_lines(repo, base, head)
            rows.append(measure(repo, instance, anchors_for(repo, changed)))
            last = rows[-1]
            print(
                f"{instance}: anchors {last.anchors}, sites {last.sites}, "
                f"derived now {last.derived_now}",
                flush=True,
            )
        report(rows, len(cases), "SWE-bench held-out corpus")
    else:
        cache = _TreeCache(ROOT)
        picked = (
            self_all_anchors(args.limit)
            if args.all_definitions
            else self_anchors(args.limit)
        )
        by_file: dict[str, list[Anchor]] = {}
        for anchor in picked:
            by_file.setdefault(anchor.path, []).append(anchor)
        for path, group in sorted(by_file.items()):
            rows.append(measure(ROOT, path, group, cache))
        label = (
            "this repository, every module-level function (the ceiling)"
            if args.all_definitions
            else "this repository, recently changed functions (the diff analogue)"
        )
        report(rows, len(rows), label)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "produced": "2026-09-11",
                    "upper_bounds": _RELAXATIONS_ARE_UPPER_BOUNDS,
                    "units": [
                        {
                            "unit": r.case,
                            "anchors": r.anchors,
                            "sites": r.sites,
                            "derived_now": r.derived_now,
                            "reasons": dict(r.reasons),
                            "admitted": dict(r.admitted),
                            "anchors_admitted": dict(r.anchors_admitted),
                        }
                        for r in rows
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - a driver
    raise SystemExit(main())
