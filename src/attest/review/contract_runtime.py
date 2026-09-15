"""Experimental runtime contract observations; deliberately disconnected from certification.

The host selects source sites and checks consistency independently of the in-process
recorder. Same-process observations can be forged by project code: these are shadow data,
never a ContractRecord, accepted receipt, or proof of intended behaviour.
"""

from __future__ import annotations

import ast
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.benchmark.artifacts import canonical_json_bytes, sha256_bytes
from attest.review.contracts import _owners
from attest.review.executor import ExecutionOutcome, ExecutionResult
from attest.review.index import build_index
from attest.review.intent import is_spec_file

SCHEMA = "attest.runtime-contract-shadow.v3"
PREFIX = "ATTEST_CONTRACT_SHADOW_V3="
OBSERVER = "_attest_contract_shadow"
MAX_SITES = 8


@dataclass(frozen=True)
class RuntimeSite:
    path: str
    node: str
    line: int
    anchor: str
    symbol: str
    assertion: str
    source_digest: str
    target_digest: str
    target_line: int
    resolution: str

    @property
    def identity(self) -> str:
        return sha256_bytes(f"{self.path}:{self.node}:{self.line}:{self.assertion}".encode())[:20]


@dataclass(frozen=True)
class RuntimeDiscovery:
    sites: tuple[RuntimeSite, ...]
    refused: tuple[str, ...]
    truncated: int
    omitted_refusals: int


def discover_sites(root: Path, changed: dict[str, tuple[str, ...]]) -> RuntimeDiscovery:
    index = build_index(root)
    targets = {
        f"{d.module}:{d.qualname}": d
        for d in index.definitions
        if d.kind == "function"
        and d.path in changed
        and (d.qualname in changed[d.path] or d.name in changed[d.path])
    }
    calls = {(c.path, c.line, c.name): c for c in index.calls}
    sites: list[RuntimeSite] = []
    refused: list[str] = []
    for path in sorted(index.modules):
        if not is_spec_file(Path(path)):
            continue
        try:
            source = (root / path).read_text()
            tree = ast.parse(source)
        except (OSError, ValueError, SyntaxError):
            refused.append(f"{path}: source unavailable")
            continue
        owners = _owners(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("test"):
                continue
            for statement in ast.walk(fn):
                if not isinstance(statement, ast.Assert):
                    continue
                test = statement.test
                if not (
                    isinstance(test, ast.Compare)
                    and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq)
                    and isinstance(test.left, ast.Call)
                ):
                    refused.append(f"{path}:{statement.lineno}: unsupported assertion shape")
                    continue
                call = test.left
                name = (
                    call.func.attr
                    if isinstance(call.func, ast.Attribute)
                    else getattr(call.func, "id", "")
                )
                indexed = calls.get((path, call.lineno, name))
                target = targets.get(indexed.callee) if indexed is not None else None
                resolution = "index-exact"
                if target is None and isinstance(call.func, ast.Attribute):
                    possible = [d for d in targets.values() if d.name == name]
                    if len(possible) == 1:
                        target, resolution = possible[0], "attribute-needs-runtime-binding"
                if target is None:
                    continue
                node = "::".join([*(c.name for c in owners.get(id(fn), ())), fn.name])
                sites.append(
                    RuntimeSite(
                        path,
                        node,
                        statement.lineno,
                        target.path,
                        target.qualname,
                        ast.dump(statement.test, include_attributes=False),
                        sha256_bytes(source.encode()),
                        sha256_bytes((root / target.path).read_bytes()),
                        target.start,
                        resolution,
                    )
                )
    selected_lines = {(s.path, s.line) for s in sites}
    for indexed_call in index.calls:
        if (
            indexed_call.callee in targets
            and is_spec_file(Path(indexed_call.path))
            and (indexed_call.path, indexed_call.line) not in selected_lines
        ):
            refused.append(
                f"{indexed_call.path}:{indexed_call.line}: "
                "target call outside supported direct equality"
            )
    sites.sort(key=lambda s: (s.path, s.node, s.line, s.anchor))
    return RuntimeDiscovery(
        tuple(sites[:MAX_SITES]),
        tuple(refused[:64]),
        max(0, len(sites) - MAX_SITES),
        max(0, len(refused) - 64),
    )


def instrument(source: str, site: RuntimeSite) -> str:
    if sha256_bytes(source.encode()) != site.source_digest:
        raise ValueError("source digest changed")
    tree = ast.parse(source)
    if any(isinstance(n, ast.Name) and n.id == OBSERVER for n in ast.walk(tree)):
        raise ValueError("observer binding already exists")
    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assert)
        and n.lineno == site.line
        and ast.dump(n.test, include_attributes=False) == site.assertion
    ]
    if len(nodes) != 1:
        raise ValueError("assertion site is not unique")
    statement = nodes[0]
    comparison = statement.test
    if not isinstance(comparison, ast.Compare) or not isinstance(comparison.left, ast.Call):
        raise ValueError("unsupported assertion")
    call = comparison.left
    if any(
        isinstance(n, (ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr))
        for n in ast.walk(comparison)
    ):
        raise ValueError("suspending or assigning assertion")
    left = ast.Call(
        ast.Attribute(ast.Name(OBSERVER, ast.Load()), "call", ast.Load()),
        [ast.Constant(site.identity), call.func, *call.args],
        call.keywords,
    )
    statement.test = ast.Call(
        ast.Attribute(ast.Name(OBSERVER, ast.Load()), "compare", ast.Load()),
        [ast.Constant(site.identity), left, comparison.comparators[0]],
        [],
    )
    # Keep module docstrings and __future__ imports first; all fixtures/hooks are retained.
    insertion = 0
    for item in tree.body:
        if (isinstance(item, ast.ImportFrom) and item.module == "__future__") or (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            insertion += 1
        else:
            break
    tree.body.insert(insertion, ast.Import([ast.alias(OBSERVER)]))
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def _snapshot_valid(value: Any, depth: int = 0) -> bool:
    if depth > 4 or not isinstance(value, dict):
        return False
    kind = value.get("kind")
    scalar_types = {"none": type(None), "bool": bool, "int": int, "float": float, "str": str}
    if isinstance(kind, str) and kind in scalar_types:
        if set(value) != {"kind", "value"} or type(value["value"]) is not scalar_types[kind]:
            return False
        item: Any = value["value"]
        return (
            (kind != "str" or len(item) <= 256)
            and (kind != "int" or item.bit_length() <= 256)
            and (kind != "float" or math.isfinite(item))
        )
    items = value.get("items")
    if not isinstance(items, list) or len(items) > 16:
        return False
    if kind == "dict" and set(value) == {"kind", "items"}:
        if not all(
            isinstance(pair, list)
            and len(pair) == 2
            and isinstance(pair[0], str)
            and len(pair[0]) <= 80
            and _snapshot_valid(pair[1], depth + 1)
            for pair in items
        ):
            return False
        return len({pair[0] for pair in items}) == len(items)
    return (
        kind in ("list", "tuple")
        and set(value) == {"kind", "type", "items"}
        and (
            isinstance(value["type"], str)
            and len(value["type"]) <= 256
            and all(_snapshot_valid(item, depth + 1) for item in items)
        )
    )


def _binding_shapes(event: dict[str, Any]) -> bool:
    fields = ("args", "kwargs", "expected", "returned", "left")
    if not all(_snapshot_valid(event.get(field)) for field in fields):
        return False
    if event["args"].get("kind") != "tuple" or event["args"].get("type") != "builtins.tuple":
        return False
    if event["kwargs"].get("kind") != "dict":
        return False
    receiver = event.get("receiver")
    return receiver is None or (
        isinstance(receiver, dict)
        and set(receiver) == {"type", "state"}
        and isinstance(receiver["type"], str)
        and len(receiver["type"]) <= 256
        and _snapshot_valid(receiver["state"])
        and receiver["state"].get("kind") == "dict"
    )


def _read_observations(
    run: ExecutionResult,
    site: RuntimeSite,
) -> tuple[dict[str, dict[str, Any]] | None, str]:
    lines = [line[len(PREFIX) :] for line in run.stdout.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        return None, "missing or duplicate runtime packet"
    try:
        packet = json.loads(lines[0])
        if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
            return None, "unknown runtime schema"
        if packet.get("truncated") is not False or packet.get("receipt_eligible") is not False:
            return None, "truncated packet or invalid authority flag"
        events = packet.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= 32:
            return None, "assertion did not execute within the bounded node population"
        expected = {
            "file": site.anchor,
            "qualname": site.symbol,
            "name": site.symbol.rsplit(".", 1)[-1],
            "line": site.target_line,
            "source_digest": site.target_digest,
        }
        by_node = {}
        for event in events:
            if not isinstance(event, dict) or event.get("site") != site.identity:
                return None, "wrong assertion identity"
            node = event.get("node")
            if not isinstance(node, str) or not node or len(node) > 2048 or node in by_node:
                return None, "missing, duplicate or invalid observation node"
            if event.get("callee") != expected:
                return None, "actual callable differs from the changed definition"
            if event.get("error") or event.get("raised") or event.get("compared") is not True:
                return None, "unsupported snapshot or assertion did not compare"
            if event.get("same_object") is not True or type(event.get("equal")) is not bool:
                return None, "call result is not bound to a Boolean comparison"
            if canonical_json_bytes(event.get("returned")) != canonical_json_bytes(
                event.get("left")
            ):
                return None, "call result changed before comparison"
            if not {"args", "kwargs", "receiver", "expected", "returned", "left"} <= event.keys():
                return None, "incomplete binding fields"
            if not _binding_shapes(event):
                return None, "malformed typed binding snapshots"
            by_node[node] = event
        return by_node, ""
    except (ValueError, TypeError):
        return None, "malformed runtime packet"


def read_observation(run: ExecutionResult, site: RuntimeSite) -> tuple[dict[str, Any] | None, str]:
    """Single-observation diagnostic interface; multi-node interpretation uses the full set."""
    events, reason = _read_observations(run, site)
    if events is None:
        return None, reason
    if len(events) != 1:
        return None, "assertion did not execute exactly once"
    return next(iter(events.values())), ""


def _completed_nodes(
    run: ExecutionResult,
    site: RuntimeSite,
    cases: list[ET.Element] | None,
) -> dict[str, tuple[str, bool]] | None:
    if run.outcome not in (ExecutionOutcome.NOT_REPRODUCED, ExecutionOutcome.REPRODUCED):
        return None
    if (
        not run.fresh_state
        or not 1 <= run.collected_count <= 32
        or run.skipped_count
        or run.xfailed_count
    ):
        return None
    if cases is None or len(cases) != run.collected_count:
        return None
    nodes = {}
    function = site.node.rsplit("::", 1)[-1]
    for case in cases:
        name, classname = case.get("name", ""), case.get("classname", "")
        if (
            name.split("[", 1)[0] != function
            or not classname
            or case.find("skipped") is not None
            or case.find("error") is not None
        ):
            return None
        suffix = name[len(function) :]
        if suffix and not (suffix.startswith("[") and suffix.endswith("]")):
            return None
        node = site.path + "::" + site.node + suffix
        if len(node) > 2048 or node in nodes:
            return None
        nodes[node] = (classname, case.find("failure") is None)
    passed = all(status for _, status in nodes.values())
    if run.exit_code != (0 if passed else 1) or passed != (
        run.outcome == ExecutionOutcome.NOT_REPRODUCED
    ):
        return None
    return nodes


def interpret_pair(
    base: RuntimeSite,
    head: RuntimeSite | None,
    runs: dict[str, ExecutionResult],
    *,
    digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "defer",
        "reason": "",
        "receipt_eligible": False,
        "trust": "same-process-shadow",
        "node_reports": {},
    }
    if head is None or head.assertion != base.assertion or head.node != base.node:
        result["reason"] = "source contract changed or disappeared at head"
        return result
    if set(runs) != {"base-original", "base-observed", "head-original", "head-observed"}:
        result["reason"] = "incomplete paired runs"
        return result
    case_tables = {}
    for label, run in runs.items():
        try:
            cases = list(ET.fromstring(run.junit_xml).iter("testcase"))
        except ET.ParseError:
            cases = None
        case_tables[label] = cases
        result["node_reports"][label] = {
            "count": len(cases) if cases is not None else None,
            "parse_error": cases is None,
            "omitted": max(0, len(cases) - 32) if cases is not None else 0,
            "rows": [
                {
                    "name": case.get("name", ""),
                    "classname": case.get("classname", ""),
                    "outcome": next(
                        (
                            kind
                            for kind in ("error", "skipped", "failure")
                            if case.find(kind) is not None
                        ),
                        "passed",
                    ),
                }
                for case in (cases or [])[:32]
            ],
        }
    outcomes: dict[str, dict[str, tuple[str, bool]]] = {}
    for label, run in runs.items():
        completed = _completed_nodes(run, base, case_tables[label])
        if completed is None:
            result["reason"] = "nodes did not complete uniquely without skip or executor refusal"
            return result
        outcomes[label] = completed
    if (
        digests is None
        or set(digests) != set(runs)
        or any(runs[label].test_file_digest != digest for label, digest in digests.items())
    ):
        result["reason"] = "test bytes do not match the declared original/overlay"
        return result
    node_ids = {tuple(sorted((n, c) for n, (c, _) in v.items())) for v in outcomes.values()}
    if len(node_ids) != 1:
        result["reason"] = "collected node identities differ"
        return result
    identities = {
        (r.executor_profile, r.executor_digest, r.interpreter_version, r.environment_digest)
        for r in runs.values()
    }
    if len(identities) != 1:
        result["reason"] = "execution environments differ"
        return result
    events_by_revision = []
    for revision, site in (("base", base), ("head", head)):
        observed = runs[revision + "-observed"]
        if outcomes[revision + "-original"] != outcomes[revision + "-observed"]:
            result["reason"] = "instrumentation changed the outcome"
            return result
        events, reason = _read_observations(observed, site)
        if events is None:
            result["reason"] = reason
            return result
        if set(events) != set(outcomes[revision + "-observed"]):
            result["reason"] = "observation nodes differ from the complete collected population"
            return result
        if any(
            events[n]["equal"] != status
            for n, (_, status) in outcomes[revision + "-observed"].items()
        ):
            result["reason"] = "assertion result disagrees with node outcome"
            return result
        events_by_revision.append(events)
    fields = ("args", "kwargs", "receiver", "expected")
    nodes = []
    for node in sorted(events_by_revision[0]):
        pair = [revision[node] for revision in events_by_revision]
        row = {
            "node": node,
            "status": "defer",
            "reason": "",
            "receipt_eligible": False,
            "observations": pair,
        }
        if any(
            canonical_json_bytes(pair[0][f]) != canonical_json_bytes(pair[1][f]) for f in fields
        ):
            row["reason"] = "input, receiver state or expectation changed between revisions"
        elif not pair[0]["equal"] or pair[1]["equal"]:
            row["reason"] = "no base-pass/head-fail bound assertion"
        else:
            row.update(
                status="binding_observed", reason="consistent runtime binding in shadow only"
            )
        nodes.append(row)
    result["nodes"] = nodes
    if any(row["status"] == "binding_observed" for row in nodes):
        result.update(status="binding_observed", reason="consistent runtime binding in shadow only")
    else:
        result["reason"] = (
            nodes[0]["reason"] if len(nodes) == 1 else "no node has a bound regression"
        )
    if len(nodes) == 1:
        result["observations"] = nodes[0]["observations"]
    return result
