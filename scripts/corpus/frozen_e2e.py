"""The free end-to-end acceptance of D-254: the product's whole review path on ledger-frozen
proposals and ledger-frozen model probes, shipped against experimental.

Why ledger-frozen and not the recorded proposals themselves: the paid runs uploaded their
ledgers and nothing else -- neither the candidate store (`.attest/candidates.jsonl`) nor the
model's responses left the runner -- so the claim text, the exact anchor line and every
non-eligible candidate of a recorded run are gone. What the ledger does keep, per task, is
enough to freeze the part of discovery that verification depends on:

    every eligible candidate      its change unit, its symbol, its cluster size and its score
                                  (`verification_ranking.order`)
    the model probe it was given  the probe that produced the differential, verbatim
                                  (`probe_observation`: imports, setup, expression)
    the cost of the stages        tokens by stage (`review_run.spend_breakdown`)

`FrozenProvider` answers the review exactly from those facts and nothing else:

  * a **proposal** call for a change unit returns, for sample *i*, every recorded eligible
    candidate of that unit whose cluster size exceeds *i*, anchored by a fixed rule (the first
    hunk line inside the recorded symbol on head, an added line first) and named by one token
    unique to it (`frozen<finding id>`), so the product's own dedup rebuilds the recorded
    clusters and nothing merges that was apart;
  * a **probe** call for a candidate returns its recorded probe once, and refuses every further
    call -- the search's earlier attempts were never recorded, so a candidate whose recorded
    search found no differential gets no probe at all;
  * every call is charged the recorded per-call tokens of its stage, so the budget sees the
    recorded spend.

Nothing here reads a mutation's answer: `run` takes each case's repository, base and head from
its manifest and its candidates from the arm C ledger. Only `score`, after every review, reads
the planted site -- to decide whether a published receipt is the planted defect, and at which
stage a case that did not publish lost it.

Arms: **S** is the shipped path (no contract search, `attest.intent.v5.1`); **E** is the
experimental one (`contract_probes = True`, `attest.intent.v6`). Both on identical frozen input.

    .venv/bin/python scripts/corpus/frozen_e2e.py forty --run-id f1 --arm S
    .venv/bin/python scripts/corpus/frozen_e2e.py forty --run-id f1 --arm E
    .venv/bin/python scripts/corpus/frozen_e2e.py counterexamples --run-id f1 --arm E
    .venv/bin/python scripts/corpus/frozen_e2e.py controls --run-id f1 --arm E
    .venv/bin/python scripts/corpus/frozen_e2e.py score --run-id f1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from mutation_recall import STUDY, WORK, classify  # noqa: E402

from attest.certification.intent import INTENT_POLICY_V6, INTENT_POLICY_VERSION  # noqa: E402
from attest.review.config import load_config  # noqa: E402
from attest.review.diffs import DiffInfo, parse_diff  # noqa: E402
from attest.review.intent import symbol_ranges  # noqa: E402
from attest.review.proposer import ProviderResult  # noqa: E402
from attest.review.run import run_review  # noqa: E402

OUT = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-frozen-e2e"
ARM_C = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-14-probe-arms" / "arm-C"
BATCH3 = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-14-lines-on-real-prs-batch3" / "run-d"
E05_V3 = ROOT / "benchmarks" / "studies" / "e05-external-v3"
CONTROLS = ROOT / ".attest" / "corpora" / "e05-controls"
PAIRING = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-container-pairing"
ARMS = {
    "S": {"contract_probes": False, "intent_policy": INTENT_POLICY_VERSION},
    "E": {"contract_probes": True, "intent_policy": INTENT_POLICY_V6},
    "C51": {"contract_probes": True, "intent_policy": INTENT_POLICY_VERSION},
    "V6": {"contract_probes": False, "intent_policy": INTENT_POLICY_V6},
}
K_SAMPLES = 5
BUDGET_USD = 1.00
VERIFICATION_TIMEOUT_S = 900.0
_CLAIM = re.compile(r"frozen([0-9a-f]{10})")
_UNIT_HEADER = re.compile(r"^\+\+\+ b/(\S+)$", re.MULTILINE)


# ------------------------------------------------------------------- io


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:300]}")
    return done.stdout


def _checkout(repo: Path, sha: str) -> None:
    _git(repo, "checkout", "-q", "--", ".")
    _git(repo, "checkout", "-q", "--detach", sha)


# ------------------------------------------------------- the frozen input


@dataclass(frozen=True)
class FrozenCandidate:
    finding_id: str  # the recorded run's
    unit: str
    symbol: str
    cluster_size: int
    score: int


@dataclass
class FrozenTask:
    recorded_task: str
    candidates: list[FrozenCandidate]
    probes: dict[str, dict[str, str]]  # recorded finding id -> probe
    per_call: dict[str, dict[str, int]]  # stage -> tokens per call
    recorded: dict[str, Any]


def frozen_task(rows: list[dict], recorded_task: str) -> FrozenTask:
    """What the recorded run's ledger keeps about one task, and nothing more."""
    mine = [r for r in rows if r.get("task_id") == recorded_task]
    ranking = next((r for r in mine if r.get("kind") == "verification_ranking"), None)
    candidates = [
        FrozenCandidate(finding_id=str(o["finding_id"]), unit=str(o["unit"]),
                        symbol=str(o.get("symbol") or ""), cluster_size=int(o["cluster_size"]),
                        score=int(o.get("score") or 0))
        for o in (ranking or {}).get("order", [])
    ]
    probes = {}
    for r in mine:
        if r.get("kind") == "probe_observation" and r.get("expression"):
            probes[str(r["finding_id"])] = {"imports": str(r.get("imports") or ""),
                                            "setup": str(r.get("setup") or ""),
                                            "expression": str(r["expression"])}
    run_row = next((r for r in mine if r.get("kind") == "review_run"), {})
    per_call: dict[str, dict[str, int]] = {}
    for stage, spend in (run_row.get("spend_breakdown") or {}).items():
        calls = int(spend.get("calls") or 0)
        if calls <= 0:
            continue
        per_call[stage] = {
            key: int(spend.get(key) or 0) // calls
            for key in ("input_tokens", "cache_creation_input_tokens",
                        "cache_read_input_tokens", "output_tokens")
        }
    coverage = next((r for r in mine if r.get("kind") == "proposal_coverage"), {})
    recorded = {
        "eligibility_rows": sum(1 for r in mine if r.get("kind") == "eligibility"),
        "eligible": len(candidates),
        "below_cap": (ranking or {}).get("below_cap", 0),
        "units_read": coverage.get("units_read"),
        "units_planned": coverage.get("units_planned"),
        "budget_limited": coverage.get("budget_limited"),
        "spend_usd": run_row.get("spend_usd"),
        "certified": [r.get("finding_id") for r in mine
                      if r.get("kind") == "certification" and r.get("outcome") == "accepted"],
        "recorded_probes": sorted(probes),
    }
    return FrozenTask(recorded_task, candidates, probes, per_call, recorded)


def anchor_line(diff: DiffInfo, head_source: str, unit: str, symbol: str) -> int | None:
    """The fixed anchor rule: the first line of the unit's hunks inside the recorded symbol
    on head -- an added line first -- else the first added line, else the first hunk line."""
    ranges = diff.hunks.get(unit) or []
    lines = sorted({line for start, end in ranges for line in range(start, end + 1)})
    if not lines:
        return None
    added = diff.added_lines.get(unit, set())
    spans = [(s, e) for name, s, e in (symbol_ranges(head_source) or ()) if name == symbol]
    inside = [line for line in lines if any(s <= line <= e for s, e in spans)]
    for pool in ([n for n in inside if n in added], inside, [n for n in lines if n in added],
                 lines):
        if pool:
            return pool[0]
    return None


class FrozenProvider:
    """Answers a review from the recorded ledger alone (see the module docstring)."""

    def __init__(self, task: FrozenTask, diff: DiffInfo, head_sources: dict[str, str]) -> None:
        self.task = task
        self.anchors: dict[str, tuple[str, int]] = {}
        self.unanchored: list[str] = []
        for c in task.candidates:
            line = anchor_line(diff, head_sources.get(c.unit, ""), c.unit, c.symbol)
            if line is None:
                self.unanchored.append(c.finding_id)
            else:
                self.anchors[c.finding_id] = (c.unit, line)
        self._lock = threading.Lock()
        self._proposal_calls: dict[str, int] = {}
        self._probes_served: set[str] = set()
        self.log: list[dict[str, Any]] = []

    @staticmethod
    def claim(finding_id: str) -> str:
        return f"frozen{finding_id}"

    def new_finding_id(self, finding_id: str) -> str | None:
        anchored = self.anchors.get(finding_id)
        if anchored is None:
            return None
        key = f"{anchored[0]}:{anchored[1]}:{self.claim(finding_id)}".encode()
        return hashlib.sha256(key).hexdigest()[:10]

    def _usage(self, stage: str, text: str | None) -> ProviderResult:
        tokens = self.task.per_call.get(stage, {})
        return ProviderResult(
            text=text,
            input_tokens=tokens.get("input_tokens", 0),
            output_tokens=tokens.get("output_tokens", 0),
            stop_reason="end_turn",
            cache_creation_input_tokens=tokens.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=tokens.get("cache_read_input_tokens", 0),
        )

    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int, *,
               timeout_s: float | None = None) -> ProviderResult:
        del system, max_tokens, timeout_s
        properties = schema.get("properties", {})
        if "findings" in properties:
            units = set(_UNIT_HEADER.findall(prompt))
            key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            with self._lock:
                index = self._proposal_calls.get(key, 0)
                self._proposal_calls[key] = index + 1
            findings = []
            for c in self.task.candidates:
                if (c.unit not in units or c.cluster_size <= index
                        or c.finding_id not in self.anchors):
                    continue
                unit, line = self.anchors[c.finding_id]
                findings.append({"claim": self.claim(c.finding_id),
                                 "anchor": {"file": unit, "line": line},
                                 "failure_scenario": self.claim(c.finding_id),
                                 "falsification_plan": "the recorded candidate"})
            with self._lock:
                self.log.append({"stage": "proposal", "units": sorted(units), "sample": index,
                                 "findings": [f["claim"] for f in findings]})
            return self._usage("discovery", json.dumps({"findings": findings}))
        if "expression" in properties:
            match = _CLAIM.search(prompt)
            recorded = match.group(1) if match else ""
            with self._lock:
                already = recorded in self._probes_served
                probe = self.task.probes.get(recorded)
                served = probe is not None and not already
                if served:
                    self._probes_served.add(recorded)
                self.log.append({"stage": "probe", "candidate": recorded, "served": served,
                                 "why": "" if served else
                                 ("already served: the search's later attempts were never "
                                  "recorded" if already else
                                  "no probe was recorded for this candidate")})
            if not served:
                raise RuntimeError("frozen: no recorded probe for this call")
            return self._usage("probe", json.dumps(probe))
        with self._lock:
            self.log.append({"stage": "other", "properties": sorted(properties)})
        raise RuntimeError("frozen: this stage was not recorded")


# ------------------------------------------------------------ one review


def review(
    *, repo: Path, base_sha: str, head_sha: str, task: FrozenTask, arm: str, task_id: str,
) -> dict:
    _checkout(repo, head_sha)
    diff = parse_diff(_git(repo, "diff", "--no-color", base_sha))
    head_sources = {}
    for c in task.candidates:
        try:
            head_sources[c.unit] = (repo / c.unit).read_text(encoding="utf-8", errors="replace")
        except OSError:
            head_sources[c.unit] = ""
    provider = FrozenProvider(task, diff, head_sources)
    config = load_config(repo)
    config = config.__class__(**{
        **config.__dict__,
        "k_samples": K_SAMPLES, "budget_usd": BUDGET_USD,
        "value_notes_visible": True,
        # the gate level buys generations the recorded ledger never kept
        "gate_notes_visible": False, "gate_shadow": False,
        # one clone serves many reviews; a history-dependent alpha would leak between them
        "auto_tighten_alpha": False,
        **ARMS[arm],
    })
    # every review pays its own frozen calls: the proposer's attempt cache would otherwise
    # replay an earlier review's identical prompts for free and hand this arm a larger
    # budget than the other (run f1 found it). The earlier cache is kept, moved aside.
    attempts = repo / ".attest" / "cache" / "attempts"
    if attempts.is_dir():
        attempts.rename(attempts.with_name(f"attempts-before-{task_id}"))
    started = time.monotonic()
    run = run_review(repo, base_sha, config, provider, task_id=task_id, verify=True,
                     verification_timeout_s=VERIFICATION_TIMEOUT_S)
    rows = [r for r in _read_jsonl(repo / ".attest" / "ledger.jsonl")
            if r.get("task_id") == task_id]
    mapping = {provider.new_finding_id(c.finding_id): c.finding_id for c in task.candidates}
    ranking = next((r for r in rows if r.get("kind") == "verification_ranking"), {})
    rebuilt = sorted((o["unit"], o.get("symbol") or "", o["cluster_size"])
                     for o in ranking.get("order", []))
    recorded = sorted((c.unit, c.symbol, c.cluster_size) for c in task.candidates)
    return {
        "arm": arm, "task_id": task_id, "recorded_task": task.recorded_task,
        "base_sha": base_sha, "head_sha": head_sha,
        "elapsed_s": round(time.monotonic() - started, 1),
        "spend_usd": round(run.budget.spent_usd, 6),
        "deferred_reason": run.deferred_reason,
        "published": [f.accepted_receipt.receipt.candidate_id for f in run.published],
        "certified": [f.accepted_receipt.receipt.candidate_id for f in run.certified],
        "finding_map": {k: v for k, v in mapping.items() if k},
        "unanchored": provider.unanchored,
        "fidelity": {"recorded_eligible": recorded, "rebuilt_eligible": rebuilt,
                     "same": recorded == rebuilt, "recorded": task.recorded},
        "provider_log": provider.log,
        "attempt_cache": "isolated: an earlier cache was moved aside before this review",
        "protocol_refusals": sum(
            1 for r in rows if r.get("kind") == "verification"
            for e in (r.get("run_evidence") or [])
            if "unsafe name" in str(e.get("reason", ""))
        ),
        "rows": rows,
    }


def _summary_line(label: str, record: dict) -> str:
    kinds = [r.get("kind") for r in record["rows"]]
    probes = [(r.get("source"), r.get("origin")) for r in record["rows"]
              if r.get("kind") == "probe_observation"]
    return json.dumps({"label": label, "arm": record["arm"], "elapsed_s": record["elapsed_s"],
                       "certified": len(record["certified"]),
                       "published": len(record["published"]),
                       "verifications": kinds.count("verification"), "probes": probes,
                       "fidelity": record["fidelity"]["same"],
                       "deferred": (record["deferred_reason"] or "")[:80]}, ensure_ascii=False)


# ----------------------------------------------------------------- populations


def _trial_tasks(path: Path) -> dict[str, str]:
    return {r["unit_id"]: r["task_id"] for r in _read_jsonl(path)}


def cmd_forty(args: argparse.Namespace) -> int:
    tasks = _trial_tasks(ARM_C / "trials-arm-C.jsonl")
    out = OUT / f"forty-{args.run_id}-{args.arm}.jsonl"
    done = {r["label"] for r in _read_jsonl(out)}
    ledgers: dict[str, list[dict]] = {}
    only = {s for s in args.only.split(",") if s}
    for row in _read_jsonl(STUDY / "sample.jsonl"):
        unit_id, library = str(row["unit_id"]), str(row["library"])  # no mutation field is read
        if unit_id in done or (only and unit_id not in only):
            continue
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        if library not in ledgers:
            ledgers[library] = _read_jsonl(ARM_C / f"{library}-ledger.jsonl")
        task = frozen_task(ledgers[library], tasks[unit_id])
        record = review(repo=Path(manifest["repo_path"]), base_sha=manifest["base_sha"],
                        head_sha=manifest["head_sha"], task=task, arm=args.arm,
                        task_id=f"fe-{args.run_id}-{args.arm}-{unit_id}")
        record["label"] = unit_id
        _append(out, record)
        print(_summary_line(unit_id, record), flush=True)
    return 0


def cmd_counterexamples(args: argparse.Namespace) -> int:
    """The intended-change variants of the container pairing, kept as they were built:
    each is the mutation plus the removal of the test an admitted contract stood on."""
    tasks = _trial_tasks(ARM_C / "trials-arm-C.jsonl")
    variants = {}
    for r in _read_jsonl(PAIRING / "counterexamples-r2.jsonl"):
        variants.setdefault(r["variant_head"], r)
    out = OUT / f"counterexamples-{args.run_id}-{args.arm}.jsonl"
    done = {r["label"] for r in _read_jsonl(out)}
    for variant_head, r in sorted(variants.items(), key=lambda kv: kv[1]["label"]):
        unit_id = r["unit_id"]
        label = f"{unit_id}@{variant_head[:12]}"
        if label in done:
            continue
        manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
        library = next(x["library"] for x in _read_jsonl(STUDY / "sample.jsonl")
                       if x["unit_id"] == unit_id)
        task = frozen_task(_read_jsonl(ARM_C / f"{library}-ledger.jsonl"), tasks[unit_id])
        record = review(repo=Path(manifest["repo_path"]), base_sha=manifest["base_sha"],
                        head_sha=variant_head, task=task, arm=args.arm,
                        task_id=f"fe-{args.run_id}-{args.arm}-cx-{variant_head[:12]}")
        record.update({"label": label, "unit_id": unit_id, "removed": r.get("removed")})
        _append(out, record)
        print(_summary_line(label, record), flush=True)
    return 0


def cmd_controls(args: argparse.Namespace) -> int:
    """Batch 3's 24 merged pull requests: real traffic no rule of D-252..D-254 was built on."""
    tasks = _trial_tasks(E05_V3 / "trials.jsonl")
    out = OUT / f"controls-{args.run_id}-{args.arm}.jsonl"
    done = {r["label"] for r in _read_jsonl(out)}
    ledgers: dict[str, list[dict]] = {}
    for row in _read_jsonl(E05_V3 / "sample.jsonl"):
        unit_id = str(row["unit_id"])
        if unit_id in done or unit_id not in tasks:
            continue
        library = str(row["repository"]).split("/")[1]
        repo = CONTROLS / library / "repo"
        if library not in ledgers:
            ledgers[library] = _read_jsonl(BATCH3 / f"{library}-ledger.jsonl")
        task = frozen_task(ledgers[library], tasks[unit_id])
        record = review(repo=repo, base_sha=row["base_sha"], head_sha=row["head_sha"], task=task,
                        arm=args.arm,
                        # the execution protocol accepts only a safe path component as a
                        # task id; `#` in a pull request's id made run f2's controls defer
                        # every probe run before it started (kept, and marked invalid)
                        task_id=re.sub(r"[^A-Za-z0-9._-]", "_",
                                       f"fe-{args.run_id}-{args.arm}-{unit_id}"))
        record["label"] = unit_id
        _append(out, record)
        print(_summary_line(unit_id, record), flush=True)
    return 0


# ---------------------------------------------------------------------- scoring


def _loss_stage(record: dict, site: tuple[str, int]) -> tuple[str, str]:
    """Where a forty case that did not publish its planted defect lost it (the scorer reads
    the site; the review never did)."""
    rows = record["rows"]
    path, _line = site
    klass, why = classify(rows, str(record.get("deferred_reason") or ""), site=site)
    certified_here = [r.get("finding_id") for r in rows
                      if r.get("kind") == "certification" and r.get("outcome") == "accepted"]
    on_site = []
    for fid in certified_here:
        v = next((r for r in rows if r.get("kind") == "verification"
                  and r.get("finding_id") == fid), {})
        intent = v.get("intent") or {}
        lines = intent.get("changed_lines") or []
        if intent.get("path") == path and lines and min(lines) <= site[1] <= max(lines):
            on_site.append(fid)
    if on_site and any(fid in record["published"] for fid in on_site):
        return "published on the planted hunk", ""
    if on_site:
        return "publication: certified on the hunk and suppressed", json.dumps(
            next((r.get("suppressed") for r in rows if r.get("kind") == "publication_policy"),
                 []))[:200]
    ranking = next((r for r in rows if r.get("kind") == "verification_ranking"), {})
    in_unit = [o for o in ranking.get("order", []) if o.get("unit") == path]
    if not in_unit:
        coverage = next((r for r in rows if r.get("kind") == "proposal_coverage"), {})
        if path in " ".join(coverage.get("units_unread") or []):
            return "budget: the unit was never read", str(coverage.get("budget_shortfall"))
        return "discovery: no eligible candidate on the planted unit", ""
    verified = [r for r in rows if r.get("kind") == "verification"
                and r.get("finding_id") in {o["finding_id"] for o in in_unit}]
    if not verified:
        refused = next((r for r in rows if r.get("kind") == "verification_ranking"), {})
        if refused.get("below_cap"):
            return "ranking: below the per-unit cap", ""
        return "budget or deadline: no verification was bought", str(record.get("deferred_reason"))
    reasons = " || ".join(str(v.get("reason", "")) for v in verified)
    if "deadline" in reasons or "budget" in reasons.lower():
        return "budget or deadline during verification", reasons[:200]
    if any(v.get("intent") for v in verified):
        return "intent: the differential held and the rule drawered it", reasons[:200]
    if "generation failed" in reasons or "frozen" in reasons:
        return "search: no recorded probe to give the candidate", reasons[:200]
    if klass == "certified elsewhere":
        return "certified elsewhere", why[:200]
    return "search: no probe made the revisions differ", reasons[:200]


def cmd_score(args: argparse.Namespace) -> int:
    sample = {r["unit_id"]: r for r in _read_jsonl(STUDY / "sample.jsonl")}
    summary: dict[str, Any] = {"run_id": args.run_id}
    per_arm: dict[str, dict[str, dict]] = {}
    for arm in ARMS:
        records = {r["label"]: r for r in _read_jsonl(OUT / f"forty-{args.run_id}-{arm}.jsonl")}
        if not records:
            continue
        cases = {}
        for unit_id, record in records.items():
            mutation = sample[unit_id]["mutation"]
            site = (str(mutation["path"]), int(mutation["line"]))
            stage, detail = _loss_stage(record, site)
            contract_rows = [r for r in record["rows"] if r.get("kind") == "contract_search"]
            probes = [(r.get("source"), r.get("origin")) for r in record["rows"]
                      if r.get("kind") == "probe_observation"]
            cases[unit_id] = {
                "stage": stage, "detail": detail, "fidelity": record["fidelity"]["same"],
                "unanchored": record["unanchored"], "spend_usd": record["spend_usd"],
                "elapsed_s": record["elapsed_s"],
                "probes": probes,
                "contract_probes_built": sum(len(r.get("probes", [])) for r in contract_rows),
                "contract_refused": sum(int(r.get("refused_count") or 0) for r in contract_rows),
                "contract_chosen": [r.get("chosen") for r in contract_rows if r.get("chosen")],
                "published": len(record["published"]),
            }
        per_arm[arm] = cases
        hits = sorted(u for u, c in cases.items() if c["stage"] == "published on the planted hunk")
        stages: dict[str, int] = {}
        for c in cases.values():
            stages[c["stage"]] = stages.get(c["stage"], 0) + 1
        summary[arm] = {
            "cases": len(cases), "published_on_the_planted_hunk": len(hits), "hits": hits,
            "stages": stages,
            "fidelity_mismatches": sorted(u for u, c in cases.items() if not c["fidelity"]),
            "spend_usd": round(sum(float(c["spend_usd"]) for c in cases.values()), 6),
        }
    if "S" in per_arm and "E" in per_arm:
        s_hits = set(summary["S"]["hits"])
        e_hits = set(summary["E"]["hits"])
        summary["E_vs_S"] = {"gained": sorted(e_hits - s_hits), "lost": sorted(s_hits - e_hits)}
    for population in ("counterexamples", "controls"):
        for arm in ARMS:
            records = _read_jsonl(OUT / f"{population}-{args.run_id}-{arm}.jsonl")
            if not records:
                continue
            by_case: dict[str, dict] = {}
            for r in records:
                case = r.get("unit_id") or r["label"]
                entry = by_case.setdefault(case, {"reviews": 0, "published": 0, "certified": 0,
                                                  "labels": []})
                entry["reviews"] += 1
                entry["published"] += len(r["published"])
                entry["certified"] += len(r["certified"])
                entry["labels"].append(r["label"])
            summary[f"{population}_{arm}"] = {
                "independent_cases": len(by_case),
                "cases_with_a_publication": sorted(c for c, e in by_case.items() if e["published"]),
                "reviews": len(records),
                "per_case": by_case,
            }
    summary["per_case"] = per_arm
    target = OUT / f"score-{args.run_id}.json"
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    brief = {k: v for k, v in summary.items() if k != "per_case"}
    print(json.dumps(brief, indent=2, ensure_ascii=False)[:8000])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("forty", cmd_forty), ("counterexamples", cmd_counterexamples),
                       ("controls", cmd_controls)):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.add_argument("--arm", required=True, choices=sorted(ARMS))
        p.add_argument("--only", default="")
        p.set_defaults(func=func)
    s = sub.add_parser("score")
    s.add_argument("--run-id", required=True)
    s.set_defaults(func=cmd_score)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
