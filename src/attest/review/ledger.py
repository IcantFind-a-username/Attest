"""Local append-only ledger: .attest/ledger.jsonl in the reviewed repo.

One line per event. Review entries follow the spec schema (ts, task_id,
finding_id, channels_bought, spend, wealth_final, action, feedback?);
alpha-tightening events and monitor alarms are separate kinds. The ledger is
also the label source for the alpha auto-tighten rule and, eventually
(>= 500 labels, global only), recalibration.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALPHA_FLOOR = 0.01
PRECISION_TARGET = 0.90
PRECISION_WINDOW = 50
_SECRET_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")


def _known_secrets() -> tuple[str, ...]:
    return tuple(
        value
        for name, value in os.environ.items()
        if value and any(part in name.upper() for part in _SECRET_NAME_PARTS)
    )


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    return value


@dataclass
class Ledger:
    root: Path  # repo root; entries live in root/.attest/ledger.jsonl

    @property
    def path(self) -> Path:
        return self.root / ".attest" / "ledger.jsonl"

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = _redact(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **entry},
            _known_secrets(),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def record_review(
        self,
        task_id: str,
        finding_id: str,
        channels_bought: list[str],
        spend: float,
        wealth_final: float,
        action: str,
    ) -> None:
        self.append(
            {
                "kind": "review",
                "task_id": task_id,
                "finding_id": finding_id,
                "channels_bought": channels_bought,
                "spend": round(spend, 6),
                "wealth_final": round(wealth_final, 4),
                "action": action,
            }
        )

    def record_feedback(self, finding_id: str, feedback: str) -> None:
        """feedback: 'fix' | 'good' -> true label; 'dismiss' -> false label."""
        if feedback not in ("fix", "good", "dismiss"):
            raise ValueError("feedback must be fix, good, or dismiss")
        self.append({"kind": "feedback", "finding_id": finding_id, "feedback": feedback})

    def record_verification(
        self,
        *,
        task_id: str,
        finding_id: str,
        outcome: str,
        reason: str,
        elapsed_s: float,
        network_blocked: bool,
        evidence: str,
        mode: str | None = None,
        base_sha: str | None = None,
        head_sha: str | None = None,
        head_runs: list[str] | None = None,
        base_runs: list[str] | None = None,
        repeats: int | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "kind": "verification",
            "task_id": task_id,
            "finding_id": finding_id,
            "outcome": outcome,
            "reason": reason,
            "elapsed_s": round(elapsed_s, 6),
            "network_blocked": network_blocked,
            "evidence": evidence,
        }
        differential_fields = {
            "mode": mode,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "head_runs": head_runs,
            "base_runs": base_runs,
            "repeats": repeats,
        }
        entry.update(
            {name: value for name, value in differential_fields.items() if value is not None}
        )
        self.append(entry)

    def record_ci_final(
        self,
        *,
        task_id: str,
        decisions: list[dict[str, Any]],
        spend_usd: float,
        elapsed_s: float | None = None,
    ) -> None:
        """Record authoritative post-verification decisions and total run spend."""
        entry: dict[str, Any] = {
            "kind": "ci_final",
            "task_id": task_id,
            "decisions": decisions,
            "spend_usd": round(spend_usd, 6),
        }
        if elapsed_s is not None:
            entry["elapsed_s"] = round(elapsed_s, 2)
        self.append(entry)

    def surfaced_precision(self, window: int = PRECISION_WINDOW) -> tuple[float | None, int]:
        """Precision over the last `window` surfaced findings that have
        feedback labels. Returns (precision or None, n_labeled)."""
        entries = self.entries()
        final_tasks = {
            str(e["task_id"])
            for e in entries
            if e.get("kind") == "ci_final" and isinstance(e.get("task_id"), str)
        }
        surfaced_ids: list[str] = []
        for e in entries:
            if e.get("kind") == "ci_final":
                for decision in e.get("decisions", []):
                    if isinstance(decision, dict) and decision.get("action") == "surface":
                        fid = str(decision.get("finding_id", ""))
                        if fid in surfaced_ids:
                            surfaced_ids.remove(fid)
                        if fid:
                            surfaced_ids.append(fid)
            if e.get("kind") == "review" and str(e.get("action", "")).endswith("surface"):
                if str(e.get("task_id", "")) in final_tasks:
                    continue
                fid = e["finding_id"]
                if fid in surfaced_ids:  # re-verification must not double-count
                    surfaced_ids.remove(fid)
                surfaced_ids.append(fid)
        labels: dict[str, bool] = {}
        for e in entries:
            if e.get("kind") == "feedback":
                labels[e["finding_id"]] = e["feedback"] in ("fix", "good")
        labeled = [(fid, labels[fid]) for fid in surfaced_ids[-window:] if fid in labels]
        if not labeled:
            return None, 0
        precision = sum(1 for _, ok in labeled if ok) / len(labeled)
        return precision, len(labeled)

    def maybe_tighten_alpha(self, alpha: float, enabled: bool) -> tuple[float, str | None]:
        """MVP auto-tighten rule: rolling surfaced precision < 90% (with at
        least 10 labels) halves alpha, floored at 0.01. Recorded in the ledger;
        configurable off."""
        if not enabled:
            return alpha, None
        entries = self.entries()
        n_labels = sum(1 for e in entries if e.get("kind") == "feedback")
        last_tighten = next(
            (e for e in reversed(entries) if e.get("kind") == "alpha_tightened"), None
        )
        # watermark: never re-halve on the same stale label window — a new
        # tightening needs at least one label recorded since the last one
        if last_tighten is not None and last_tighten.get("label_count") == n_labels:
            return alpha, None
        precision, n = self.surfaced_precision()
        if precision is None or n < 10 or precision >= PRECISION_TARGET:
            return alpha, None
        new_alpha = max(ALPHA_FLOOR, alpha / 2)
        if new_alpha == alpha:
            return alpha, None
        note = (
            f"precision {precision:.2f} over last {n} labeled surfaced findings "
            f"< {PRECISION_TARGET:.0%}: alpha {alpha} -> {new_alpha}"
        )
        self.append(
            {
                "kind": "alpha_tightened",
                "from": alpha,
                "to": new_alpha,
                "label_count": n_labels,
                "note": note,
            }
        )
        return new_alpha, note

    def current_alpha(self, configured: float) -> float:
        """Configured alpha, overridden by any recorded tightenings."""
        alpha = configured
        for e in self.entries():
            if e.get("kind") == "alpha_tightened" and e.get("from") == alpha:
                alpha = float(e["to"])
        return alpha
