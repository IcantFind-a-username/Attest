"""mutations-v1-recall: the first red-level recall measurement on a fair corpus (owner
authorisation 2 of 2026-09-13, work order PR 2 d).

The population is D-231's `mutations-v1`: crash mutations injected on lines each of
eight public libraries' own tests reach, on the development host, never committed.
This study freezes a **stratified random sample of 40 forward cases** -- base = the
library's tip, head = the mutation, the pull request that introduces the defect --
five per library under a seed written into the preregistration, and reviews each
on the declared CI platform through the local review path (no GitHub client, nothing
written anywhere) at the factory settings, K=5 and $1.00 per unit, under a hard
cumulative cap.

    sample   from the local corpus's manifest.jsonl: the 40 cases, with the mutation
             site each one is re-created from (kind, path, line, replacement, span)
             and the library tip it is applied to -- recorded before any unit runs
    build    on the runner: clone each library, check out the recorded tip, re-apply
             the recorded mutation as one commit, write the case manifest
    run      one review per sampled case, in the frozen order, under the cap
    table    what each case's own ledger says: certified (numerator), sent to the
             drawer by D-232 (a rejection on a line the mutation wrote), the value
             class, refused, or no receipt -- with the Wilson interval over 40

The denominator is the sample: 40. A case the cap refuses is a miss that is named,
not a smaller n. The same table says how many of the 40 defects D-232 reads as a
behaviour change with unknown intent, which is the number the owner asked to see.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from driver_budget import DriverCap  # noqa: E402
from heldout_v2 import wilson  # noqa: E402  -- one Wilson interval, kept in one place
from mutate import Site, _apply  # noqa: E402

from attest.benchmark import prospective  # noqa: E402

STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
CORPUS = ROOT / ".attest" / "corpora" / "mutations-v1"  # D-231's local build
WORK = ROOT / ".attest" / "corpora" / "mutations-v1-recall"  # the runner's clones and cases
PER_LIBRARY = 5
REPOSITORIES = {
    "attrs": "python-attrs/attrs",
    "click": "pallets/click",
    "itsdangerous": "pallets/itsdangerous",
    "jinja": "pallets/jinja",
    "more-itertools": "more-itertools/more-itertools",
    "packaging": "pypa/packaging",
    "python-dotenv": "theskumar/python-dotenv",
    "urllib3": "urllib3/urllib3",
}
# D-232's drawer, as the verification row words it
FRAME_RULE_MARKERS = ("on a changed line", "reached through a changed line")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        # the stderr is the reason; a CalledProcessError without it said nothing
        # when the first paid dispatch died on the 19th case (run 34665205269)
        raise RuntimeError(f"git {' '.join(args)} failed ({done.returncode}): {done.stderr.strip()[:400]}")
    return done.stdout.strip()


def _checkout_case(repo: Path, sha: str) -> str | None:
    """Check the case's head out, restoring the tree first; the reason when it cannot.

    The eight clones are shared by five cases each and the review leaves what
    it leaves in the working tree. A case whose checkout fails is skipped **by
    name** and the run goes on: the first paid dispatch aborted at its 19th
    case on exactly this and recorded 18 of 40."""
    for attempt in ("plain", "restored"):
        try:
            if attempt == "restored":
                _git(repo, "checkout", "-q", "--", ".")
            _git(repo, "checkout", "-q", "--detach", sha)
            return None
        except RuntimeError as exc:
            reason = str(exc)
    return reason


def _read_jsonl(path: Path) -> list[dict]:
    return prospective._read_jsonl(path)


def cmd_sample(args: argparse.Namespace) -> int:
    manifests = _read_jsonl(CORPUS / "manifest.jsonl")
    assert manifests, f"no corpus at {CORPUS}: build it with scripts/corpus/mutate.py first"
    forward = [m for m in manifests if str(m["instance_id"]).endswith("--forward")]
    preregistration = json.loads((STUDY / "preregistration.json").read_text(encoding="utf-8"))
    seed = int(preregistration["silent_audit_seed"])
    per_library = int(preregistration.get("per_library", PER_LIBRARY))
    rows: list[dict[str, object]] = []
    recorded_at = datetime.now(UTC).isoformat()
    for library in sorted(REPOSITORIES):
        pool = sorted(
            (m for m in forward if m["repo"] == library), key=lambda m: str(m["instance_id"])
        )
        assert pool, f"no forward case for {library}"
        chosen = random.Random(f"{seed}:{library}").sample(pool, k=min(per_library, len(pool)))
        for m in sorted(chosen, key=lambda m: str(m["instance_id"])):
            rows.append(
                {
                    "unit_id": m["instance_id"],
                    "repository": REPOSITORIES[library],
                    "library": library,
                    "tip": m["tip"],
                    "mutation": m["mutation"],
                    "shape": m["shape"],
                    "stratum": m["mutation"]["kind"],
                    "recorded_at": recorded_at,
                    "prospective": False,
                    "silent_audit_inclusion_probability": 1.0,
                    "selected_for_silent_audit": True,
                    "local_head_sha": m["head_sha"],
                }
            )
    # round-robin across libraries in name order, as every stratum before it
    by_library: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_library.setdefault(str(row["library"]), []).append(row)
    ordered: list[dict[str, object]] = []
    index = 0
    while any(index < len(group) for group in by_library.values()):
        for name in sorted(by_library):
            if index < len(by_library[name]):
                ordered.append(by_library[name][index])
        index += 1
    sample = STUDY / "sample.jsonl"
    if sample.exists() and not args.force:
        raise SystemExit(f"{sample} exists; the sample is frozen (pass --force to rewrite)")
    sample.write_text(
        "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in ordered),
        encoding="utf-8",
    )
    counts = Counter(str(r["library"]) for r in ordered)
    kinds = Counter(str(r["stratum"]) for r in ordered)
    print(f"{len(ordered)} cases -> {sample}; per library {dict(counts)}; by class {dict(kinds)}")
    return 0


def _clone_dir(library: str) -> Path:
    return WORK / library / "repo"


def cmd_build(_args: argparse.Namespace) -> int:
    sample = _read_jsonl(STUDY / "sample.jsonl")
    assert sample, "the sample is empty"
    built = 0
    for row in sample:
        library = str(row["library"])
        repo = _clone_dir(library)
        case = WORK / "cases" / str(row["unit_id"])
        manifest = case / "manifest.json"
        if manifest.is_file():
            built += 1
            continue
        if not (repo / ".git").is_dir():
            print(json.dumps({"unit_id": row["unit_id"], "build": "no clone"}), flush=True)
            continue
        try:
            _git(repo, "checkout", "-q", "--", ".")
            _git(repo, "checkout", "-q", "--detach", str(row["tip"]))
        except RuntimeError as exc:
            print(json.dumps({"unit_id": row["unit_id"], "build": "tip not in clone",
                              "detail": str(exc)[:200]}), flush=True)
            continue
        site = Site(**{k: v for k, v in row["mutation"].items() if k != "span"},
                    span=tuple(row["mutation"]["span"]))
        if not _apply(repo, site):
            print(json.dumps({"unit_id": row["unit_id"], "build": "mutation does not parse"}),
                  flush=True)
            _git(repo, "checkout", "-q", "--", ".")
            continue
        _git(repo, "-c", "user.email=corpus@attest.invalid", "-c", "user.name=attest corpus",
             "commit", "-q", "-am", f"mutation {site.kind} at {site.path}:{site.line}")
        head = _git(repo, "rev-parse", "HEAD")
        case.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"instance_id": row["unit_id"], "repo": library,
                        "repository": row["repository"], "repo_path": str(repo),
                        "base_sha": row["tip"], "head_sha": head, "shape": row["shape"],
                        "mutation": row["mutation"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        built += 1
        print(json.dumps({"unit_id": row["unit_id"], "build": "ok", "head": head[:12]}),
              flush=True)
    print(f"built {built} of {len(sample)} sampled cases")
    return 0 if built == len(sample) else 1


def cmd_run(args: argparse.Namespace) -> int:
    from prospective_shadow import _author_visible_lines

    from attest.review.config import load_config
    from attest.review.proposer import ApiProvider
    from attest.review.run import run_review

    preregistration = prospective.load_preregistration(STUDY)
    sample = _read_jsonl(STUDY / "sample.jsonl")
    assert sample, "the sample is empty"
    trials_path = STUDY / (args.trials_file or prospective.TRIALS_FILE)
    lines_path = STUDY / f"lines-{trials_path.stem}.jsonl"
    done = {row["unit_id"] for row in _read_jsonl(trials_path)}
    pending = [row for row in sample if str(row["unit_id"]) not in done]
    if args.limit:
        pending = pending[: args.limit]
    unit_budget = args.unit_budget or preregistration.per_pr_budget_usd
    reserve = args.reserve or len(pending) * unit_budget
    preflight = prospective.preflight_prospective(
        STUDY, devspend_path=ROOT / "DEVSPEND.md", env=os.environ,
        allow_paid_api=args.allow_paid_api, reserve_usd=reserve,
    )
    print(json.dumps(preflight.to_json_dict()), flush=True)
    cap = DriverCap(
        cap=min(preregistration.cost_cap_usd, args.reserve) if args.reserve
        else preregistration.cost_cap_usd,
        reservation_usd=unit_budget,
        spent=sum(float(r.get("spend_usd", 0.0)) for r in _read_jsonl(trials_path)),
    )
    unbought: list[str] = []
    for row in pending:
        unit_id = str(row["unit_id"])
        refusal = cap.refusal(unit_id)
        if refusal is not None:
            print(json.dumps({"unit_id": unit_id, "skipped": "cap", "detail": refusal}), flush=True)
            unbought.append(unit_id)
            continue
        case = WORK / "cases" / unit_id / "manifest.json"
        if not case.is_file():
            print(json.dumps({"unit_id": unit_id, "skipped": "not built"}), flush=True)
            continue
        manifest = json.loads(case.read_text(encoding="utf-8"))
        repo = Path(manifest["repo_path"])
        failure = _checkout_case(repo, manifest["head_sha"])
        if failure is not None:
            print(json.dumps({"unit_id": unit_id, "skipped": "checkout failed",
                              "detail": failure[:300]}), flush=True)
            continue
        cap.start(unit_id)
        config = load_config(repo)
        config = config.__class__(**{
            **config.__dict__,
            "k_samples": preregistration.k_samples,
            "budget_usd": unit_budget,
            "value_notes_visible": True,
            "gate_notes_visible": True,
        })
        started = datetime.now(UTC)
        review = run_review(
            repo, manifest["base_sha"], config, ApiProvider(config.model),
            verify=True, verification_timeout_s=900.0,
        )
        ledger_path = repo / ".attest" / "ledger.jsonl"
        ledger_rows = _read_jsonl(ledger_path) if ledger_path.exists() else []
        trial = prospective.trial_from_ledger(
            ledger_rows, unit_id=unit_id, task_id=review.task_id,
            recorded_at=started.isoformat(),
            would_publish=tuple(sorted(
                f.accepted_receipt.receipt.candidate_id for f in review.published
            )),
            deferred_reason=review.deferred_reason, spend_usd=review.budget.spent_usd,
            elapsed_s=review.elapsed_s,
        )
        prospective._append_jsonl(trials_path, trial.to_json_dict())
        cap.settle(trial.spend_usd)
        print(json.dumps(trial.to_json_dict(), ensure_ascii=False), flush=True)
        lines = _author_visible_lines(
            repo, review, ledger_rows, config,
            base_sha=manifest["base_sha"], head_sha=manifest["head_sha"],
        )
        prospective._append_jsonl(lines_path, {
            "unit_id": unit_id, "repository": row["repository"], "task_id": review.task_id,
            "recorded_at": started.isoformat(), "spend_usd": trial.spend_usd,
            "unit_budget_usd": unit_budget, "lines": lines,
        })
    if unbought:
        print(json.dumps({"unbought_units": unbought, "cap_usd": cap.cap,
                          "spent_usd": round(cap.spent, 6)}), flush=True)
    print(cap.summary())
    return 0


def classify(rows: list[dict], deferred_reason: str) -> tuple[str, str]:
    """One case's class from its own ledger rows, and the wording that decided it."""
    from attest.certification.intent import INTENT_UNKNOWN_LABEL, VALUE_CHANGE_LABEL

    certified = [
        r for r in rows if r.get("kind") == "certification" and r.get("outcome") == "accepted"
    ]
    if certified:
        return "certified", str(certified[0].get("reason", ""))
    verifications = [r for r in rows if r.get("kind") == "verification"]
    reasons = [str(r.get("reason", "")) for r in verifications] + [deferred_reason or ""]
    for reason in reasons:
        if INTENT_UNKNOWN_LABEL in reason and any(m in reason for m in FRAME_RULE_MARKERS):
            return "drawer: D-232 frame rule", reason
    for reason in reasons:
        if INTENT_UNKNOWN_LABEL in reason:
            return "drawer: behaviour change (statement)", reason
    for reason in reasons:
        if VALUE_CHANGE_LABEL in reason:
            return "value class", reason
    blob = " || ".join(reasons)
    for marker, name in (("outside the project's declared range", "refused: interpreter"),
                         ("environment bootstrap failed", "refused: image"),
                         ("isolation backend unavailable", "refused: executor")):
        if marker in blob:
            return name, blob[:200]
    if not verifications:
        return "no reproduction attempted", deferred_reason or ""
    return "no receipt", reasons[0][:200]


def cmd_table(args: argparse.Namespace) -> int:
    sample = _read_jsonl(STUDY / "sample.jsonl")
    trials_path = STUDY / (args.trials_file or prospective.TRIALS_FILE)
    trials = {r["unit_id"]: r for r in _read_jsonl(trials_path)}
    ledgers: dict[str, list[dict]] = {}
    for library in sorted(REPOSITORIES):
        path = Path(args.ledgers) / library / "repo" / ".attest" / "ledger.jsonl" if args.ledgers \
            else _clone_dir(library) / ".attest" / "ledger.jsonl"
        if not path.is_file():
            path = Path(args.ledgers) / f"{library}-ledger.jsonl" if args.ledgers else path
        ledgers[library] = _read_jsonl(path) if path.is_file() else []
    out = []
    for row in sample:
        unit_id = str(row["unit_id"])
        trial = trials.get(unit_id)
        if trial is None:
            site = f"{row['mutation']['path']}:{row['mutation']['line']}"
            out.append({"case": unit_id, "library": row["library"], "kind": row["stratum"],
                        "class": "not run", "site": site})
            continue
        mine = [e for e in ledgers[str(row["library"])] if e.get("task_id") == trial["task_id"]]
        klass, why = classify(mine, str(trial.get("deferred_reason") or ""))
        out.append({"case": unit_id, "library": row["library"], "kind": row["stratum"],
                    "site": f"{row['mutation']['path']}:{row['mutation']['line']}",
                    "class": klass, "why": why[:300], "candidates": trial.get("candidates"),
                    "eligible": trial.get("eligible"), "attempted": trial.get("attempted"),
                    "certified": trial.get("certified"), "spend_usd": trial.get("spend_usd")})
    n = len(sample)
    certified = sum(1 for r in out if r["class"] == "certified")
    low, high = wilson(certified, n)
    summary = {
        "denominator": n,
        "run": sum(1 for r in out if r["class"] != "not run"),
        "certified": certified,
        "point": round(certified / n, 4) if n else None,
        "wilson95": [round(low, 4), round(high, 4)],
        "classes": dict(Counter(r["class"] for r in out)),
        "by_kind": {
            kind: dict(Counter(r["class"] for r in out if r["kind"] == kind))
            for kind in sorted({r["kind"] for r in out})
        },
        "spend_usd": round(sum(float(r.get("spend_usd") or 0.0) for r in out), 6),
    }
    payload = {"summary": summary, "cases": out}
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_sample)
    sub.add_parser("build").set_defaults(func=cmd_build)
    r = sub.add_parser("run")
    r.add_argument("--allow-paid-api", action="store_true")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--unit-budget", type=float, default=0.0)
    r.add_argument("--reserve", type=float, default=0.0)
    r.add_argument("--trials-file", default="")
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--trials-file", default="")
    t.add_argument("--ledgers", default="")
    t.add_argument("--out", default=str(STUDY / "table.json"))
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
