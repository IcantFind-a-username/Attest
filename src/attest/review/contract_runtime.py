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

SCHEMA = "attest.runtime-contract-shadow.v2"
PREFIX = "ATTEST_CONTRACT_SHADOW_V2="
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


def read_observation(run: ExecutionResult, site: RuntimeSite) -> tuple[dict[str, Any] | None, str]:
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
        if not isinstance(events, list) or len(events) != 1 or not isinstance(events[0], dict):
            return None, "assertion did not execute exactly once"
        event = events[0]
        if event.get("site") != site.identity:
            return None, "wrong assertion identity"
        expected = {
            "file": site.anchor,
            "qualname": site.symbol,
            "name": site.symbol.rsplit(".", 1)[-1],
            "line": site.target_line,
            "source_digest": site.target_digest,
        }
        if event.get("callee") != expected:
            return None, "actual callable differs from the changed definition"
        if event.get("error") or event.get("raised") or event.get("compared") is not True:
            return None, "unsupported snapshot or assertion did not compare"
        if event.get("same_object") is not True or type(event.get("equal")) is not bool:
            return None, "call result is not bound to a Boolean comparison"
        if canonical_json_bytes(event.get("returned")) != canonical_json_bytes(event.get("left")):
            return None, "call result changed before comparison"
        if not {"args", "kwargs", "receiver", "expected", "returned", "left"} <= event.keys():
            return None, "incomplete binding fields"
        if not _binding_shapes(event):
            return None, "malformed typed binding snapshots"
        return event, ""
    except (ValueError, TypeError):
        return None, "malformed runtime packet"


def _node_completed(run: ExecutionResult, node: str) -> bool:
    if run.outcome not in (ExecutionOutcome.NOT_REPRODUCED, ExecutionOutcome.REPRODUCED):
        return False
    if not run.fresh_state or run.collected_count != 1 or run.skipped_count or run.xfailed_count:
        return False
    try:
        cases = list(ET.fromstring(run.junit_xml).iter("testcase"))
    except ET.ParseError:
        return False
    return len(cases) == 1 and cases[0].get("name", "").split("[", 1)[0] == node.split("::")[-1]


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
    }
    if head is None or head.assertion != base.assertion or head.node != base.node:
        result["reason"] = "source contract changed or disappeared at head"
        return result
    if set(runs) != {"base-original", "base-observed", "head-original", "head-observed"}:
        result["reason"] = "incomplete paired runs"
        return result
    if not all(_node_completed(r, base.node) for r in runs.values()):
        result["reason"] = "node did not complete exactly once without skip or executor refusal"
        return result
    if (
        digests is None
        or set(digests) != set(runs)
        or any(runs[label].test_file_digest != digest for label, digest in digests.items())
    ):
        result["reason"] = "test bytes do not match the declared original/overlay"
        return result
    node_ids = {
        tuple(
            (c.get("classname"), c.get("name")) for c in ET.fromstring(r.junit_xml).iter("testcase")
        )
        for r in runs.values()
    }
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
    events = []
    for revision, site in (("base", base), ("head", head)):
        original, observed = runs[revision + "-original"], runs[revision + "-observed"]
        if original.outcome != observed.outcome or original.exit_code != observed.exit_code:
            result["reason"] = "instrumentation changed the outcome"
            return result
        event, reason = read_observation(observed, site)
        if event is None:
            result["reason"] = reason
            return result
        if event["equal"] != (observed.outcome == ExecutionOutcome.NOT_REPRODUCED):
            result["reason"] = "assertion result disagrees with node outcome"
            return result
        events.append(event)
    fields = ("args", "kwargs", "receiver", "expected")
    if any(
        canonical_json_bytes(events[0][field]) != canonical_json_bytes(events[1][field])
        for field in fields
    ):
        result["reason"] = "input, receiver state or expectation changed between revisions"
    elif not events[0]["equal"] or events[1]["equal"]:
        result["reason"] = "no base-pass/head-fail bound assertion"
    else:
        result.update(status="binding_observed", reason="consistent runtime binding in shadow only")
    result["observations"] = events
    return result
