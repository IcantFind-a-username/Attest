"""D-127 replay: the value discriminator over every receipt the corpus recorded.

Offline and free -- no model call, no execution, no paid anything. For every
`verification` row that reproduced, this rebuilds the inputs the intent observer
was given (the anchored file's two revisions, the generated test, the head
failure messages, the base and head trees at the recorded revisions) and asks
the observer twice:

  old   `attest.intent.v2` -- the discriminator that published `jinja ac3ac6c9`
  new   `attest.intent.v3` -- D-127's value rule

and then, on the receipts that survive, asks `select_for_publication` under the
family policy in force (D-125) what would have been published.

    .venv/bin/python scripts/corpus/intent_v3_replay.py --json report.json

The old side is *recomputed*, not read from the ledger, so both sides come from
the same code path on the same bytes; a row whose recomputed old class differs
from the class the run recorded is reported as `unreplayable` and excluded from
the comparison rather than silently counted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.intent import (  # noqa: E402
    INTENT_POLICY_V2,
    IntentObservation,
    evidence_class_for,
    intent_verdict,
)
from attest.certification.selection import (  # noqa: E402
    FamilyPolicy,
    ScoredFinding,
    select_for_publication,
)
from attest.certification.types import (  # noqa: E402
    _ACCEPTED_RECEIPT_TOKEN,
    AcceptedReceipt,
    CertificationReceipt,
    CertifiedFinding,
    ExecutionRun,
    FindingAnchor,
)
from attest.certification.units import unit_counts  # noqa: E402
from attest.review.channels import V_CAP  # noqa: E402
from attest.review.intent import observe_intent  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
DEFAULT_CLONES = ("attest", "corum", "us-stock-helper", "icantfind-a-username")
CONTROL_CLONES = ("gnull/attrs", "gnull/click", "gnull/itsdangerous", "gnull/jinja")


@dataclass
class ReceiptReplay:
    clone: str
    task_id: str
    candidate_id: str
    path: str
    control: bool
    recorded_class: str
    old_class: str
    old_verdict: str
    new_class: str
    new_verdict: str
    shape: str  # rejection | constant | value | crash
    pinned_values: list[str]
    value_specified: list[list[str]]
    value_respecified: list[list[str]]
    replayable: bool


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _rows(clone: Path) -> list[dict]:
    path = clone / ".attest" / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _candidates(clone: Path) -> dict[str, dict[str, dict]]:
    path = clone / ".attest" / "candidates.jsonl"
    by_task: dict[str, dict[str, dict]] = {}
    if not path.exists():
        return by_task
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        by_task.setdefault(row["task_id"], {})[row["finding_id"]] = row
    return by_task


def _failure_messages(bundle: Path) -> list[str]:
    """The JUnit failure message of each head run, exactly as the executor read it."""
    messages: list[str] = []
    runs = bundle / "runs"
    if not runs.is_dir():
        return messages
    for run in sorted(p for p in runs.iterdir() if p.name.startswith("head-")):
        junit = run / "junit.xml"
        message = ""
        if junit.is_file():
            try:
                for node in ET.parse(junit).iter():
                    if node.tag in ("failure", "error"):
                        message = " ".join(str(node.attrib.get("message", "")).split())[:2000]
                        break
            except ET.ParseError:
                message = ""
        messages.append(message)
    return messages


class Trees:
    """Base and head worktrees of a clone, made once per revision and reused."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._made: dict[tuple[Path, str], Path | None] = {}

    def at(self, clone: Path, sha: str) -> Path | None:
        key = (clone, sha)
        if key in self._made:
            return self._made[key]
        target = self.root / clone.name / sha[:12]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _git(clone, "worktree", "add", "--detach", str(target), sha)
            made: Path | None = target
        except subprocess.CalledProcessError:
            made = None
        self._made[key] = made
        return made

    def clean(self) -> None:
        for (clone, _sha), path in self._made.items():
            if path is not None:
                subprocess.run(
                    ["git", "-C", str(clone), "worktree", "remove", "--force", str(path)],
                    check=False,
                    capture_output=True,
                )


def _shape(observation: IntentObservation) -> str:
    if observation.new_rejection:
        return "rejection"
    if observation.constant_substitution and observation.asserted_constants:
        return "constant"
    return "value" if observation.value_mismatch else "crash"


def replay_receipt(
    *, clone: Path, row: dict, bundle: Path, trees: Trees, control: bool
) -> ReceiptReplay | None:
    recorded = row.get("intent") or {}
    intent_path = str(recorded.get("path") or "")
    changed = tuple(int(x) for x in recorded.get("changed_lines") or ())
    test = bundle / "test_repro.py"
    if not intent_path or not changed or not test.is_file():
        return None
    base_sha, head_sha = str(row.get("base_sha") or ""), str(row.get("head_sha") or "")
    base_tree = trees.at(clone, base_sha)
    head_tree = trees.at(clone, head_sha)
    if base_tree is None or head_tree is None:
        return None
    try:
        head_source = (head_tree / intent_path).read_text(encoding="utf-8", errors="replace")
        base_source = (base_tree / intent_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    messages = _failure_messages(bundle)
    if not messages:
        return None
    observed = observe_intent(
        path=intent_path,
        changed_lines=changed,
        head_source=head_source,
        base_source=base_source,
        test_source=test.read_text(encoding="utf-8", errors="replace"),
        head_origins=[() for _ in messages],
        head_failures=messages,
        base_tree=base_tree,
        head_tree=head_tree,
    )
    if isinstance(observed, str):
        return None
    # the same observation judged under v2: v3's four fields are not v2's, so the
    # value rule does not reach it and the old verdict is what the run applied
    old = replace(observed, policy_version=INTENT_POLICY_V2)
    # the raise origins are not replayable from the bundle, so a receipt the run
    # recorded as a rejection is carried across from its record rather than
    # re-derived; the value rule never applies to one.
    if recorded.get("new_rejection"):
        old = replace(
            old,
            new_rejection=True,
            origin_line=int(recorded["origin_line"]),
            origin_statement=str(recorded["origin_statement"]),
            exception_type=str(recorded["exception_type"]),
            rejected_inputs=tuple(recorded.get("rejected_inputs") or ()),
            witnesses=tuple(
                (str(a), str(b)) for a, b in (recorded.get("witnesses") or ())
            ),
        )
        observed = replace(
            observed,
            new_rejection=True,
            origin_line=old.origin_line,
            origin_statement=old.origin_statement,
            exception_type=old.exception_type,
            rejected_inputs=old.rejected_inputs,
            witnesses=old.witnesses,
            value_mismatch=False,
            pinned_values=(),
            value_specified=(),
            value_respecified=(),
        )
    old_class, new_class = evidence_class_for(old), evidence_class_for(observed)
    return ReceiptReplay(
        clone=clone.name,
        task_id=str(row["task_id"]),
        candidate_id=str(row["finding_id"]),
        path=intent_path,
        control=control,
        recorded_class=str(row.get("evidence_class") or ""),
        old_class=old_class,
        old_verdict=intent_verdict(old) or "",
        new_class=new_class,
        new_verdict=intent_verdict(observed) or "",
        shape=_shape(observed),
        pinned_values=list(observed.pinned_values),
        value_specified=[list(pair) for pair in observed.value_specified],
        value_respecified=[list(pair) for pair in observed.value_respecified],
        replayable=old_class == str(row.get("evidence_class") or old_class),
    )


def _finding(bundle: Path, candidate: dict) -> CertifiedFinding | None:
    try:
        raw = json.loads((bundle / "receipt.json").read_bytes())
        raw["head_runs"] = tuple(ExecutionRun(**run) for run in raw["head_runs"])
        raw["base_runs"] = tuple(ExecutionRun(**run) for run in raw["base_runs"])
        receipt = CertificationReceipt(**raw)
    except (OSError, ValueError, TypeError, KeyError):
        return None
    accepted = AcceptedReceipt._from_validated(receipt, _ACCEPTED_RECEIPT_TOKEN)
    anchor = FindingAnchor(path=candidate["file"], line=int(candidate["line"]))
    return CertifiedFinding.from_accepted_receipt(accepted, (anchor,))


def publications(clone: Path, drawered: set[tuple[str, str]]) -> list[dict]:
    """Per review: what the current family policy publishes with and without the
    receipts D-127 sends to the drawer."""
    rows = _rows(clone)
    candidates = _candidates(clone)
    certifications: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("kind") == "certification":
            certifications.setdefault(str(row["task_id"]), []).append(row)
    out: list[dict] = []
    for row in rows:
        if row.get("kind") != "publication_policy":
            continue
        task_id = str(row["task_id"])
        stored = candidates.get(task_id, {})
        eligible = [
            c
            for c in stored.values()
            if c.get("eligibility") == "regression" and c.get("action") != "discard"
        ]
        before: list[ScoredFinding] = []
        after: list[ScoredFinding] = []
        for cert in certifications.get(task_id, []):
            if cert.get("outcome") != "accepted" or "bundle_path" not in cert:
                continue
            candidate = stored.get(str(cert["finding_id"]))
            if candidate is None:
                continue
            finding = _finding(Path(str(cert["bundle_path"])), candidate)
            if finding is None:
                continue
            item = ScoredFinding(finding, float(candidate["wealth"]) * V_CAP)
            before.append(item)
            if (task_id, str(cert["finding_id"])) not in drawered:
                after.append(item)
        policy = FamilyPolicy(
            alpha=float(row["alpha"]),
            eligible_count=len(eligible),
            hard_cap=int(row["hard_cap"]),
            eligible_units=dict(unit_counts(c["file"] for c in eligible)),
        )
        e_values = [float(c["wealth"]) * V_CAP for c in eligible]

        def ids(selection) -> list[str]:  # type: ignore[no-untyped-def]
            return sorted(f.accepted_receipt.receipt.candidate_id for f in selection.published)

        # A row written before D-125 was produced by the PR-wide family, so
        # today's per-unit policy is not expected to reproduce it; only a
        # publication-policy v2 row is a check on the replay itself.
        under_current_rule = str(row.get("schema_version", "")) == "attest.publication-policy.v2"
        old_ids = ids(select_for_publication(before, policy, e_values))
        out.append(
            {
                "task_id": task_id,
                "clone": clone.name,
                "under_current_rule": under_current_rule,
                "recorded_published": sorted(str(x) for x in row["published"]),
                "old_published": old_ids,
                "new_published": ids(select_for_publication(after, policy, e_values)),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone", action="append", default=[])
    parser.add_argument("--control", action="append", default=[])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    clones = [(name, False) for name in (args.clone or DEFAULT_CLONES)]
    clones += [(name, True) for name in (args.control or CONTROL_CLONES)]

    replays: list[ReceiptReplay] = []
    skipped: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="attest-v3-replay-") as tmp:
        trees = Trees(Path(tmp))
        try:
            for name, control in clones:
                clone = CORPORA / name
                if not (clone / ".attest" / "ledger.jsonl").exists():
                    continue
                for row in _rows(clone):
                    if row.get("kind") != "verification" or row.get("outcome") != "reproduced":
                        continue
                    bundle = (
                        clone
                        / ".attest"
                        / "evidence"
                        / str(row["task_id"])
                        / str(row["finding_id"])
                    )
                    if not bundle.is_dir():
                        skipped.append(
                            {"task": str(row["task_id"]), "candidate": str(row["finding_id"]),
                             "why": "no evidence bundle on this host"}
                        )
                        continue
                    replayed = replay_receipt(
                        clone=clone, row=row, bundle=bundle, trees=trees, control=control
                    )
                    if replayed is None:
                        skipped.append(
                            {"task": str(row["task_id"]), "candidate": str(row["finding_id"]),
                             "why": "inputs the observer needs are not on this host"}
                        )
                        continue
                    replays.append(replayed)
        finally:
            trees.clean()

    comparable = [r for r in replays if r.replayable]
    drawered = {
        (r.task_id, r.candidate_id)
        for r in comparable
        if not r.old_verdict and r.new_verdict
    }
    review_rows: list[dict] = []
    for name, _control in clones:
        clone = CORPORA / name
        if (clone / ".attest" / "ledger.jsonl").exists():
            review_rows.extend(publications(clone, drawered))

    payload = {
        "schema_version": "attest.intent-v3-replay.v1",
        "clones": [name for name, _ in clones],
        "receipts": len(replays),
        "skipped": skipped,
        "comparable": len(comparable),
        "unreplayable": [
            {"task": r.task_id, "candidate": r.candidate_id} for r in replays if not r.replayable
        ],
        "by_shape": {
            shape: sum(1 for r in comparable if r.shape == shape)
            for shape in ("rejection", "constant", "value", "crash")
        },
        "published_before": sum(1 for r in comparable if not r.old_verdict),
        "published_after": sum(1 for r in comparable if not r.new_verdict),
        "drawered_by_v3": [
            {"task": r.task_id, "candidate": r.candidate_id, "clone": r.clone, "path": r.path}
            for r in comparable
            if not r.old_verdict and r.new_verdict
        ],
        "control_publications_before": sum(
            1 for r in comparable if r.control and not r.old_verdict
        ),
        "control_publications_after": sum(
            1 for r in comparable if r.control and not r.new_verdict
        ),
        "reviews": len(review_rows),
        "reviews_under_current_rule": sum(1 for r in review_rows if r["under_current_rule"]),
        "reviews_reproducing_their_ledger": sum(
            1
            for r in review_rows
            if r["under_current_rule"] and r["old_published"] == r["recorded_published"]
        ),
        "review_published_before": sum(len(r["old_published"]) for r in review_rows),
        "review_published_after": sum(len(r["new_published"]) for r in review_rows),
        "receipt_rows": [asdict(r) for r in replays],
        "review_rows": review_rows,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(
        f"receipts {payload['receipts']} comparable {payload['comparable']} "
        f"shapes {payload['by_shape']}\n"
        f"certifying: before {payload['published_before']} -> after "
        f"{payload['published_after']}\n"
        f"controls certifying: before {payload['control_publications_before']} -> after "
        f"{payload['control_publications_after']}\n"
        f"reviews {payload['reviews']} ({payload['reviews_reproducing_their_ledger']} of "
        f"{payload['reviews_under_current_rule']} under today's family rule reproduce their "
        f"ledger): published before {payload['review_published_before']} -> after "
        f"{payload['review_published_after']}; skipped receipts {len(skipped)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
