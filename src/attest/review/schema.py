"""The four-piece finding schema. All four pieces or the finding is void."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from attest.review.diffs import DiffInfo

# JSON schema the proposer model is constrained to (structured output).
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": 5,
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


@dataclass
class Finding:
    claim: str
    file: str
    line: int
    failure_scenario: str
    falsification_plan: str
    votes: int = 1  # samples independently asserting this finding
    sample_ids: list[int] = field(default_factory=list)

    @property
    def finding_id(self) -> str:
        key = f"{self.file}:{self.line}:{self.claim}".encode()
        return hashlib.sha256(key).hexdigest()[:10]


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?。!?]+", text.strip()) if s.strip()])


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
    file = str(anchor["file"]).replace("\\", "/").lstrip("./")
    try:
        line = int(anchor["line"])
    except (TypeError, ValueError):
        return None, "non-integer anchor line"
    if not diff.anchor_in_hunk(file, line):
        return None, f"anchor {file}:{line} not inside any diff hunk"
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
