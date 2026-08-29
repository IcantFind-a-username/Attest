"""Cross-sample dedup: merge findings that point at the same defect.

Two findings merge when their anchors are close (same file, within a few lines)
and their claims are lexically similar. Votes = number of distinct samples
asserting the merged finding (the S channel's input).
"""

from __future__ import annotations

import re

from attest.review.schema import Finding

LINE_SLACK = 3
# same defect, different wording: independent samples describe one bug very
# differently, so the lexical bar is graded by anchor agreement — an exact
# line match needs only weak overlap, a nearby line needs substantially more
# (calibrated on the first dogfood run, D-013)
JACCARD_EXACT_LINE = 0.15
JACCARD_NEAR_LINE = 0.35

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "be",
    "been",
    "to",
    "of",
    "in",
    "on",
    "and",
    "or",
    "if",
    "it",
    "this",
    "that",
    "with",
    "for",
    "as",
    "by",
    "can",
    "will",
    "may",
    "when",
    "not",
    "no",
}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)} - _STOP


def _similar(a: Finding, b: Finding) -> bool:
    if a.file != b.file or abs(a.line - b.line) > LINE_SLACK:
        return False
    ta = _tokens(a.claim) | _tokens(a.failure_scenario)
    tb = _tokens(b.claim) | _tokens(b.failure_scenario)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    threshold = JACCARD_EXACT_LINE if a.line == b.line else JACCARD_NEAR_LINE
    return jaccard >= threshold


def merge_findings(per_sample: list[list[Finding]]) -> list[Finding]:
    """per_sample[i] = validated findings from sample i. Returns merged
    candidates; votes counts distinct samples, not repeated mentions."""
    merged: list[Finding] = []
    for sample_id, findings in enumerate(per_sample):
        for f in findings:
            f.sample_ids = [sample_id]
            match = next((m for m in merged if _similar(m, f)), None)
            if match is None:
                merged.append(f)
            elif sample_id not in match.sample_ids:
                match.sample_ids.append(sample_id)
                match.votes = len(match.sample_ids)
                # keep the longer, more specific text of the two
                if len(f.failure_scenario) > len(match.failure_scenario):
                    match.failure_scenario = f.failure_scenario
                if len(f.falsification_plan) > len(match.falsification_plan):
                    match.falsification_plan = f.falsification_plan
    return merged
