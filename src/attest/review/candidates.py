"""Task-scoped persistence for review candidates."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.review.gate import GateResult
from attest.review.schema import Finding


@dataclass(frozen=True)
class StoredCandidate:
    task_id: str
    finding: Finding
    wealth: float
    action: str
    alpha: float


class CandidateStore:
    def __init__(self, repo: Path):
        self.repo = repo

    @property
    def path(self) -> Path:
        return self.repo / ".attest" / "candidates.jsonl"

    def append(self, task_id: str, alpha: float, results: list[GateResult]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for result in results:
                finding = result.finding
                fh.write(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "finding_id": finding.finding_id,
                            "file": finding.file,
                            "line": finding.line,
                            "claim": finding.claim,
                            "failure_scenario": finding.failure_scenario,
                            "falsification_plan": finding.falsification_plan,
                            "votes": finding.votes,
                            "sample_ids": finding.sample_ids,
                            "wealth": result.wealth,
                            "action": result.action,
                            "alpha": alpha,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def load(self, task_id: str | None = None) -> list[StoredCandidate]:
        if not self.path.is_file():
            return []
        candidates: list[StoredCandidate] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line, parse_constant=CandidateStore._reject_json_constant)
                candidate = self._from_record(record)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if task_id is None or candidate.task_id == task_id:
                candidates.append(candidate)
        return candidates

    def latest(self, finding_id: str, task_id: str | None = None) -> StoredCandidate | None:
        matches = [
            candidate
            for candidate in self.load(task_id)
            if candidate.finding.finding_id == finding_id
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _from_record(record: Any) -> StoredCandidate:
        if not isinstance(record, dict):
            raise TypeError("candidate row must be an object")
        sample_ids = record.get("sample_ids", [])
        if not isinstance(sample_ids, list):
            raise TypeError("sample_ids must be a list")
        finding = Finding(
            claim=CandidateStore._string(record, "claim"),
            file=CandidateStore._string(record, "file"),
            line=CandidateStore._integer(record, "line"),
            failure_scenario=CandidateStore._string(record, "failure_scenario"),
            falsification_plan=CandidateStore._string(record, "falsification_plan"),
            votes=CandidateStore._integer(record, "votes"),
            sample_ids=[int(sample_id) for sample_id in sample_ids],
        )
        return StoredCandidate(
            task_id=CandidateStore._string(record, "task_id"),
            finding=finding,
            wealth=CandidateStore._number(record, "wealth"),
            action=CandidateStore._string(record, "action"),
            alpha=CandidateStore._number(record, "alpha"),
        )

    @staticmethod
    def _string(record: dict[str, Any], key: str) -> str:
        value = record[key]
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} must be a non-empty string")
        return value

    @staticmethod
    def _integer(record: dict[str, Any], key: str) -> int:
        value = record[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        return value

    @staticmethod
    def _number(record: dict[str, Any], key: str) -> float:
        value = record[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{key} must be a number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{key} must be finite")
        return number

    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")
