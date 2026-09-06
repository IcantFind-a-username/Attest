"""D-168 offline: what the discovery schedule would have done to the 17 commits.

**Free.** Nothing is bought. The 2026-09-07 budget re-run is already on disk --
its ledgers, its plans, its candidates, its per-sample token counts -- and this
replays owner decision 1 of 2026-09-07 over them:

* the **proposal stage** may reserve at most `PROPOSAL_SHARE` of the review's
  budget, the first change unit included;
* candidates are ranked by **cluster size**, then by **static credibility**,
  then by finding id;
* at most `--cap` of them **per change unit** may buy a reproduction.

Two numbers come out per commit: the **predicted spend**, and **which candidates
would be verified** against which ones actually were.

    replay --json <out> [--budget 1.00] [--cap 3]

What is exact and what is estimated, stated rather than blurred:

* **exact** -- the plan's per-unit character counts, so which units the 30%
  ceiling admits is arithmetic on recorded numbers; the proposal stage's actual
  cost, priced from the recorded per-sample token counts at the shipped table;
  every candidate's anchor and cluster size; the credibility score, recomputed
  from the head tree of the recorded commit; and which candidates the recorded
  run actually verified.
* **estimated** -- what one reproduction costs. The ledger records a review's
  total and each verification's outcome, but not each verification's price, so
  this uses the run's own mean: (total spend - proposal spend) / verifications
  attempted. A commit's predicted spend is therefore a mean-cost projection, and
  the report says so rather than quoting it to the cent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.budget import PROPOSAL_SHARE, Budget  # noqa: E402
from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.proposer import PROPOSER_MAX_OUTPUT_TOKENS  # noqa: E402
from attest.review.ranking import CredibilityIndex, cluster_size, rank, within_cap  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
MAX_TREE_FILES = 3_000

# The 2026-09-07 `--budget 1.00` re-run, in the order the report lists it. Task
# ids are read out of each clone's own ledger; the commits are the population.
POPULATION: tuple[tuple[str, str, str], ...] = (
    ("attest", "eede42194df5f33ef7b18a417cb57a3747a353a9", "20260906-045706-d6495f25"),
    ("attest", "9b1c9a869989fddc5db3a25cffbf08b4e64065c4", "20260906-050004-0f21f509"),
    ("attest", "8537f6a9d3ad89d6517b1c15d1cb8f181bb03585", "20260906-050055-4e1393af"),
    ("attest", "150804a34bf09ab84dc4e2f9a6a943c9b0824405", "20260906-050116-362ad82e"),
    ("attest", "993ae171e7959529bfcd839777dae84cd265ddfb", "20260906-050416-5e604c37"),
    ("attest", "48b418c895735beecea1d1f66bf4b7cbc0995b87", "20260906-050507-d137c7d6"),
    ("attest", "c88f67e599893055eec843b9498795ef0222641f", "20260906-051043-1b830447"),
    ("attest", "820b973d0949df7055d8ebe2a3648aad7888b248", "20260906-051414-cf27ea06"),
    ("attest", "84c75985a0d826a9b1fca1753a4e32082a2f493a", "20260906-051452-75cb92e7"),
    ("attest", "6579a8fec7145a17defec9b6b9886be0d2318238", "20260906-051842-9e4bc35a"),
    ("attest", "4c3492065c0872627bd5d6e6e29bcbd200a57e1c", "20260906-052101-ff462406"),
    ("us-stock-helper", "3f6b67b0b6dcbb9660890552edb0f1c6939b9ee5", "20260906-052106-233c8712"),
    ("us-stock-helper", "ead0bd75d42e1bf8a12d53a8d5847cd8095e5e4f", "20260906-052259-887eb81e"),
    ("us-stock-helper", "4ef2226bcf2405129a38ad81e65130a3d3c989eb", "20260906-052654-2d9800f6"),
    ("us-stock-helper", "801fb292ce77b6c2768e731859637de50b6f0ae3", "20260906-052845-684eba8a"),
    ("us-stock-helper", "abefa25f7d77174759aa698ecdedffed5dcd5886", "20260906-053153-312a919d"),
    ("us-stock-helper", "8cfab6c5a737bde7c78f2e423d38ac9183378c1d", "20260906-053324-05e17cd3"),
)
K_SAMPLES = 4  # the re-run's `--k 4`

# The other population that matters: the 11 forward pairs of the 2026-09-06b
# probe run, which are the only units in this project's history where red has
# ever published. A schedule that saves money by dropping one of those three
# receipts is not a saving, so the replay is run over them too.
FORWARD: tuple[tuple[str, str], ...] = (
    ("gnull/attrs", "20260906-011429-93f00473"),
    ("gnull/attrs", "20260906-011434-91295ab0"),
    ("gnull/click", "20260906-011444-3b19d6bc"),
    ("gnull/click", "20260906-011648-0c37806d"),
    ("gnull/click", "20260906-012044-31918bcc"),
    ("gnull/itsdangerous", "20260906-012212-ef9d97e7"),
    ("gnull/more-itertools", "20260906-012302-cdccf6bf"),
    ("gnull/more-itertools", "20260906-012316-fa015ad8"),
    ("gnull/more-itertools", "20260906-012333-17d8eecf"),
    ("gnull/more-itertools", "20260906-012349-228115d7"),
    ("gnull/packaging", "20260906-012410-a15435a5"),
)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:160]}")
    return done.stdout


def tree_sources(repo: Path, sha: str) -> dict[str, str]:
    """Every Python file of one revision, in a single `git cat-file` pass."""
    names = [
        line.strip()
        for line in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
        if line.strip().endswith(".py")
    ][:MAX_TREE_FILES]
    if not names:
        return {}
    request = "\n".join(f"{sha}:{name}" for name in names) + "\n"
    done = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=request.encode(),
        capture_output=True,
        check=False,
    )
    sources: dict[str, str] = {}
    data, offset = done.stdout, 0
    for name in names:
        end = data.find(b"\n", offset)
        if end == -1:
            break
        header = data[offset:end].decode("utf-8", "replace").split()
        offset = end + 1
        if len(header) != 3 or header[1] != "blob":
            continue
        size = int(header[2])
        sources[name] = data[offset : offset + size].decode("utf-8", "replace")
        offset += size + 1
    return sources


def ledger_rows(repo: Path, task_id: str) -> list[dict[str, Any]]:
    path = repo / ".attest" / "ledger.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if task_id not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("task_id") == task_id:
            rows.append(row)
    return rows


def proposal_spend(budget: Budget, samples: list[dict[str, Any]]) -> float:
    """What the recorded proposal samples actually cost, at the shipped table.

    A sample served from the attempt cache (`replayed`) bought nothing and cost
    nothing, however many tokens the row records; counting it would put a
    review's reconstructed discovery spend above its own recorded total, which
    is how this was caught."""
    prices = budget.prices()
    total = 0.0
    for sample in samples:
        if sample.get("replayed") is True:
            continue
        total += (
            int(sample.get("input_tokens") or 0) * prices["in"]
            + int(sample.get("cache_creation_input_tokens") or 0) * prices["cache_write"]
            + int(sample.get("cache_read_input_tokens") or 0) * prices["cache_read"]
            + int(sample.get("output_tokens") or 0) * prices["out"]
        )
    return total


def units_under_the_share(
    budget: Budget,
    units: list[dict[str, Any]],
    k: int,
    share: float,
    actual_per_unit: list[float],
) -> tuple[int, list[float]]:
    """How many plan units the share admits, and each one's reservation.

    `propose_plan`'s arithmetic exactly, and the detail that decides the answer:
    a reservation is **transient**. `propose` reserves all `k` samples of a unit
    at the proposal token bound, then `settle` replaces each reservation with
    what the call actually cost -- and the token bound overstates a real
    proposal by about three times. So a unit is admitted when

        (what discovery has actually spent) + k x (this unit's estimate) <= ceiling

    and what it then adds to the running total is its **actual** cost, not its
    reservation. Modelling the ceiling against a sum of reservations understates
    the units a review reads by a factor of three, which is how this was caught.
    """
    ceiling = budget.limit_usd * share
    reservations: list[float] = []
    spent = 0.0
    admitted = 0
    for index, unit in enumerate(units):
        chars = int(unit.get("diff_chars", 0)) + int(unit.get("context_chars", 0))
        need = k * budget.estimate_cost(chars, PROPOSER_MAX_OUTPUT_TOKENS)
        reservations.append(need)
        if spent + need > ceiling:
            break
        spent += actual_per_unit[index] if index < len(actual_per_unit) else 0.0
        admitted += 1
    return admitted, reservations


def head_of(rows: list[dict[str, Any]]) -> str:
    """The head commit the recorded run reviewed, from its own verification rows."""
    for row in rows:
        head = row.get("head_sha")
        if isinstance(head, str) and len(head) == 40:
            return head
    return ""


def published_in(rows: list[dict[str, Any]]) -> list[str]:
    for row in rows:
        if row.get("kind") == "publication_policy":
            return [str(name) for name in (row.get("published") or [])]
    return []


def replay_commit(
    repo_name: str,
    head: str,
    task_id: str,
    *,
    limit: float,
    cap: int,
    share: float = PROPOSAL_SHARE,
) -> dict:
    repo = CORPORA / repo_name
    rows = ledger_rows(repo, task_id)
    head = head or head_of(rows)
    plan = next((r for r in rows if r.get("kind") == "review_plan"), None)
    run = next((r for r in rows if r.get("kind") == "review_run"), None)
    if plan is None or run is None:
        return {"repo": repo_name, "head": head, "task_id": task_id, "ok": False}

    budget = Budget(limit_usd=limit, model=str(run.get("model") or "claude-sonnet-5"))
    units = list(plan["units"])
    samples = list(run.get("provider_samples") or [])
    recorded_units_read = max(1, -(-len(samples) // K_SAMPLES))
    # what discovery cost, recorded, per unit -- samples are emitted unit by unit
    per_unit_spend = [
        proposal_spend(budget, samples[index * K_SAMPLES : (index + 1) * K_SAMPLES])
        for index in range(recorded_units_read)
    ]
    admitted, reservations = units_under_the_share(
        budget, units, K_SAMPLES, share, per_unit_spend
    )
    recorded_proposal = sum(per_unit_spend)
    predicted_proposal = sum(per_unit_spend[:admitted])

    # which candidates survive: those anchored in a file of an admitted unit
    admitted_files = {file for unit in units[:admitted] for file in unit["files"]}
    candidates = [c for c in CandidateStore(repo).load(task_id) if c.action != "discard"]
    eligible = [c for c in candidates if c.eligibility == "regression"]
    surviving = [c for c in eligible if c.finding.file in admitted_files]
    unattributed = [
        c
        for c in eligible
        if c.finding.file not in {file for unit in units for file in unit["files"]}
    ]
    surviving += [c for c in unattributed if c not in surviving]

    # a task whose run bought nothing records no head sha; credibility then
    # abstains for every candidate, exactly as it does on an unreadable tree,
    # and the order falls back to cluster size and finding id
    index = CredibilityIndex(tree_sources(repo, head) if head else {})
    ordered = rank(surviving, index)
    purchasable, below = within_cap(ordered, cap)

    # what the recorded run actually verified
    verified_now = {
        str(row.get("finding_id"))
        for row in rows
        if row.get("kind") == "verification" and row.get("finding_id")
    }
    attempts = max(1, len(verified_now))
    recorded_total = float(run.get("spend_usd") or 0.0)
    mean_repro = max(0.0, recorded_total - recorded_proposal) / attempts

    # the reproduction budget left after discovery, and how many fit in it
    headroom = max(0.0, limit - predicted_proposal)
    affordable = len(purchasable) if mean_repro <= 0 else min(
        len(purchasable), int(headroom // mean_repro)
    )
    predicted_total = predicted_proposal + affordable * mean_repro

    would_verify = [
        item.finding.finding_id for item in ordered if item.finding.finding_id in purchasable
    ][:affordable]
    return {
        "repo": repo_name,
        "head": head,
        "task_id": task_id,
        "ok": True,
        "head_known": bool(head),
        "units_planned": len(units),
        "units_read_recorded": recorded_units_read,
        "units_read_under_share": admitted,
        "first_unit_reservation_usd": round(reservations[0], 6) if reservations else 0.0,
        "share_ceiling_usd": round(limit * share, 6),
        "candidates_recorded": len(candidates),
        "eligible_recorded": len(eligible),
        "eligible_under_share": len(surviving),
        "purchasable_under_cap": len(purchasable),
        "below_cap": len(below),
        "verified_recorded": sorted(verified_now),
        "would_verify": sorted(would_verify),
        "kept": sorted(verified_now & set(would_verify)),
        "dropped": sorted(verified_now - set(would_verify)),
        "added": sorted(set(would_verify) - verified_now),
        "proposal_spend_recorded_usd": round(recorded_proposal, 6),
        "proposal_spend_predicted_usd": round(predicted_proposal, 6),
        "mean_reproduction_usd": round(mean_repro, 6),
        "spend_recorded_usd": round(recorded_total, 6),
        "spend_predicted_usd": round(predicted_total, 6),
        "cluster_sizes": sorted((cluster_size(c) for c in ordered), reverse=True)[:8],
        "published_recorded": sorted(published_in(rows)),
        "published_still_bought": sorted(
            name for name in published_in(rows) if name in set(would_verify)
        ),
    }


def cmd_replay(args: argparse.Namespace) -> int:
    rows = [
        replay_commit(repo, head, task, limit=args.budget, cap=args.cap, share=args.share)
        for repo, head, task in POPULATION
    ]
    good = [row for row in rows if row["ok"]]
    per_unit: dict[str, int] = defaultdict(int)
    for row in good:
        per_unit["kept"] += len(row["kept"])
        per_unit["dropped"] += len(row["dropped"])
        per_unit["added"] += len(row["added"])
    summary = {
        "commits": len(rows),
        "replayed": len(good),
        "budget_usd": args.budget,
        "cap_per_unit": args.cap,
        "proposal_share": args.share,
        "units_read_recorded": sum(r["units_read_recorded"] for r in good),
        "units_read_under_share": sum(r["units_read_under_share"] for r in good),
        "first_unit_over_the_share": sum(
            1 for r in good if r["first_unit_reservation_usd"] > r["share_ceiling_usd"]
        ),
        "eligible_recorded": sum(r["eligible_recorded"] for r in good),
        "eligible_under_share": sum(r["eligible_under_share"] for r in good),
        "purchasable_under_cap": sum(r["purchasable_under_cap"] for r in good),
        "below_cap": sum(r["below_cap"] for r in good),
        "verified_recorded": sum(len(r["verified_recorded"]) for r in good),
        "would_verify": sum(len(r["would_verify"]) for r in good),
        "candidates_kept": per_unit["kept"],
        "candidates_dropped": per_unit["dropped"],
        "candidates_added": per_unit["added"],
        "spend_recorded_usd": round(sum(r["spend_recorded_usd"] for r in good), 4),
        "spend_predicted_usd": round(sum(r["spend_predicted_usd"] for r in good), 4),
    }
    payload = {
        "schema_version": "attest.schedule-replay.v1",
        "generated": datetime.now(UTC).isoformat(),
        "summary": summary,
        "rows": rows,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for row in rows:
        if not row["ok"]:
            print(f"  {row['repo']:>15s} {row['head'][:10]} UNREPLAYABLE")
            continue
        print(
            f"  {row['repo']:>15s} {row['head'][:10]} units "
            f"{row['units_read_under_share']}/{row['units_read_recorded']} "
            f"eligible {row['eligible_under_share']}/{row['eligible_recorded']} "
            f"buy {len(row['would_verify'])}/{len(row['verified_recorded'])} "
            f"(kept {len(row['kept'])}, dropped {len(row['dropped'])}, added {len(row['added'])}) "
            f"${row['spend_predicted_usd']:.4f} vs ${row['spend_recorded_usd']:.4f}"
        )
    return 0


def cmd_forward(args: argparse.Namespace) -> int:
    """The same rule over the 11 forward pairs: does any receipt stop being bought?"""
    rows = [
        replay_commit(repo, "", task, limit=args.budget, cap=args.cap, share=args.share)
        for repo, task in FORWARD
    ]
    good = [row for row in rows if row["ok"]]
    published = [name for row in good for name in row["published_recorded"]]
    kept = [name for row in good for name in row["published_still_bought"]]
    summary = {
        "pairs": len(rows),
        "replayed": len(good),
        "budget_usd": args.budget,
        "cap_per_unit": args.cap,
        "proposal_share": args.share,
        "units_read_recorded": sum(r["units_read_recorded"] for r in good),
        "units_read_under_share": sum(r["units_read_under_share"] for r in good),
        "eligible_recorded": sum(r["eligible_recorded"] for r in good),
        "eligible_under_share": sum(r["eligible_under_share"] for r in good),
        "verified_recorded": sum(len(r["verified_recorded"]) for r in good),
        "would_verify": sum(len(r["would_verify"]) for r in good),
        "published_recorded": sorted(published),
        "published_still_bought": sorted(kept),
        "receipts_lost": sorted(set(published) - set(kept)),
        "spend_recorded_usd": round(sum(r["spend_recorded_usd"] for r in good), 4),
        "spend_predicted_usd": round(sum(r["spend_predicted_usd"] for r in good), 4),
    }
    payload = {
        "schema_version": "attest.schedule-replay-forward.v1",
        "generated": datetime.now(UTC).isoformat(),
        "summary": summary,
        "rows": rows,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for row in rows:
        marker = ""
        if row.get("published_recorded"):
            marker = (
                " RECEIPT KEPT"
                if row["published_still_bought"] == row["published_recorded"]
                else " RECEIPT LOST"
            )
        print(
            f"  {row['repo']:>22s} {row['task_id'][-8:]} units "
            f"{row.get('units_read_under_share')}/{row.get('units_read_recorded')} "
            f"buy {len(row.get('would_verify', []))}/{len(row.get('verified_recorded', []))} "
            f"${row.get('spend_predicted_usd', 0):.4f} vs ${row.get('spend_recorded_usd', 0):.4f}"
            f"{marker}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("--json", type=Path)
    replay.add_argument("--budget", type=float, default=1.00)
    replay.add_argument("--cap", type=int, default=3)
    replay.add_argument("--share", type=float, default=PROPOSAL_SHARE)
    replay.set_defaults(func=cmd_replay)
    forward = sub.add_parser("forward")
    forward.add_argument("--json", type=Path)
    forward.add_argument("--budget", type=float, default=1.00)
    forward.add_argument("--cap", type=int, default=3)
    forward.add_argument("--share", type=float, default=PROPOSAL_SHARE)
    forward.set_defaults(func=cmd_forward)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
