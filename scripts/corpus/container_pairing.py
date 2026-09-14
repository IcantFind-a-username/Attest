"""The container pairing: {frozen probe, contract probe} x {attest.intent.v5.1, v6}, with
kernel receipts, offline and free (D-253).

Every execution here is the product's own path, end to end, on `linux-container-v1`:
`execute_differential` (record the probe on the merge base three times, screen it once on
head, replay it three times each side, judge intent under the named policy) and then
`attempt_certification` (build the receipt, validate it in the kernel, write the evidence
bundle and verify that bundle offline with its seal). A case is *certified* only when that
last step returns `accepted`. No model is called: every probe is either the arm's own frozen
probe or one derived from a contract by the fixed rule below.

    forty            arm C's frozen probe for every case of the forty that has one, under
                     both policies; the D-249 attribution of every receipt arm C lacked
    contracts        the cases whose base tree holds a contract (the v6 pairing of
                     2026-09-15 found them): every contract turned into a probe by the rule,
                     every probe executed under v5.1, and under v6 when its differential held
    counterexamples  for every contract probe v6 certified, the same probe on a head that
                     also removes the test the admitted contract stands on -- an intended
                     change, which must not publish -- under both policies
    controls         the real-PR value lines whose note carries its probe, under both policies
    summary          the tables, from the records alone

The rule that turns a contract into a probe, fixed before anything ran and applied the same
way to every contract (no case is tuned by hand):

 1. The call is the contract's own call: for an assertion or a parametrize row, the side of
    its `==`/`is` that resolves to the anchored module; for an expected exception, the first
    call inside the `with raises(...)` block that resolves to the caller the contract names.
 2. Every free name of that call is bound, recursively, and only from the test's own source:
    a parametrize row value, a top-level import of a module that is not a test module, an
    assignment earlier in the test function, or a module-level assignment of the test file.
 3. A fixture parameter, a name defined by the test module itself (a helper function or
    class), or an import of a test module makes the contract **not constructible**, reported
    with that reason; so does the product's own static admissibility (`hygiene_refusal`, and
    the probe must import the project).
 4. One probe per parametrize row; identical probes once; order is (file, line, row).
 5. Per case, the probe that decides is the **first in that order whose differential held**
    (head FAIL 3/3, base PASS 3/3, the changed lines executed) -- the product's own screening
    rule, an ordering decision made before any intent rule reads the result, and the same
    probe under both policies. Every other probe's outcome is recorded and counted nowhere.

Artifacts are append-only JSONL under `docs/acceptance/evidence/2026-09-15-container-pairing/`
named by a run id; bundles go under `.attest/corpora/container-pairing/<run id>/`.

    .venv/bin/python scripts/corpus/container_pairing.py forty --run-id r1
    .venv/bin/python scripts/corpus/container_pairing.py contracts --run-id r1
    .venv/bin/python scripts/corpus/container_pairing.py counterexamples --run-id r1
    .venv/bin/python scripts/corpus/container_pairing.py controls --run-id r1
    .venv/bin/python scripts/corpus/container_pairing.py summary --run-id r1
"""

from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from evidence_supply import symbols_before_d249  # noqa: E402
from frozen_probe_replay import ARMS, frozen_probe  # noqa: E402
from mutation_recall import STUDY, WORK, classify  # noqa: E402

from attest.certification.intent import (  # noqa: E402
    INTENT_POLICY_V6,
    INTENT_POLICY_VERSION,
    IntentObservation,
    intent_verdict,
)
from attest.execution.backends import select_backend  # noqa: E402
from attest.review.candidates import StoredCandidate  # noqa: E402
from attest.review.certify import (  # noqa: E402
    attempt_certification,
    certification_policy,
    certification_task,
)
from attest.review.contracts import (  # noqa: E402
    _bindings,
    _module_name,
    _parametrize,
    _resolve_call,
    find_contracts,
)
from attest.review.executor import (  # noqa: E402
    ExecutorLimits,
    ReproSpec,
    VerificationRun,
    execute_differential,
)
from attest.review.gate import GateResult  # noqa: E402
from attest.review.index import tree_index  # noqa: E402
from attest.review.intent import anchored_symbols  # noqa: E402
from attest.review.probe import (  # noqa: E402
    Observation,
    ProbeSpec,
    hygiene_refusal,
    reaches_the_tree,
    replay_test_body,
    tree_roots,
)
from attest.review.schema import Finding  # noqa: E402

OUT = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-container-pairing"
BUNDLES = ROOT / ".attest" / "corpora" / "container-pairing"
PAIRING = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-v6-pairing"
CONTROLS = ROOT / ".attest" / "corpora" / "e05-controls"
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
STUDIES = ROOT / "benchmarks" / "studies"
POLICIES = {"v5.1": INTENT_POLICY_VERSION, "v6": INTENT_POLICY_V6}
REPEATS = 3
WALL_TIMEOUT_S = 180.0
MAX_PROBES_PER_CASE = 16
HARNESS_POLICY = "attest.container-pairing.v1"
_BUILTINS = frozenset(dir(builtins))


# ----------------------------------------------------------------- git / io


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:300]}")
    return done.stdout


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _checkout(repo: Path, sha: str) -> None:
    _git(repo, "checkout", "-q", "--", ".")
    _git(repo, "checkout", "-q", "--detach", sha)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text)[:120]


# --------------------------------------------------------- one execution


_BACKENDS: dict[tuple[str, str], object] = {}


def execute(
    *,
    run_id: str,
    label: str,
    repo: Path,
    library: str,
    base_sha: str,
    head_sha: str,
    path: str,
    line: int,
    probe: ProbeSpec,
    policy: str,
) -> dict:
    """One probe, one policy, the product's path to a kernel verdict. Returns the record."""
    _checkout(repo, head_sha)
    key = (str(repo), head_sha)
    if key not in _BACKENDS:
        _BACKENDS[key] = select_backend(repo, production=True)
    backend = _BACKENDS[key]
    record: dict = {
        "run_id": run_id, "label": label, "library": library, "policy": policy,
        "base_sha": base_sha, "head_sha": head_sha, "anchor": f"{path}:{line}",
        "probe": asdict(probe), "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if backend.adapter is None:  # type: ignore[attr-defined]
        record.update({"outcome": "backend unavailable", "reason": backend.reason,  # type: ignore[attr-defined]
                       "certification": "not_attempted"})
        return record
    task_id = _safe(f"cp-{run_id}-{label}-{policy.rsplit('.', 1)[-1]}")
    candidate = StoredCandidate(
        task_id=task_id,
        finding=Finding(claim=f"container pairing {label} under {policy}", file=path, line=line,
                        failure_scenario="", falsification_plan=""),
        wealth=0.0, action="verify", alpha=0.1,
    )
    started = time.monotonic()
    execution = execute_differential(
        repo, candidate, ReproSpec(test_body=""), ExecutorLimits(wall_timeout_s=WALL_TIMEOUT_S),
        base_sha=base_sha, head_sha=head_sha, repeats=REPEATS,
        adapter=backend.adapter,  # type: ignore[attr-defined]
        probe=probe, intent_policy=policy,
    )
    profile = backend.profile  # type: ignore[attr-defined]
    cpolicy = certification_policy(REPEATS, profile, intent_policy_version=policy)
    diff = _git(repo, "diff", base_sha, head_sha)
    task = certification_task(
        task_id=task_id, repository_id=library, merge_base_sha=base_sha, head_sha=head_sha,
        diff_digest=_digest(diff), policy_source_sha=base_sha, policy=cpolicy,
        review_policy_digest=_digest(HARNESS_POLICY),
    )
    verification = VerificationRun(
        execution=execution,
        gate_result=GateResult(finding=candidate.finding, wealth=0.0),
        spec=execution.executed_spec,
    )
    bundle_root = BUNDLES / run_id
    bundle_root.mkdir(parents=True, exist_ok=True)
    attempt = attempt_certification(task, cpolicy, candidate, verification,
                                    limits=ExecutorLimits(wall_timeout_s=WALL_TIMEOUT_S),
                                    bundle_root=bundle_root)
    intent = execution.intent
    record.update({
        "task_id": task_id,
        "backend": profile,
        "outcome": execution.outcome.value,
        "evidence_class": execution.evidence_class.value,
        "reason": execution.reason,
        "differential_held": intent is not None,
        "head_runs": [r.outcome.value for r in execution.head_runs],
        "base_runs": [r.outcome.value for r in execution.base_runs],
        "probe_observation": asdict(execution.probe) if execution.probe else None,
        "intent": intent.record() if intent is not None else None,
        "intent_verdict": (intent_verdict(intent) or "publishes") if intent is not None else None,
        "test_body": execution.executed_spec.test_body if execution.executed_spec else "",
        "certification": attempt.outcome,
        "certification_reason": attempt.reason,
        "rejection_codes": list(attempt.rejection_codes),
        "receipt_digest": attempt.receipt_digest,
        "bundle": (str(attempt.bundle.path.relative_to(ROOT))
                   if attempt.bundle is not None else None),
        "elapsed_s": round(time.monotonic() - started, 1),
    })
    return record


def _print(record: dict) -> None:
    print(json.dumps({k: record.get(k) for k in (
        "label", "policy", "outcome", "differential_held", "certification", "elapsed_s")}
        | {"why": str(record.get("intent_verdict") or record.get("reason") or "")[:110]},
        ensure_ascii=False), flush=True)


# ------------------------------------------------------------------ forty


def cmd_forty(args: argparse.Namespace) -> int:
    arm_dir = ARMS / "arm-C"
    trials = {r["unit_id"]: r for r in _read_jsonl(arm_dir / "trials-arm-C.jsonl")}
    out = OUT / f"forty-{args.run_id}.jsonl"
    done = {(r["label"], r["policy"]) for r in _read_jsonl(out)}
    ledgers: dict[str, list[dict]] = {}
    only = {s for s in args.only.split(",") if s}
    for row in _read_jsonl(STUDY / "sample.jsonl"):
        unit_id, library = str(row["unit_id"]), str(row["library"])
        if only and unit_id not in only:
            continue
        site = (str(row["mutation"]["path"]), int(row["mutation"]["line"]))
        trial = trials[unit_id]
        if library not in ledgers:
            ledgers[library] = _read_jsonl(arm_dir / f"{library}-ledger.jsonl")
        mine = [r for r in ledgers[library] if r.get("task_id") == trial["task_id"]]
        recorded, _why = classify(mine, str(trial.get("deferred_reason") or ""), site=site)
        probe_row, reason = frozen_probe(mine)
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        for name, policy in POLICIES.items():
            label = f"{unit_id}/frozen"
            if (label, policy) in done:
                continue
            if probe_row is None:
                _append(out, {"run_id": args.run_id, "label": label, "unit_id": unit_id,
                              "policy": policy, "recorded": recorded, "outcome": "no probe",
                              "reason": reason, "certification": "not_attempted"})
                continue
            probe = ProbeSpec(imports=str(probe_row.get("imports") or ""),
                              setup=str(probe_row.get("setup") or ""),
                              expression=str(probe_row.get("expression") or ""))
            record = execute(run_id=args.run_id, label=label, repo=repo, library=library,
                             base_sha=manifest["base_sha"], head_sha=manifest["head_sha"],
                             path=site[0], line=site[1], probe=probe, policy=policy)
            record.update({"unit_id": unit_id, "stratum": row["stratum"], "recorded": recorded,
                           "arm_c_finding": probe_row.get("finding_id")})
            if name == "v5.1" and record.get("intent"):
                record["d249"] = _d249_attribution(repo, manifest, record)
            _append(out, record)
            _print(record)
    return 0


def _d249_attribution(repo: Path, manifest: dict, record: dict) -> dict:
    """Would this very observation have published under the symbol rule before D-249?
    The recorded observation with its anchored symbols replaced by the old rule's."""
    intent = record["intent"]
    path = intent["path"]
    base_src = _git(repo, "show", f"{manifest['base_sha']}:{path}")
    head_src = _git(repo, "show", f"{manifest['head_sha']}:{path}")
    changed = tuple(intent.get("changed_lines") or ())
    before = symbols_before_d249(base_src, head_src, changed)
    now = anchored_symbols(base_source=base_src, head_source=head_src, changed_lines=changed)
    observation = IntentObservation(**intent)
    if tuple(before) == tuple(now):
        return {"symbols_changed": False, "verdict_before": record["intent_verdict"]}
    from dataclasses import replace

    old = replace(observation, anchored_symbols=tuple(before), value_specified=())
    return {"symbols_changed": True, "symbols_before": list(before), "symbols_now": list(now),
            "verdict_before": intent_verdict(old) or "publishes"}


# -------------------------------------------------------- contract probes


def _frozen_replay_body(unit_id: str, library: str) -> str:
    """Arm C's frozen probe as the replay test the product writes from it: the
    probe and the base observation the ledger recorded. `find_contracts` reads the
    probe's call out of it to know the symbol and the entry the case is about."""
    arm_dir = ARMS / "arm-C"
    trial = {r["unit_id"]: r for r in _read_jsonl(arm_dir / "trials-arm-C.jsonl")}[unit_id]
    mine = [r for r in _read_jsonl(arm_dir / f"{library}-ledger.jsonl")
            if r.get("task_id") == trial["task_id"]]
    row, _reason = frozen_probe(mine)
    if row is None:
        return ""
    spec = ProbeSpec(imports=str(row.get("imports") or ""), setup=str(row.get("setup") or ""),
                     expression=str(row.get("expression") or ""))
    return replay_test_body(spec, Observation(kind=str(row.get("observed_kind")),
                                              detail=str(row.get("observed_detail"))))


class NotConstructible(ValueError):
    pass


def _is_test_module(module: str) -> bool:
    parts = module.split(".")
    return any(p in ("tests", "test", "testing", "conftest") or p.startswith("test_")
               for p in parts)


def _free_names(node: ast.AST) -> list[str]:
    bound: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.comprehension):
            for target in ast.walk(inner.target):
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(inner, ast.Lambda):
            bound.update(a.arg for a in inner.args.args)
    found: list[str] = []
    for inner in ast.walk(node):
        if (isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)
                and inner.id not in bound and inner.id not in _BUILTINS
                and inner.id not in found):
            found.append(inner.id)
    return found


def build_probe(
    *, tree_file: ast.Module, func: ast.FunctionDef | ast.AsyncFunctionDef, statement: ast.stmt,
    call: ast.AST, row: dict[str, ast.AST],
) -> ProbeSpec:
    """Rule 2 and 3: bind every free name of ``call`` from the test's own source."""
    imports: dict[str, str] = {}
    for node in tree_file.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                imports[alias.asname or alias.name] = (
                    f"from {node.module} import {alias.name}"
                    + (f" as {alias.asname}" if alias.asname else "") + "|" + node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[(alias.asname or alias.name).split(".")[0]] = (
                    f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
                    + "|" + alias.name)
    module_assign: dict[str, ast.stmt] = {}
    local_defs: set[str] = set()
    for node in tree_file.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                node.targets[0], ast.Name):
            module_assign[node.targets[0].id] = node
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            local_defs.add(node.name)
    body_assign: dict[str, ast.stmt] = {}
    for node in ast.walk(func):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.lineno < statement.lineno):
            body_assign[node.targets[0].id] = node
    params = {a.arg for a in (*func.args.args, *func.args.kwonlyargs)}

    import_lines: list[str] = []
    setup: list[str] = []
    visiting: set[str] = set()
    placed: set[str] = set()

    def bind(name: str) -> None:
        if name in placed:
            return
        if name in visiting:
            raise NotConstructible(f"name {name!r} is defined in terms of itself")
        visiting.add(name)
        if name in row:
            for inner in _free_names(row[name]):
                bind(inner)
            setup.append(f"{name} = {ast.unparse(row[name])}")
        elif name in body_assign:
            for inner in _free_names(body_assign[name].value):  # type: ignore[attr-defined]
                bind(inner)
            setup.append(ast.unparse(body_assign[name]))
        elif name in imports:
            text, module = imports[name].split("|", 1)
            if _is_test_module(module):
                raise NotConstructible(f"{name!r} is imported from the test module {module}")
            if text not in import_lines:
                import_lines.append(text)
        elif name in module_assign:
            for inner in _free_names(module_assign[name].value):  # type: ignore[attr-defined]
                bind(inner)
            setup.append(ast.unparse(module_assign[name]))
        elif name in params:
            raise NotConstructible(f"{name!r} is a fixture of {func.name}")
        elif name in local_defs:
            raise NotConstructible(f"{name!r} is defined by the test module itself")
        else:
            raise NotConstructible(f"{name!r} is bound nowhere the rule reads")
        visiting.discard(name)
        placed.add(name)

    for name in _free_names(call):
        bind(name)
    return ProbeSpec(imports="\n".join(import_lines), setup="\n".join(setup),
                     expression=ast.unparse(call))


def derive_contract_probes(
    *, base_tree: Path, anchored: str, symbols: tuple[str, ...], pinned: tuple[str, ...],
    frozen_test: str,
) -> tuple[list[dict], list[dict]]:
    """Rules 1-4 over every contract site the base tree holds for this case."""
    contracts = find_contracts(base_tree=base_tree, head_tree=base_tree, anchored=anchored,
                               symbols=symbols, pinned=pinned, test_source=frozen_test)
    index = tree_index(base_tree)
    module = _module_name(anchored, index)
    roots = tree_roots(base_tree)
    sites: dict[tuple[str, int], dict] = {}
    for c in contracts:
        file, line = c.source.rsplit(":", 1)
        sites.setdefault((file, int(line)), {"kind": c.kind, "call_path": c.call_path})
    probes: list[dict] = []
    refused: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for (file, line), meta in sorted(sites.items()):
        source = (base_tree / file).read_text(encoding="utf-8", errors="replace")
        tree_file = ast.parse(source)
        scope = _bindings(tree_file)
        func = next(
            (n for n in ast.walk(tree_file)
             if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
             and n.lineno <= line <= (n.end_lineno or n.lineno)),
            None,
        )
        statement = next(
            (n for n in ast.walk(func) if isinstance(n, ast.Assert | ast.With)
             and n.lineno == line),
            None,
        ) if func is not None else None
        site = f"{file}:{line}"
        if func is None or statement is None:
            refused.append({"site": site, "row": None, "reason": "no statement at the site"})
            continue
        for statement_node in sorted(
                (n for n in ast.walk(func) if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Name)), key=lambda n: n.lineno):
            name = statement_node.targets[0].id  # type: ignore[attr-defined]
            if isinstance(statement_node.value, ast.Call):
                scope.calls[name] = statement_node.value
            else:
                scope.locals[name] = statement_node.value
        rows = _parametrize(func) if meta["kind"] == "parametrize_row" else [{}]
        for index_row, row in enumerate(rows):
            call: ast.AST | None = None
            if isinstance(statement, ast.Assert) and isinstance(statement.test, ast.Compare):
                # the side whose call is the touched symbol itself, by the finder's own
                # test (`_assertion_contracts`); resolving to the module is not enough --
                # `_Attributes(...)` is in attrs' anchored module too (r1's derivation
                # picked it, and is kept as the record of that mistake)
                for side in (statement.test.left, statement.test.comparators[0]):
                    resolved = _resolve_call(side, scope, row, module)
                    if (resolved is not None and resolved.module == module
                            and (resolved.callee in symbols
                                 or resolved.callee.rsplit(".", 1)[-1] in symbols)):
                        call = side
                        break
            elif isinstance(statement, ast.With):
                caller = meta["call_path"].split(" <- ")[1].split(" (")[0]
                for inner in (n for s in statement.body for n in ast.walk(s)):
                    if not isinstance(inner, ast.Call):
                        continue
                    resolved = _resolve_call(inner, scope, row, "")
                    if resolved is not None and resolved.callee.rsplit(".", 1)[-1] == \
                            caller.rsplit(".", 1)[-1]:
                        call = inner
                        break
            entry = {"site": site, "kind": meta["kind"], "row": index_row}
            if call is None:
                refused.append(entry | {"reason": "no call at the site resolves as the contract"})
                continue
            try:
                spec = build_probe(tree_file=tree_file, func=func, statement=statement,
                                   call=call, row=row)
            except NotConstructible as exc:
                refused.append(entry | {"reason": str(exc)})
                continue
            hygiene = hygiene_refusal(spec)
            if hygiene is not None:
                refused.append(entry | {"reason": f"hygiene: {hygiene}"})
                continue
            if not reaches_the_tree(spec, roots):
                refused.append(entry | {"reason": "the probe imports nothing of the project"})
                continue
            key = (spec.imports, spec.setup, spec.expression)
            if key in seen:
                continue
            seen.add(key)
            probes.append(entry | {"probe": asdict(spec)})
    return probes[:MAX_PROBES_PER_CASE], refused


def cmd_derive(args: argparse.Namespace) -> int:
    """The rule alone, without executing anything: which contracts become probes, which
    do not and why. Written once per run id, before `contracts` executes the same list."""
    forty = {r["unit_id"]: r for r in json.loads(
        (PAIRING / "forty-static-arm-C.json").read_text(encoding="utf-8"))}
    libraries = {str(r["unit_id"]): str(r["library"]) for r in _read_jsonl(STUDY / "sample.jsonl")}
    derived: dict[str, dict] = {}
    for unit_id, static in sorted(forty.items()):
        v6 = (static.get("verdicts") or {}).get(INTENT_POLICY_V6) or {}
        if not v6.get("contracts"):
            continue
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        _checkout(repo, manifest["base_sha"])
        path, _line = static["site"].rsplit(":", 1)
        probes, refused = derive_contract_probes(
            base_tree=repo, anchored=path, symbols=tuple(v6["anchored_symbols"]),
            pinned=tuple(v6["pinned"]),
            frozen_test=_frozen_replay_body(unit_id, libraries[unit_id]),
        )
        derived[unit_id] = {"frozen_probe": static.get("probe"), "probes": probes,
                            "refused": refused}
        print(json.dumps({"unit_id": unit_id, "probes": len(probes), "refused": len(refused)},
                         ensure_ascii=False), flush=True)
        for entry in probes:
            print("   probe", entry["site"], "row", entry["row"], "|",
                  entry["probe"]["expression"][:70], "| setup:",
                  entry["probe"]["setup"].replace("\n", "; ")[:90])
        for entry in refused:
            print("   refused", entry["site"], "row", entry.get("row"), "|", entry["reason"][:110])
    target = OUT / f"contract-probes-{args.run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit(f"{target} exists; a run id is written once")
    target.write_text(json.dumps(derived, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def cmd_contracts(args: argparse.Namespace) -> int:
    forty = {r["unit_id"]: r for r in json.loads(
        (PAIRING / "forty-static-arm-C.json").read_text(encoding="utf-8"))}
    libraries = {str(r["unit_id"]): str(r["library"]) for r in _read_jsonl(STUDY / "sample.jsonl")}
    cases = [u for u, r in forty.items()
             if ((r.get("verdicts") or {}).get(INTENT_POLICY_V6) or {}).get("contracts")]
    out = OUT / f"contracts-{args.run_id}.jsonl"
    derivation = OUT / f"contract-probes-{args.run_id}.json"
    done = {(r["label"], r["policy"]) for r in _read_jsonl(out)}
    derived_all: dict[str, dict] = {}
    for unit_id in sorted(cases):
        static = forty[unit_id]
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        library = libraries[unit_id]
        v6 = static["verdicts"][INTENT_POLICY_V6]
        path, line = static["site"].rsplit(":", 1)
        _checkout(repo, manifest["base_sha"])
        frozen = static.get("probe") or ""
        frozen_test = _frozen_replay_body(unit_id, libraries[unit_id])
        probes, refused = derive_contract_probes(
            base_tree=repo, anchored=path, symbols=tuple(v6["anchored_symbols"]),
            pinned=tuple(v6["pinned"]), frozen_test=frozen_test,
        )
        derived_all[unit_id] = {"frozen_probe": frozen, "probes": probes, "refused": refused}
        print(json.dumps({"unit_id": unit_id, "probes": len(probes), "refused": len(refused),
                          "refusals": [r["reason"][:80] for r in refused][:4]},
                         ensure_ascii=False), flush=True)
        decided = False
        for number, entry in enumerate(probes, 1):
            spec = ProbeSpec(**entry["probe"])
            label = f"{unit_id}/contract-{number}"
            first = None
            if (label, INTENT_POLICY_VERSION) not in done:
                first = execute(run_id=args.run_id, label=label, repo=repo, library=library,
                                base_sha=manifest["base_sha"], head_sha=manifest["head_sha"],
                                path=path, line=int(line), probe=spec,
                                policy=INTENT_POLICY_VERSION)
                first.update({"unit_id": unit_id, "contract_site": entry["site"],
                              "contract_row": entry["row"], "order": number,
                              "decides": (not decided) and bool(first.get("differential_held"))})
                _append(out, first)
                _print(first)
            else:
                first = next(r for r in _read_jsonl(out)
                             if r["label"] == label and r["policy"] == INTENT_POLICY_VERSION)
            if first.get("differential_held") and (label, INTENT_POLICY_V6) not in done:
                second = execute(run_id=args.run_id, label=label, repo=repo, library=library,
                                 base_sha=manifest["base_sha"], head_sha=manifest["head_sha"],
                                 path=path, line=int(line), probe=spec, policy=INTENT_POLICY_V6)
                second.update({"unit_id": unit_id, "contract_site": entry["site"],
                               "contract_row": entry["row"], "order": number,
                               "decides": first.get("decides")})
                _append(out, second)
                _print(second)
            if first.get("differential_held"):
                decided = True
    if not derivation.exists():
        derivation.write_text(json.dumps(derived_all, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    return 0


# --------------------------------------------------------- counterexamples


def _remove_test_functions(source: str, lines: set[int]) -> str:
    """The test file with every test function holding one of ``lines`` removed,
    decorators included."""
    tree = ast.parse(source)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
                node.lineno <= n <= (node.end_lineno or node.lineno) for n in lines):
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            spans.append((start, node.end_lineno or node.lineno))
    kept = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del kept[start - 1:end]
    return "".join(kept)


def cmd_counterexamples(args: argparse.Namespace) -> int:
    records = _read_jsonl(OUT / f"contracts-{args.run_id}.jsonl")
    out = OUT / f"counterexamples-{args.run_id}.jsonl"
    done = {(r["label"], r["policy"]) for r in _read_jsonl(out)}
    accepted = [r for r in records if r["policy"] == INTENT_POLICY_V6
                and r.get("certification") == "accepted"]
    for record in accepted:
        admitted = [c for c in (record["intent"] or {}).get("contracts", []) if c["admitted"]]
        by_file: dict[str, set[int]] = {}
        for c in admitted:
            file, line = c["source"].rsplit(":", 1)
            by_file.setdefault(file, set()).add(int(line))
        unit_id = record["unit_id"]
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        library = record["library"]
        _checkout(repo, manifest["head_sha"])
        for file, lines in by_file.items():
            target = repo / file
            target.write_text(_remove_test_functions(target.read_text(encoding="utf-8"), lines),
                              encoding="utf-8")
        _git(repo, "-c", "user.email=corpus@attest.invalid", "-c", "user.name=attest corpus",
             "commit", "-q", "-am",
             f"counterexample: the mutation and the removal of the tests at "
             f"{', '.join(sorted(c['source'] for c in admitted))}")
        variant = _git(repo, "rev-parse", "HEAD").strip()
        path, line = record["anchor"].rsplit(":", 1)
        spec = ProbeSpec(**record["probe"])
        for policy in POLICIES.values():
            label = f"{record['label']}/intended-change"
            if (label, policy) in done:
                continue
            result = execute(run_id=args.run_id, label=label, repo=repo, library=library,
                             base_sha=manifest["base_sha"], head_sha=variant, path=path,
                             line=int(line), probe=spec, policy=policy)
            result.update({"unit_id": unit_id, "of": record["label"],
                           "removed": sorted(c["source"] for c in admitted),
                           "variant_head": variant})
            _append(out, result)
            _print(result)
    return 0


# --------------------------------------------------------------- controls


def cmd_controls(args: argparse.Namespace) -> int:
    batches = (
        (EVIDENCE / "2026-09-14-lines-on-real-prs-batch3" / "run-d", STUDIES / "e05-external-v3"),
    )
    out = OUT / f"controls-{args.run_id}.jsonl"
    done = {(r["label"], r["policy"]) for r in _read_jsonl(out)}
    for batch_dir, study in batches:
        trials = {r["task_id"]: r for f in study.glob("trials*.jsonl") for r in _read_jsonl(f)}
        sample = {r["unit_id"]: r for r in _read_jsonl(study / "sample.jsonl")}
        for ledger in sorted(batch_dir.glob("*-ledger.jsonl")):
            library = ledger.name.replace("-ledger.jsonl", "")
            for note in (e for e in _read_jsonl(ledger)
                         if e.get("kind") == "value_observation_note"):
                if not note.get("pinned_values") or not (note.get("imports") or note.get("setup")):
                    continue
                trial = trials.get(note.get("task_id"))
                unit = sample.get(trial["unit_id"]) if trial else None
                if unit is None:
                    continue
                repo = CONTROLS / library / "repo"
                spec = ProbeSpec(imports=str(note.get("imports") or ""),
                                 setup=str(note.get("setup") or ""),
                                 expression=str(note.get("expression") or ""))
                label = f"{trial['unit_id']}/note-{note.get('note_id')}"
                for policy in POLICIES.values():
                    if (label, policy) in done:
                        continue
                    result = execute(run_id=args.run_id, label=label, repo=repo,
                                     library=library, base_sha=unit["base_sha"],
                                     head_sha=unit["head_sha"], path=str(note["path"]),
                                     line=int(note["line"]), probe=spec, policy=policy)
                    result.update({"pull_request": trial["unit_id"], "note": note.get("note_id"),
                                   "owner_verdict": "pending adjudication"})
                    _append(out, result)
                    _print(result)
    return 0


# ---------------------------------------------------------------- summary


def _certified(record: dict | None) -> bool:
    return bool(record) and record.get("certification") == "accepted"


def _why(record: dict | None) -> str:
    if not record:
        return "not run"
    if record.get("certification") == "accepted":
        return "certified"
    return str(record.get("intent_verdict") or record.get("reason") or "")[:140]


def cmd_summary(args: argparse.Namespace) -> int:
    """Every table of the report, from the records of one run id alone."""
    summary: dict = {"run_id": args.run_id}
    forty = _read_jsonl(OUT / f"forty-{args.run_id}.jsonl")
    by_case: dict[str, dict[str, dict]] = {}
    for r in forty:
        by_case.setdefault(r["unit_id"], {})[r["policy"]] = r
    recorded = {u: next(iter(p.values())).get("recorded") for u, p in by_case.items()}
    v51 = {u for u, p in by_case.items() if _certified(p.get(INTENT_POLICY_VERSION))}
    v6 = {u for u, p in by_case.items() if _certified(p.get(INTENT_POLICY_V6))}
    arm_c = {u for u, k in recorded.items() if k == "certified"}
    new_v51 = sorted(v51 - arm_c)
    d249 = [u for u in new_v51
            if (by_case[u][INTENT_POLICY_VERSION].get("d249") or {}).get("symbols_changed")
            and by_case[u][INTENT_POLICY_VERSION]["d249"]["verdict_before"] != "publishes"]
    summary["forty"] = {
        "cases": len(by_case),
        "with_a_frozen_probe": sum(1 for p in by_case.values()
                                   if next(iter(p.values())).get("outcome") != "no probe"),
        "arm_c_recorded_certified": len(arm_c),
        "certified_v5.1": len(v51), "certified_v6": len(v6),
        "new_v5.1_vs_arm_c": new_v51, "lost_v5.1_vs_arm_c": sorted(arm_c - v51),
        "new_attributable_to_d249": d249,
        "new_not_attributable_to_d249": sorted(set(new_v51) - set(d249)),
        "v6_gained_over_v5.1": sorted(v6 - v51), "v6_lost_against_v5.1": sorted(v51 - v6),
        "per_case": {u: {"recorded": recorded[u], "v5.1": _why(p.get(INTENT_POLICY_VERSION)),
                         "v6": _why(p.get(INTENT_POLICY_V6))}
                     for u, p in sorted(by_case.items())},
    }
    contracts = _read_jsonl(OUT / f"contracts-{args.run_id}.jsonl")
    derivation_path = OUT / f"contract-probes-{args.run_id}.json"
    derivation = json.loads(derivation_path.read_text()) if derivation_path.exists() else {}
    grid: dict[str, dict] = {}
    for unit_id, derived in sorted(derivation.items()):
        mine = [r for r in contracts if r.get("unit_id") == unit_id]
        decisive = {r["policy"]: r for r in mine if r.get("decides")}
        frozen = by_case.get(unit_id, {})
        cells = {
            "frozen x v5.1": _certified(frozen.get(INTENT_POLICY_VERSION)),
            "frozen x v6": _certified(frozen.get(INTENT_POLICY_V6)),
            "contract x v5.1": _certified(decisive.get(INTENT_POLICY_VERSION)),
            "contract x v6": _certified(decisive.get(INTENT_POLICY_V6)),
        }
        if cells["frozen x v5.1"]:
            depends = "neither: the frozen probe already certifies under the shipped rule"
        elif cells["contract x v5.1"]:
            depends = "the contract probe alone: the shipped rule certifies it"
        elif cells["frozen x v6"]:
            depends = "v6 alone: the frozen probe certifies under v6"
        elif cells["contract x v6"]:
            depends = "both: the contract probe, and v6 admitting its contract"
        else:
            depends = "no cell certifies"
        grid[unit_id] = {
            "probes_constructed": len(derived["probes"]),
            "not_constructible": [r["reason"] for r in derived["refused"]],
            "probes_executed_v5.1": sum(1 for r in mine if r["policy"] == INTENT_POLICY_VERSION),
            "differentials_held": sum(1 for r in mine if r["policy"] == INTENT_POLICY_VERSION
                                      and r.get("differential_held")),
            "decisive_probe": (decisive.get(INTENT_POLICY_VERSION) or {}).get("probe"),
            "cells": cells,
            "why": {
                "frozen x v5.1": _why(frozen.get(INTENT_POLICY_VERSION)),
                "frozen x v6": _why(frozen.get(INTENT_POLICY_V6)),
                "contract x v5.1": _why(decisive.get(INTENT_POLICY_VERSION)),
                "contract x v6": _why(decisive.get(INTENT_POLICY_V6)),
            },
            "contracts_on_the_decisive_v6_run": [
                {k: c[k] for k in ("kind", "source", "input", "derived", "input_bound",
                                   "evaluated", "path_bound", "standing_at_head", "admitted",
                                   "reason")}
                for c in ((decisive.get(INTENT_POLICY_V6) or {}).get("intent") or {}).get(
                    "contracts", [])
            ],
            "other_probes_certified_counted_nowhere": sorted(
                f"{r['label']} under {r['policy']}" for r in mine
                if _certified(r) and not r.get("decides")),
            "new_certification_depends_on": depends,
        }
    summary["contracts"] = grid
    counter = _read_jsonl(OUT / f"counterexamples-{args.run_id}.jsonl")
    summary["counterexamples"] = [
        {"label": r["label"], "policy": r["policy"], "removed": r.get("removed"),
         "certified": _certified(r), "why": _why(r),
         "contracts": [{k: c[k] for k in ("source", "standing_at_head", "admitted", "reason")}
                       for c in (r.get("intent") or {}).get("contracts", [])]}
        for r in counter
    ]
    controls = _read_jsonl(OUT / f"controls-{args.run_id}.jsonl")
    summary["controls"] = [
        {"label": r["label"], "policy": r["policy"], "certified": _certified(r), "why": _why(r)}
        for r in controls
    ]
    target = OUT / f"summary-{args.run_id}.json"
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:6000])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("forty", cmd_forty), ("derive", cmd_derive), ("contracts", cmd_contracts),
                       ("counterexamples", cmd_counterexamples), ("controls", cmd_controls),
                       ("summary", cmd_summary)):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.add_argument("--only", default="")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
