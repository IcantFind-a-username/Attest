"""One full `attest review` per **forward** pair (D-135, owner instruction 3 of 2026-09-05d).

The pairs come from `forward_pairs.py`, whose construction is free: `head` is the
commit that *introduced* a defect and `base` is its parent, so time runs the way
it runs in a pull request. The reviews here are the paid half, and they are the
first value-class recall number this project may quote at all -- D-135 bars the
number from the reversed corpus, where clause (c) is wrong on 4 of 4.

  run     one `attest review` per **distinct** `(repo, head, base)`, head
          checked out detached in the clone, `--base` its parent, K=4,
          `--budget 1.00`, containers, local only. Resumes from its own log,
          runs nothing twice, and stops at a hard cumulative cap.
  table   the value-class table, read from the driver's log and each clone's
          ledger and bundles. Every row carries `fwd`, because a value-class
          row from a reversed pair may not be quoted (D-135) and a table that
          does not say which it is invites exactly that.

**n is 11 and the tables say so.** Three of the thirteen resolutions converge on
one `click` pair; a review of it buys the same evidence three times.

Paid: `run`. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from driver_budget import DriverCap  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
RUNS = ROOT / "benchmarks" / "attest-v2" / "runs"
PAIRS = RUNS / "2026-09-05-forward-pairs.json"


# Where each repository of the forward-pair corpus is cloned. `attest`,
# `us-stock-helper` and `corum` sit directly under the corpora root; the eight
# public clones of `G-NULL-001a` are shared with the null study, which is why
# the two drivers may not run at the same time -- both check a commit out.
def clone_of(repo: str) -> Path:
    direct = CORPORA / repo
    return direct if direct.is_dir() else CORPORA / "gnull" / repo


def distinct_pairs() -> list[dict[str, str]]:
    """The distinct `(repo, head, base)` triples, in a fixed order, each with
    the repairing commits whose oracle located it."""
    document = json.loads(PAIRS.read_text(encoding="utf-8"))
    order: list[tuple[str, str, str]] = []
    fixes: dict[tuple[str, str, str], list[str]] = {}
    for pair in document["pairs"]:
        if not pair.get("resolved"):
            continue
        key = (str(pair["repo"]), str(pair["head"]), str(pair["base"]))
        if key not in fixes:
            order.append(key)
            fixes[key] = []
        fixes[key].append(str(pair.get("fix_subject", ""))[:70])
    return [
        {
            "repo": repo,
            "head": head,
            "base": base,
            "fixes": fixes[(repo, head, base)],
        }
        for repo, head, base in order
    ]


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def cmd_run(args: argparse.Namespace) -> int:
    pairs = distinct_pairs()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")

    done: set[str] = set()
    spent = 0.0
    log_path = Path(args.log)
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        for block in re.split(r"^=== fp ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            if "[rc " in body:
                done.add(head.split()[0])
        seen = re.findall(r"\[cumulative spend \$([0-9.]+)\]", text)
        spent = float(seen[-1]) if seen else 0.0
    # D-172: the cap reserves a unit's *maximum* -- one review at `--budget` --
    # before the unit starts. Gating on money already spent let the 2026-09-07
    # run end $0.62 above its own cumulative cap.
    cap = DriverCap(cap=args.cap, reservation_usd=args.budget, spent=spent)
    log = log_path.open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop

    for pair in pairs:
        head = str(pair["head"])
        if head in done:
            continue
        clone = clone_of(str(pair["repo"]))
        log.write(f"=== fp {head} {pair['repo']} base={str(pair['base'])[:10]} fwd\n")
        if not clone.is_dir():
            log.write(f"[skipped: no clone at {clone}]\n")
            log.flush()
            continue
        refusal = cap.refusal(head[:10])
        if refusal is not None:
            log.write(f"[{refusal}]\n")
            log.flush()
            continue
        cap.start(head[:10])
        git(clone, "checkout", "-q", "--detach", head)
        completed = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-c",
                "from attest.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
                "--repo",
                str(clone),
                "review",
                "--base",
                str(pair["base"]),
                "--k",
                "4",
                "--budget",
                f"{args.budget:.2f}",
                "--verification-timeout",
                str(args.verification_timeout),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        log.write(
            # 40k, not 6k: a 42-candidate review's drawer listing pushed the
            # `run status:` line out of a 6k tail, and that line is the table's
            # primary source. The fallback below covers a log that lost it anyway.
            completed.stdout[-40000:]
            + completed.stderr[-1500:]
            + f"\n[rc {completed.returncode}]\n"
        )
        found = re.search(r"spend \$([0-9.]+) of", completed.stdout)
        cap.settle(float(found.group(1)) if found else None)
        log.write(f"[cumulative spend ${cap.spent:.6f}]\n")
        log.flush()
    log.write("=== fp done\n")
    return 0


STATUS = re.compile(
    # `, budget-limited` is appended when the review stopped reading units for
    # want of budget, and a status line that carried it used to fall through to
    # the summary fallback -- which cannot see `published`, so a published
    # finding was reported as unpublished. Found on `click cd4674a6de`, the only
    # budget-limited pair in the corpus.
    r"read (?P<read>\d+) of (?P<total>\d+) units(?:, budget-limited)?; "
    r"candidates: (?P<candidates>\d+); "
    r"eligible: (?P<eligible>\d+); reproductions attempted: (?P<attempted>\d+); "
    r"certified: (?P<certified>\d+); published: (?P<published>\d+)"
)
VERIFY = re.compile(r"verification: (?P<finding>[0-9a-f]+): (?P<reason>.+)")
# Every review prints this last, however many candidates it had, so it is the
# fallback when a very large review's `run status:` block did not survive the
# driver's stdout window.
SUMMARY = re.compile(
    r"(?P<candidates>\d+) candidate\(s\): (?P<verified>\d+) verified, "
    r"(?P<unverified>\d+) unverified, (?P<discarded>\d+) discarded"
)
# A verification line is one of three things, and only the third is the product
# answering about the code: the budget ran out before a reproduction was bought,
# the host or the image could not run one, or the policy reached a verdict.
BUDGET_REFUSED = ("generation failed: BudgetExceeded",)
INFRASTRUCTURE = (
    "isolation backend unavailable",
    "collection deferred",
    "executor failure",
    "process containment unavailable",
    "shared verification deadline",
    "could not create",
    "unsupported anchor language",
)
# D-146: the two generator-specific verdicts the before/after table compares.
# `UNFAITHFUL` is the legacy generator's wall -- the model asserted a behaviour
# base does not have. `PROBE_REFUSED` is what replaces it: the recording was not
# admissible, which is a refusal *before* any head run is bought rather than a
# reproduction discovered to be worthless after six.
UNFAITHFUL = "unfaithful generated test: fails on base as well"
PROBE_REFUSED = "probe "
VALUE_MARKERS = (
    "value change confirmed, intent unknown",
    "constant change confirmed, intent unknown",
    "intent stated in the change itself",
)


BUNDLE = re.compile(r"bundle:\s+(\.attest/evidence/\S+)")


def _certified_classes(clone: Path, body: str) -> list[dict[str, object]]:
    """For every bundle this review wrote, the evidence class it certified under
    and whether the intent observation calls it a **value** mismatch.

    A drawer reason names the value class in its own text; a *certified* one does
    not, because the receipt publishes as the regression it is and the
    specification it contradicts lives in the intent observation. So the bundle
    is where a certified value-class row has to be read from.
    """
    found: list[dict[str, object]] = []
    for match in BUNDLE.finditer(body):
        directory = clone / match.group(1)
        receipt = directory / "receipt.json"
        intent = directory / "intent.json"
        if not receipt.is_file():
            continue
        row: dict[str, object] = {
            "bundle": match.group(1),
            "evidence_class": json.loads(receipt.read_text(encoding="utf-8")).get("evidence_class"),
            "value_mismatch": None,
        }
        if intent.is_file():
            row["value_mismatch"] = bool(
                json.loads(intent.read_text(encoding="utf-8")).get("value_mismatch")
            )
        found.append(row)
    return found


def cmd_table(args: argparse.Namespace) -> int:
    """The value-class table on forward pairs, read from the driver's log.

    The log is the only record that names the pair beside its outcome: a
    `review_run` ledger row carries no head sha, so a ledger-only table cannot
    say which pair a row is about (the same lesson D-136's driver learned).
    """
    pairs = {str(p["head"]): p for p in distinct_pairs()}
    text = Path(args.log).read_text(encoding="utf-8")
    rows: list[dict[str, object]] = []
    for block in re.split(r"^=== fp ", text, flags=re.M)[1:]:
        header, _, body = block.partition("\n")
        parts = header.split()
        if not parts or parts[0] not in pairs:
            continue
        head = parts[0]
        pair = pairs[head]
        status = STATUS.search(body)
        summary = SUMMARY.search(body)
        verdicts = [
            {"finding": match.group("finding"), "reason": match.group("reason").strip()}
            for match in VERIFY.finditer(body)
        ]
        value_rows = [v for v in verdicts if any(marker in v["reason"] for marker in VALUE_MARKERS)]
        certified_rows = _certified_classes(clone_of(str(pair["repo"])), body)
        refused = [v for v in verdicts if str(v["reason"]).startswith(BUDGET_REFUSED)]
        blocked = [v for v in verdicts if str(v["reason"]).startswith(INFRASTRUCTURE)]
        answered = [v for v in verdicts if v not in refused and v not in blocked]
        rows.append(
            {
                "direction": "fwd",  # D-135: every row says which way time ran
                "repo": pair["repo"],
                "head": head[:10],
                "base": str(pair["base"])[:10],
                "ran": "[rc " in body,
                "candidates": int(
                    status.group("candidates")
                    if status
                    else (summary.group("candidates") if summary else 0)
                ),
                "eligible": int(status.group("eligible")) if status else None,
                # without the status line the number of *attempts* is not
                # recoverable, but the number of candidates the verification
                # stage answered about is: one line each
                "attempted": int(status.group("attempted")) if status else len(verdicts),
                "certified": int(
                    status.group("certified")
                    if status
                    else (summary.group("verified") if summary else 0)
                ),
                # published <= certified, and a review that certified nothing
                # published nothing
                "published": int(status.group("published")) if status else 0,
                "status_line": bool(status),
                "budget_refused": len(refused),
                "infrastructure_blocked": len(blocked),
                # D-146's before/after columns
                "unfaithful": sum(1 for v in verdicts if UNFAITHFUL in str(v["reason"])),
                "probe_refused": sum(
                    1 for v in verdicts if str(v["reason"]).startswith(PROBE_REFUSED)
                ),
                # the recall denominator: candidates whose reproduction reached a
                # verdict about the code, plus the ones that certified
                "policy_answered": len(answered)
                + int(
                    status.group("certified")
                    if status
                    else (summary.group("verified") if summary else 0)
                ),
                "verdicts": verdicts,
                "value_class_drawered": value_rows,
                "certified_bundles": certified_rows,
                "value_class_certified": [r for r in certified_rows if r["value_mismatch"]],
                "fixes": pair["fixes"],
            }
        )

    reviewed = [row for row in rows if row["ran"]]
    payload = {
        "schema_version": "attest.forward-pair-reviews.v1",
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "policy": "attest.intent.v4.1",
        "direction": "fwd",
        "n_distinct_pairs": len(pairs),
        "reviewed": len(reviewed),
        "attempted_reproductions": sum(int(row["attempted"]) for row in reviewed),
        "budget_refused": sum(int(row["budget_refused"]) for row in reviewed),
        "infrastructure_blocked": sum(int(row["infrastructure_blocked"]) for row in reviewed),
        "policy_answered": sum(int(row["policy_answered"]) for row in reviewed),
        "unfaithful": sum(int(row["unfaithful"]) for row in reviewed),
        "probe_refused": sum(int(row["probe_refused"]) for row in reviewed),
        "certified": sum(int(row["certified"]) for row in reviewed),
        "published": sum(int(row["published"]) for row in reviewed),
        "value_class_drawered": sum(len(list(row["value_class_drawered"])) for row in reviewed),
        "value_class_certified": sum(len(list(row["value_class_certified"])) for row in reviewed),
        "rows": rows,
    }
    print(
        f"forward pairs: {len(reviewed)} of {len(pairs)} reviewed; "
        f"verification answers {payload['attempted_reproductions']} "
        f"({payload['policy_answered']} about the code, "
        f"{payload['budget_refused']} budget-refused, "
        f"{payload['infrastructure_blocked']} host-blocked); "
        f"unfaithful {payload['unfaithful']}; probe-refused {payload['probe_refused']}; "
        f"certified {payload['certified']}; published {payload['published']}; "
        f"value class: {payload['value_class_certified']} certified, "
        f"{payload['value_class_drawered']} drawered"
    )
    for row in rows:
        print(
            f"  {row['direction']} {row['repo']:<15} {row['head']} "
            f"cand={row['candidates']} answered={row['policy_answered']} "
            f"budget={row['budget_refused']} host={row['infrastructure_blocked']} "
            f"cert={row['certified']} pub={row['published']} "
            f"value-cert={len(list(row['value_class_certified']))} "
            f"value-drawer={len(list(row['value_class_drawered']))}"
        )
    if args.json:
        Path(args.json).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for index, pair in enumerate(distinct_pairs(), start=1):
        clone = clone_of(str(pair["repo"]))
        print(
            f"{index:>2} fwd {pair['repo']:<15} {str(pair['head'])[:10]} "
            f"<- {str(pair['base'])[:10]}  clone={'yes' if clone.is_dir() else 'MISSING'} "
            f"({len(list(pair['fixes']))} fix commit(s))"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    r = sub.add_parser("run")
    r.add_argument("--budget", type=float, required=True)
    r.add_argument("--cap", type=float, required=True, help="hard cumulative spend cap")
    r.add_argument("--log", required=True)
    r.add_argument("--verification-timeout", type=int, default=1200)
    r.set_defaults(func=cmd_run)

    t = sub.add_parser("table")
    t.add_argument("--log", required=True, help="the driver log the run wrote")
    t.add_argument("--json", type=Path)
    t.set_defaults(func=cmd_table)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
