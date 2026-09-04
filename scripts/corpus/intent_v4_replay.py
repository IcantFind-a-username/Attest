"""D-132/D-134 replay: v2, v3, v4 and v4.1 side by side over every receipt the
corpus recorded.

Offline and free -- no model call, no execution, no paid anything. For every
`verification` row that reproduced, this rebuilds the inputs the intent observer
was given (the anchored file's two revisions, the generated test, the head
failure messages *and their JUnit longreprs*, the diff's file list, the base and
head trees at the recorded revisions) and reads three verdicts off one
observation:

  v2   `attest.intent.v2` -- the discriminator that published `jinja ac3ac6c9`
  v3   `attest.intent.v3` -- D-127's value rule, which published `urllib3 c7b9adcb`
  v4   `attest.intent.v4` -- D-132: the failing assertion only, no generic
       constant, and no diff that states its own intent
  v4.1 `attest.intent.v4.1` -- D-134: clause (c) narrowed, so a symbol name is
       intent only where it appears in a recognisable form (backticked,
       dot-qualified, or a long bare name English does not supply)

and then, on the receipts that survive each, asks `select_for_publication` under
the family policy in force (D-125) what would have been published.

The v4 column's intent evidence is recomputed with the *pre*-D-134 mention rule
(`find_intent_evidence(distinctive=False)`), because `observe_intent` now applies
the narrowed one; every other field of the two columns is shared, so v4 and v4.1
differ by the mention rule and by nothing else.

    .venv/bin/python scripts/corpus/intent_v4_replay.py --json report.json

The v2 side is *recomputed*, not read from the ledger, so every column comes from
the same code path on the same bytes; a row whose recomputed v2 class differs
from the class the run recorded is reported as `unreplayable` and excluded from
the comparison rather than silently counted.

v3's columns are computed from a v3-stamped copy of the same observation. That is
exact for every field v3 defines except one: `pinned_values` under v4 is the
failing assertion's, and v3's was every assertion's. The v3 column therefore
recomputes its own pinned set with `assertion_pinned_values`, so the three
columns differ only by the rules and never by the inputs.
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
    INTENT_POLICY_V3,
    INTENT_POLICY_V4,
    IntentObservation,
    distinctive_pinned_values,
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
from attest.review.intent import (  # noqa: E402
    MAX_VALUE_CHARS,
    assertion_pinned_values,
    find_intent_evidence,
    find_specifications,
    observe_intent,
)

CORPORA = ROOT / ".attest" / "corpora"
DEFAULT_CLONES = ("attest", "corum", "us-stock-helper", "icantfind-a-username")
# every `G-NULL-001a` control clone this host holds a ledger for -- `urllib3`
# included, because it is the control v4 exists to stop (D-131)
CONTROL_CLONES = (
    "gnull/attrs",
    "gnull/click",
    "gnull/itsdangerous",
    "gnull/jinja",
    "gnull/more-itertools",
    "gnull/packaging",
    "gnull/python-dotenv",
    "gnull/urllib3",
)


@dataclass
class ReceiptReplay:
    clone: str
    task_id: str
    candidate_id: str
    path: str
    control: bool
    recorded_class: str
    v2_class: str
    v2_verdict: str
    v3_class: str
    v3_verdict: str
    v4_class: str
    v4_verdict: str
    v4_1_class: str
    v4_1_verdict: str
    shape: str  # rejection | constant | value | crash
    v3_pinned_values: list[str]
    pinned_values: list[str]  # v4: the failing assertion's
    failing_assertion_line: int
    anchored_symbols: list[str]
    intent_evidence: list[list[str]]  # v4.1: recognisable mentions only
    intent_evidence_v4: list[list[str]]  # v4: any word-boundary mention
    value_specified: list[list[str]]
    value_respecified: list[list[str]]
    # which of D-132's clauses would drawer this receipt on its own, given the
    # other two are satisfied
    clause_a: bool  # the failing assertion pins less than every assertion did
    clause_b: bool  # what it pins is generic only
    clause_c: bool  # the diff states its own intent, under v4's mention rule
    clause_c_v4_1: bool  # ... and under v4.1's
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


def _failure_messages(bundle: Path) -> tuple[list[str], list[str]]:
    """Each head run's JUnit failure message and body, as the executor read them."""
    messages: list[str] = []
    details: list[str] = []
    runs = bundle / "runs"
    if not runs.is_dir():
        return messages, details
    for run in sorted(p for p in runs.iterdir() if p.name.startswith("head-")):
        junit = run / "junit.xml"
        message, detail = "", ""
        if junit.is_file():
            try:
                for node in ET.parse(junit).iter():
                    if node.tag in ("failure", "error"):
                        message = " ".join(str(node.attrib.get("message", "")).split())[:2000]
                        detail = (node.text or "")[-8000:]
                        break
            except ET.ParseError:
                message, detail = "", ""
        messages.append(message)
        details.append(detail)
    return messages, details


def _changed_files(clone: Path, base_sha: str, head_sha: str) -> tuple[str, ...]:
    """Every path the reviewed change touched, for D-132's intent-evidence walk."""
    try:
        out = _git(clone, "diff", "--no-color", "--name-only", base_sha, head_sha)
    except subprocess.CalledProcessError:
        return ()
    return tuple(sorted({line.strip() for line in out.splitlines() if line.strip()}))


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
    messages, details = _failure_messages(bundle)
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
        head_failure_details=details,
        changed_files=_changed_files(clone, base_sha, head_sha),
        base_tree=base_tree,
        head_tree=head_tree,
    )
    if isinstance(observed, str):
        return None
    # D-134: `observe_intent` now records only *recognisable* mentions, so the v4
    # column recomputes clause (c)'s evidence under the rule v4 actually applied
    # -- any word-boundary match -- from the same bytes.
    wide_evidence = (
        find_intent_evidence(
            base_tree=base_tree,
            head_tree=head_tree,
            changed_files=_changed_files(clone, base_sha, head_sha),
            anchored=intent_path,
            base_source=base_source,
            head_source=head_source,
            changed_lines=changed,
            symbols=observed.anchored_symbols,
            distinctive=False,
        )
        if observed.anchored_symbols
        else ()
    )
    under_v4 = replace(
        observed, policy_version=INTENT_POLICY_V4, intent_evidence=wide_evidence
    )
    # v3's pinned set was every assertion of the generated test, so the v3 column
    # recomputes it (and its specifications) rather than inheriting v4's narrower
    # one; every other field is shared, and the three columns then differ only by
    # the rules.
    v3_pinned = (
        assertion_pinned_values(test.read_text(encoding="utf-8", errors="replace"))
        if observed.value_mismatch
        else ()
    ) or ()
    v3_specified, v3_respecified = (
        find_specifications(
            base_tree=base_tree, head_tree=head_tree, pinned=v3_pinned, anchored=intent_path
        )
        if v3_pinned
        else ((), ())
    )
    v3 = replace(
        observed,
        policy_version=INTENT_POLICY_V3,
        pinned_values=tuple(repr(value)[:MAX_VALUE_CHARS] for _kind, value in v3_pinned),
        value_specified=v3_specified,
        value_respecified=v3_respecified,
    )
    # the same observation judged under v2: v3's and v4's fields are not v2's, so
    # neither value rule reaches it and the v2 verdict is what the run applied
    v2 = replace(v3, policy_version=INTENT_POLICY_V2)
    # the raise origins are not replayable from the bundle, so a receipt the run
    # recorded as a rejection is carried across from its record rather than
    # re-derived; the value rule never applies to one.
    if recorded.get("new_rejection"):
        carried = {
            "new_rejection": True,
            "origin_line": int(recorded["origin_line"]),
            "origin_statement": str(recorded["origin_statement"]),
            "exception_type": str(recorded["exception_type"]),
            "rejected_inputs": tuple(recorded.get("rejected_inputs") or ()),
            "witnesses": tuple((str(a), str(b)) for a, b in (recorded.get("witnesses") or ())),
        }
        cleared = {
            "value_mismatch": False,
            "pinned_values": (),
            "value_specified": (),
            "value_respecified": (),
            "intent_evidence": (),
        }
        v2 = replace(v2, **carried)
        v3 = replace(v3, **carried, **cleared)
        observed = replace(observed, **carried, **cleared)
        under_v4 = replace(under_v4, **carried, **cleared)
    # D-132's three clauses, each asked on its own: would it drawer a receipt the
    # other two let through?
    v3_reprs = set(v3.pinned_values)
    v4_reprs = set(observed.pinned_values)
    clause_a = observed.value_mismatch and v4_reprs != v3_reprs
    clause_b = observed.value_mismatch and bool(v4_reprs) and not distinctive_pinned_values(
        observed
    )
    clause_c = under_v4.value_mismatch and bool(under_v4.intent_evidence)
    clause_c_v4_1 = observed.value_mismatch and bool(observed.intent_evidence)
    return ReceiptReplay(
        clone=clone.name,
        task_id=str(row["task_id"]),
        candidate_id=str(row["finding_id"]),
        path=intent_path,
        control=control,
        recorded_class=str(row.get("evidence_class") or ""),
        v2_class=evidence_class_for(v2),
        v2_verdict=intent_verdict(v2) or "",
        v3_class=evidence_class_for(v3),
        v3_verdict=intent_verdict(v3) or "",
        v4_class=evidence_class_for(under_v4),
        v4_verdict=intent_verdict(under_v4) or "",
        v4_1_class=evidence_class_for(observed),
        v4_1_verdict=intent_verdict(observed) or "",
        shape=_shape(observed),
        v3_pinned_values=list(v3.pinned_values),
        pinned_values=list(observed.pinned_values),
        failing_assertion_line=observed.failing_assertion_line,
        anchored_symbols=list(observed.anchored_symbols),
        intent_evidence=[list(pair) for pair in observed.intent_evidence],
        intent_evidence_v4=[list(pair) for pair in under_v4.intent_evidence],
        value_specified=[list(pair) for pair in observed.value_specified],
        value_respecified=[list(pair) for pair in observed.value_respecified],
        clause_a=clause_a,
        clause_b=clause_b,
        clause_c=clause_c,
        clause_c_v4_1=clause_c_v4_1,
        replayable=evidence_class_for(v2) == str(row.get("evidence_class") or ""),
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


def publications(
    clone: Path, drawered: dict[str, set[tuple[str, str]]], control: bool = False
) -> list[dict]:
    """Per review: what the current family policy publishes under each of v2, v3
    and v4, with the receipts that version drawers withheld."""
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
        columns: dict[str, list[ScoredFinding]] = {
            "v2": [],
            "v3": [],
            "v4": [],
            "v4_1": [],
        }
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
            for version, withheld in drawered.items():
                if (task_id, str(cert["finding_id"])) not in withheld:
                    columns[version].append(item)
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
        out.append(
            {
                "task_id": task_id,
                "clone": clone.name,
                "control": control,
                "under_current_rule": under_current_rule,
                "recorded_published": sorted(str(x) for x in row["published"]),
                **{
                    f"{version}_published": ids(
                        select_for_publication(items, policy, e_values)
                    )
                    for version, items in columns.items()
                },
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
        version: {
            (r.task_id, r.candidate_id)
            for r in comparable
            if getattr(r, f"{version}_verdict")
        }
        for version in ("v2", "v3", "v4", "v4_1")
    }
    review_rows: list[dict] = []
    for name, control in clones:
        clone = CORPORA / name
        if (clone / ".attest" / "ledger.jsonl").exists():
            review_rows.extend(publications(clone, drawered, control))

    def certifying(version: str, rows: list[ReceiptReplay]) -> int:
        return sum(1 for r in rows if not getattr(r, f"{version}_verdict"))

    controls = [r for r in comparable if r.control]
    payload = {
        "schema_version": "attest.intent-v4-replay.v2",
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
        "certifying": {
            version: certifying(version, comparable)
            for version in ("v2", "v3", "v4", "v4_1")
        },
        "certifying_value_class": {
            version: certifying(version, [r for r in comparable if r.shape == "value"])
            for version in ("v2", "v3", "v4", "v4_1")
        },
        "control_receipts": len(controls),
        "control_certifying": {
            version: certifying(version, controls)
            for version in ("v2", "v3", "v4", "v4_1")
        },
        "drawered_by_v4_not_v3": [
            {"task": r.task_id, "candidate": r.candidate_id, "clone": r.clone, "path": r.path,
             "clause_a": r.clause_a, "clause_b": r.clause_b, "clause_c": r.clause_c,
             "verdict": r.v4_verdict}
            for r in comparable
            if not r.v3_verdict and r.v4_verdict
        ],
        "certifying_under_v4_not_v3": [
            {"task": r.task_id, "candidate": r.candidate_id, "clone": r.clone, "path": r.path}
            for r in comparable
            if r.v3_verdict and not r.v4_verdict
        ],
        "clause_incidence_over_value_receipts": {
            clause: sum(1 for r in comparable if getattr(r, f"clause_{clause}"))
            for clause in ("a", "b", "c", "c_v4_1")
        },
        # D-134: the receipts v4 drawered on a mention v4.1 does not recognise,
        # and (the direction that must stay empty) any v4.1 drawers and v4 did not
        "certifying_under_v4_1_not_v4": [
            {"task": r.task_id, "candidate": r.candidate_id, "clone": r.clone,
             "path": r.path, "control": r.control,
             "dropped_evidence": r.intent_evidence_v4,
             "pinned_values": r.pinned_values,
             "clause_a": r.clause_a, "clause_b": r.clause_b}
            for r in comparable
            if r.v4_verdict and not r.v4_1_verdict
        ],
        "drawered_by_v4_1_not_v4": [
            {"task": r.task_id, "candidate": r.candidate_id, "clone": r.clone,
             "path": r.path, "control": r.control}
            for r in comparable
            if not r.v4_verdict and r.v4_1_verdict
        ],
        "clause_incidence_over_v3_publishers": {
            clause: sum(
                1
                for r in comparable
                if not r.v3_verdict and getattr(r, f"clause_{clause}")
            )
            for clause in ("a", "b", "c", "c_v4_1")
        },
        "reviews": len(review_rows),
        "reviews_under_current_rule": sum(1 for r in review_rows if r["under_current_rule"]),
        "reviews_reproducing_their_ledger": sum(
            1
            for r in review_rows
            if r["under_current_rule"] and r["v2_published"] == r["recorded_published"]
        ),
        "review_published": {
            version: sum(len(r[f"{version}_published"]) for r in review_rows)
            for version in ("v2", "v3", "v4", "v4_1")
        },
        "control_review_published": {
            version: sum(
                len(r[f"{version}_published"]) for r in review_rows if r["control"]
            )
            for version in ("v2", "v3", "v4", "v4_1")
        },
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
        f"certifying   v2 {payload['certifying']['v2']}  v3 {payload['certifying']['v3']}  "
        f"v4 {payload['certifying']['v4']}  v4.1 {payload['certifying']['v4_1']}\n"
        f"  value class v2 {payload['certifying_value_class']['v2']}  "
        f"v3 {payload['certifying_value_class']['v3']}  "
        f"v4 {payload['certifying_value_class']['v4']}  "
        f"v4.1 {payload['certifying_value_class']['v4_1']}\n"
        f"controls ({payload['control_receipts']}) certifying   "
        f"v2 {payload['control_certifying']['v2']}  v3 {payload['control_certifying']['v3']}  "
        f"v4 {payload['control_certifying']['v4']}  "
        f"v4.1 {payload['control_certifying']['v4_1']}\n"
        f"clauses drawering a v3 publisher: "
        f"{payload['clause_incidence_over_v3_publishers']}\n"
        f"reviews {payload['reviews']} ({payload['reviews_reproducing_their_ledger']} of "
        f"{payload['reviews_under_current_rule']} under today's family rule reproduce their "
        f"ledger): published {payload['review_published']}; "
        f"controls {payload['control_review_published']}; skipped receipts {len(skipped)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
