"""Probes derived from a repository's own tests -- a **harness** tool since
2026-09-11 (owner authorisation 5 of the drawer window).

D-206 put this in the product path and D-212 measured its supply: 5 of 39
held-out cases had a derived probe at all, and D-216's model search covers
the same ground. The product no longer derives probes; `probe_reach.py`
still measures what the derivation would reach, and imports it from here.
"""


from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from attest.review.binding import _UNPARSABLE, dotted_name
from attest.review.impact import CallSite, FunctionDef, build_call_graph, is_test_path
from attest.review.probe import ProbeSpec

DERIVED_PROBE_POLICY_VERSION = "attest.probe.derived-from-tests.v1"

# How many derived probes one candidate may try before the model is asked.
# Each costs the recording runs on base plus one screening run on head and no
# model call; the bound is on container time, not on money.
MAX_DERIVED_PROBES = 4
# Boundary variants taken from one exact call, in the order they are tried.
MAX_VARIANTS_PER_CALL = 3

KIND_EXACT = "exact"
KIND_VARIANT = "variant"


@dataclass(frozen=True)
class DerivedProbe:
    """One probe read out of a test, and where it came from."""

    spec: ProbeSpec
    origin: str  # "tests/test_mod.py:12"
    kind: str  # KIND_EXACT | KIND_VARIANT
    policy_version: str = DERIVED_PROBE_POLICY_VERSION


def derive_probes(
    sources: Mapping[str, str],
    *,
    path: str,
    line: int,
    limit: int = MAX_DERIVED_PROBES,
) -> tuple[DerivedProbe, ...]:
    """Probes for the module-level function of ``path`` that contains ``line``.

    ``sources`` is the tree (or the part of it that matters: the anchored file
    and the test files), keyed by repository-relative POSIX path. Exact calls
    come first, in file and line order, then one boundary variant at a time of
    each; the same expression is never returned twice, and the whole is capped.
    """
    if limit <= 0:
        return ()
    anchored = sources.get(path)
    if anchored is None:
        return ()
    name = _module_level_function_at(anchored, line)
    if name is None:
        return ()
    restricted = {
        relative: source
        for relative, source in sources.items()
        if relative == path or is_test_path(relative)
    }
    graph = build_call_graph(restricted)
    definition = _definition(graph.definitions.get(name, ()), path, name)
    if definition is None or graph.binding is None:
        return ()
    sites = [site for site in graph.bound_sites(definition) if site.is_test]
    sites.sort(key=lambda site: (site.path, site.line))

    parsed: dict[str, ast.Module | None] = {}
    exact: list[DerivedProbe] = []
    variants: list[DerivedProbe] = []
    seen: set[str] = set()
    for site in sites:
        imports = _import_line(graph.binding.facts(site.path), site)
        if imports is None:
            continue
        if site.path not in parsed:
            parsed[site.path] = _parse(restricted.get(site.path, ""))
        module = parsed[site.path]
        if module is None:
            continue
        for call in _calls_at(module, site):
            if not _all_literal(call):
                continue
            origin = f"{site.path}:{site.line}"
            expression = ast.unparse(call)
            if expression not in seen:
                seen.add(expression)
                exact.append(DerivedProbe(ProbeSpec(imports, "", expression), origin, KIND_EXACT))
            for variant in _variants(call):
                text = ast.unparse(variant)
                if text in seen:
                    continue
                seen.add(text)
                variants.append(DerivedProbe(ProbeSpec(imports, "", text), origin, KIND_VARIANT))
    return tuple((*exact, *variants)[:limit])


# --- which function, and which calls ------------------------------------------


def _module_level_function_at(source: str, line: int) -> str | None:
    module = _parse(source)
    if module is None:
        return None
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
            node.lineno <= line <= (node.end_lineno or node.lineno)
        ):
            return node.name
    return None


def _definition(candidates: Iterable[FunctionDef], path: str, name: str) -> FunctionDef | None:
    found = [d for d in candidates if d.path == path and d.qualname == name]
    return found[0] if len(found) == 1 else None


def _parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None


def _calls_at(module: ast.Module, site: CallSite) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and node.lineno == site.line
        and dotted_name(node.func) == site.dotted
    ]


# --- the import, as the test wrote it -----------------------------------------


def _import_line(facts: object, site: CallSite) -> str | None:
    """The one import statement that binds the call's root name in the test.

    Reproduced rather than invented: the test's own import is the shape that
    resolves on this tree. A relative import cannot be reproduced outside the
    test tree and is refused."""
    if facts is _UNPARSABLE or not site.dotted:
        return None
    parts = site.dotted.split(".")
    if len(parts) == 1:
        bound = getattr(facts, "functions", {}).get(parts[0])
        if bound is None:
            return None
        module, level, original = bound
        if level or module is None:
            return None
        alias = "" if original == parts[0] else f" as {parts[0]}"
        return f"from {module} import {original}{alias}"
    prefix = ".".join(parts[:-1])
    bound_module = getattr(facts, "modules", {}).get(prefix)
    if bound_module is None:
        return None
    module, level = bound_module
    if level or module is None:
        return None
    return f"import {module}" if module == prefix else f"import {module} as {prefix}"


# --- literals and their boundaries ----------------------------------------------


def _all_literal(call: ast.Call) -> bool:
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return False
    if any(keyword.arg is None for keyword in call.keywords):
        return False
    return all(_is_literal(arg) for arg in call.args) and all(
        _is_literal(keyword.value) for keyword in call.keywords
    )


def _is_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str | bytes | int | float | bool | type(None))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        return isinstance(node.operand, ast.Constant) and isinstance(
            node.operand.value, int | float
        )
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return all(_is_literal(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _is_literal(key) for key in node.keys) and all(
            _is_literal(value) for value in node.values
        )
    return False


def _boundaries(node: ast.expr) -> list[ast.expr]:
    """Boundary values of one literal, most-different first."""
    if isinstance(node, ast.List):
        return [ast.List(elts=[], ctx=ast.Load())] if node.elts else []
    if isinstance(node, ast.Tuple):
        return [ast.Tuple(elts=[], ctx=ast.Load())] if node.elts else []
    if isinstance(node, ast.Set):
        return [ast.Call(ast.Name("set", ast.Load()), [], [])] if node.elts else []
    if isinstance(node, ast.Dict):
        return [ast.Dict(keys=[], values=[])] if node.keys else []
    if isinstance(node, ast.UnaryOp):
        # a negative number: its boundary is zero
        return [ast.Constant(0)]
    if not isinstance(node, ast.Constant):
        return []
    value = node.value
    if isinstance(value, bool):
        return [ast.Constant(not value)]
    if isinstance(value, int):
        out: list[ast.expr] = []
        if value != 0:
            out.append(ast.Constant(0))
        if value > 0:
            out.append(ast.Constant(-1))
        return out
    if isinstance(value, float):
        return [ast.Constant(0.0)] if value != 0.0 else []
    if isinstance(value, str):
        return [ast.Constant("")] if value else []
    if isinstance(value, bytes):
        return [ast.Constant(b"")] if value else []
    return []


def _variants(call: ast.Call) -> list[ast.Call]:
    """One argument changed to a boundary value at a time, bounded per call."""
    out: list[ast.Call] = []
    slots: list[tuple[str, int]] = [("arg", i) for i in range(len(call.args))] + [
        ("kw", i) for i in range(len(call.keywords))
    ]
    for kind, index in slots:
        original = call.args[index] if kind == "arg" else call.keywords[index].value
        for boundary in _boundaries(original):
            args = list(call.args)
            keywords = [ast.keyword(k.arg, k.value) for k in call.keywords]
            if kind == "arg":
                args[index] = boundary
            else:
                keywords[index] = ast.keyword(call.keywords[index].arg, boundary)
            out.append(ast.Call(func=call.func, args=args, keywords=keywords))
            if len(out) >= MAX_VARIANTS_PER_CALL:
                return out
    return out


# --- reading only what this needs ------------------------------------------------

MAX_PROBE_SOURCE_FILES = 2_000
MAX_PROBE_SOURCE_BYTES = 400_000
_SKIPPED = frozenset(
    {".git", ".attest", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
)


def probe_sources(root: Path, path: str) -> dict[str, str]:
    """The anchored file and the tree's test files, by relative POSIX path.

    Deliberately not the whole tree: deriving a probe needs the definition and
    the tests that call it, and reading a large repository's every module to
    find them is time this pays on every candidate.
    """
    sources: dict[str, str] = {}
    anchored = root / path
    text = _read(anchored)
    if text is None:
        return {}
    sources[path] = text
    for candidate in sorted(root.rglob("*.py")):
        relative = candidate.relative_to(root)
        if any(part in _SKIPPED for part in relative.parts):
            continue
        posix = relative.as_posix()
        if posix in sources or not is_test_path(posix):
            continue
        body = _read(candidate)
        if body is not None:
            sources[posix] = body
        if len(sources) >= MAX_PROBE_SOURCE_FILES:
            break
    return sources


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_PROBE_SOURCE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
