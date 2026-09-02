"""The four-piece finding schema. All four pieces or the finding is void."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from attest.review.diffs import DiffInfo, norm_path

# JSON schema the proposer model is constrained to (structured output).
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            # no maxItems: the structured-output API rejects it for arrays;
            # the <=5 cap is enforced by the prompt instead
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {
                        "type": "string",
                        "description": "At most 2 sentences: the high-severity defect",
                    },
                    "anchor": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                        },
                        "required": ["file", "line"],
                        "additionalProperties": False,
                    },
                    "failure_scenario": {
                        "type": "string",
                        "description": "Concrete input/state under which this blows up",
                    },
                    "falsification_plan": {
                        "type": "string",
                        "description": "How to check whether the claim is wrong",
                    },
                },
                "required": ["claim", "anchor", "failure_scenario", "falsification_plan"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ClusterMember:
    """One validated sample finding retained as cluster provenance."""

    sample_id: int
    file: str
    line: int
    claim: str


@dataclass
class Finding:
    claim: str
    file: str
    line: int
    failure_scenario: str
    falsification_plan: str
    votes: int = 1  # samples independently asserting this finding
    sample_ids: list[int] = field(default_factory=list)
    cluster_id: str = ""  # order-invariant discovery cluster identity (R-03)
    members: list[ClusterMember] = field(default_factory=list)

    @property
    def finding_id(self) -> str:
        key = f"{self.file}:{self.line}:{self.claim}".encode()
        return hashlib.sha256(key).hexdigest()[:10]


_CODE_SPAN_RE = re.compile(r"`[^`]*`")
_ABBREV_RE = re.compile(r"\b(e\.g\.|i\.e\.|etc\.|vs\.|cf\.|et al\.)", re.IGNORECASE)
# a sentence ends at .!? followed by whitespace + a capital/digit/quote, or at
# the end of the text — dots inside identifiers (Token.Error), decimals,
# ellipses, and common abbreviations do not count
_SENTENCE_END_RE = re.compile(r"[.!?。!?]+(?=\s+[A-Z0-9\"'`(]|\s*$)")


def _sentence_count(text: str) -> int:
    stripped = _CODE_SPAN_RE.sub(" ", text)
    stripped = _ABBREV_RE.sub(" ", stripped).strip()
    if not stripped:
        return 0
    return max(1, len(_SENTENCE_END_RE.findall(stripped)))


def validate_finding(raw: dict[str, Any], diff: DiffInfo) -> tuple[Finding | None, str]:
    """Return (finding, "") or (None, reason). Missing/invalid pieces void it."""
    for key in ("claim", "anchor", "failure_scenario", "falsification_plan"):
        if not raw.get(key):
            return None, f"missing {key}"
    anchor = raw["anchor"]
    if not isinstance(anchor, dict) or not anchor.get("file") or "line" not in anchor:
        return None, "malformed anchor"
    claim = str(raw["claim"]).strip()
    if _sentence_count(claim) > 2:
        return None, "claim exceeds 2 sentences"
    file = norm_path(str(anchor["file"]))
    try:
        line = int(anchor["line"])
    except (TypeError, ValueError):
        return None, "non-integer anchor line"
    canonical = diff.canonical_anchor(file, line)
    if canonical is None:
        return None, f"anchor {file}:{line} not inside any diff hunk"
    # store the canonical repository path: finding_id, dedup, tier-0 matching,
    # and inline comment paths must all use the real path, not git notation
    file = canonical
    return (
        Finding(
            claim=claim,
            file=file,
            line=line,
            failure_scenario=str(raw["failure_scenario"]).strip(),
            falsification_plan=str(raw["falsification_plan"]).strip(),
        ),
        "",
    )
