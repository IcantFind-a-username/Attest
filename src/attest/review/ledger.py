"""Local append-only ledger: .attest/ledger.jsonl in the reviewed repo.

One line per event. Review entries follow the spec schema (ts, task_id,
finding_id, channels_bought, spend, wealth_final, action, feedback?);
alpha-tightening events and monitor alarms are separate kinds. The ledger is
also the label source for the alpha auto-tighten rule and, eventually
(>= 500 labels, global only), recalibration.
"""

from __future__ import annotations

import json
import math
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ALPHA_FLOOR = 0.01
PRECISION_TARGET = 0.90
PRECISION_WINDOW = 50
_SECRET_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")
_MAX_DURABLE_LEDGER_BYTES = 64 * 1024 * 1024
_MAX_DURABLE_LEDGER_ROW_BYTES = 1024 * 1024

# feedback label -> precision polarity. "ambiguous" labels are excluded from
# both the numerator and denominator of surfaced_precision (see
# Ledger.record_feedback for why 'dismiss' is ambiguous rather than false).
_LABEL_POLARITY: dict[str, str] = {
    "fix": "true",
    "good": "true",
    "wontfix": "true",
    "wrong": "false",
    "dismiss": "ambiguous",
}
_AMBIGUOUS_POLARITY = "ambiguous"
_DELIVERY_KINDS = {
    "delivery_attempt_intent",
    "delivery_attempt_settlement",
    "delivery_journal_finalization",
}


def _require_row_fields(
    entry: dict[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    allowed = required | (set() if optional is None else optional)
    if not required <= set(entry) <= allowed:
        raise ValueError(f"{entry.get('kind', 'ledger')} row has an invalid field set")
    for field in ("ts", "kind"):
        if field in required and (type(entry[field]) is not str or not entry[field]):
            raise ValueError(f"ledger {field} must be a non-empty exact string")


def _required_string(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if type(value) is not str or not value:
        raise ValueError(f"ledger {field} must be a non-empty exact string")
    return value


def _require_finite_nonnegative(value: object, field: str) -> None:
    if type(value) not in {int, float}:
        raise ValueError(f"ledger {field} must be a finite non-negative number")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"ledger {field} must be a finite non-negative number")


def _label_polarity(entry: dict[str, Any]) -> str:
    """Precision polarity of one feedback row, re-deriving it for older ledger
    rows written before `label_polarity` was recorded."""
    _require_row_fields(
        entry,
        {"ts", "kind", "finding_id", "feedback"},
        {"label_polarity"},
    )
    _required_string(entry, "finding_id")
    feedback = entry.get("feedback")
    if type(feedback) is not str or feedback not in _LABEL_POLARITY:
        raise ValueError("feedback label is invalid")
    derived = _LABEL_POLARITY[feedback]
    if "label_polarity" not in entry:
        return derived
    recorded = entry["label_polarity"]
    if type(recorded) is not str or recorded not in {
        "true",
        "false",
        _AMBIGUOUS_POLARITY,
    }:
        raise ValueError("feedback label_polarity is invalid")
    if recorded != derived:
        raise ValueError("feedback label_polarity contradicts feedback")
    return recorded


def _surfaced_projection(
    entries: list[dict[str, Any]],
) -> tuple[tuple[str, ...], dict[str, int]]:
    """Return surfaced order and each finding's first author-visible row."""

    from attest.review.ci import reconcile_delivery_rows

    final_tasks: set[str] = set()
    delivery_tasks: set[str] = set()
    comment_tasks: set[str] = set()
    for entry in entries:
        kind = entry.get("kind")
        if kind == "ci_final":
            _require_row_fields(
                entry,
                {"ts", "kind", "task_id", "decisions", "spend_usd"},
                {"elapsed_s"},
            )
            task_id = _required_string(entry, "task_id")
            if type(entry["decisions"]) is not list:
                raise ValueError("ci_final decisions must be an exact list")
            _require_finite_nonnegative(entry["spend_usd"], "spend_usd")
            if "elapsed_s" in entry:
                _require_finite_nonnegative(entry["elapsed_s"], "elapsed_s")
            final_tasks.add(task_id)
        elif kind == "github_comment":
            _require_row_fields(
                entry,
                {"ts", "kind", "task_id", "phase", "outcome"},
                {"reason"},
            )
            task_id = _required_string(entry, "task_id")
            _required_string(entry, "phase")
            if type(entry["outcome"]) is not str or entry["outcome"] not in {
                "posted",
                "failed",
            }:
                raise ValueError("github_comment outcome is invalid")
            if "reason" in entry and type(entry["reason"]) is not str:
                raise ValueError("github_comment reason must be an exact string")
            comment_tasks.add(task_id)
        elif kind in _DELIVERY_KINDS:
            delivery_tasks.add(_required_string(entry, "task_id"))
    ci_tasks = final_tasks | delivery_tasks | comment_tasks
    delivered_by_attempt = {
        (task_id, event.attempt_id): tuple(
            finding_id
            for finding_id, _placement in event.members
        )
        for task_id in delivery_tasks
        for event in reconcile_delivery_rows(entries, task_id)[0]
        if event.outcome == "succeeded"
    }
    surfaced_ids: list[str] = []
    first_surface: dict[str, int] = {}
    for index, entry in enumerate(entries):
        finding_ids: tuple[str, ...] = ()
        if entry.get("kind") == "delivery_attempt_settlement":
            finding_ids = delivered_by_attempt.get(
                (
                    str(entry.get("task_id", "")),
                    str(entry.get("attempt_id", "")),
                ),
                (),
            )
        elif entry.get("kind") == "review":
            _require_row_fields(
                entry,
                {
                    "ts",
                    "kind",
                    "task_id",
                    "finding_id",
                    "channels_bought",
                    "spend",
                    "wealth_final",
                    "action",
                },
            )
            task_id = _required_string(entry, "task_id")
            finding_id = _required_string(entry, "finding_id")
            action = _required_string(entry, "action")
            channels = entry["channels_bought"]
            if type(channels) is not list or any(type(item) is not str for item in channels):
                raise ValueError("review channels_bought must be an exact string list")
            _require_finite_nonnegative(entry["spend"], "spend")
            _require_finite_nonnegative(entry["wealth_final"], "wealth_final")
            if action not in {
                "discard",
                "drawer",
                "surface",
                "overflow_surface",
                "verified_discard",
                "verified_drawer",
                "verified_surface",
            }:
                raise ValueError("review action is invalid")
            if action.endswith("surface") and task_id not in ci_tasks:
                finding_ids = (finding_id,)
        for finding_id in finding_ids:
            if finding_id in surfaced_ids:
                surfaced_ids.remove(finding_id)
            if finding_id:
                first_surface.setdefault(finding_id, index)
                surfaced_ids.append(finding_id)
    return tuple(surfaced_ids), first_surface


def _surfaced_finding_ids(entries: list[dict[str, Any]]) -> tuple[str, ...]:
    """Return the ordered, de-duplicated author-visible finding population."""

    return _surfaced_projection(entries)[0]


def _labeled_surfaced(
    entries: list[dict[str, Any]],
    surfaced_ids: tuple[str, ...],
    first_surface: dict[str, int],
    *,
    window: int | None = None,
) -> tuple[tuple[str, str], ...]:
    """Project latest labels written after first author-visible delivery."""

    population = surfaced_ids if window is None else surfaced_ids[-window:]
    included = set(population)
    polarities: dict[str, str] = {}
    for index, entry in enumerate(entries):
        finding_id = str(entry.get("finding_id", ""))
        if (
            entry.get("kind") != "feedback"
            or finding_id not in included
            or index <= first_surface[finding_id]
        ):
            continue
        polarities[finding_id] = _label_polarity(entry)
    return tuple(
        (finding_id, polarities[finding_id])
        for finding_id in population
        if finding_id in polarities
        and polarities[finding_id] != _AMBIGUOUS_POLARITY
    )


def _watermark(
    entries: list[dict[str, Any]], tighten_index: int
) -> tuple[tuple[str, str], ...] | None:
    """Reconstruct the rolling precision population at one tightening."""

    for tighten_entry in entries[: tighten_index + 1]:
        if tighten_entry.get("kind") != "alpha_tightened":
            continue
        if "label_count" in tighten_entry:
            recorded = tighten_entry["label_count"]
            if type(recorded) is not int or recorded < 0:
                return None
    prefix = entries[:tighten_index]
    try:
        surfaced_ids, first_surface = _surfaced_projection(prefix)
        labeled = _labeled_surfaced(
            prefix,
            surfaced_ids,
            first_surface,
            window=PRECISION_WINDOW,
        )
        return tuple(sorted(labeled))
    except ValueError:
        return None


def _alpha_number(value: object, context: str) -> float:
    """Require one exact finite alpha in the configured legal range."""

    if type(value) not in {int, float}:
        raise ValueError(f"{context} must be finite and in (0, 1)")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or not 0 < number < 1:
        raise ValueError(f"{context} must be finite and in (0, 1)")
    return number


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


def _strict_object_pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in rows:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_nonfinite_constant(_: str) -> object:
    raise ValueError("non-finite JSON number")


def _require_finite_json(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("strict ledger contains a non-finite JSON number")
    if isinstance(value, list):
        for item in value:
            _require_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            _require_finite_json(item)


def _open_directory_path(path: Path, flags: int) -> int:
    """Open every absolute path component without following an ancestor symlink."""

    absolute = path if path.is_absolute() else Path.cwd() / path
    descriptors: list[int] = []
    try:
        current = os.open("/", flags)
        descriptors.append(current)
        for component in absolute.parts[1:]:
            current = os.open(component, flags, dir_fd=current)
            descriptors.append(current)
    except OSError as exc:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise ValueError("strict ledger path contains a symlink or unsafe ancestor") from exc
    for descriptor in descriptors[:-1]:
        os.close(descriptor)
    return descriptors[-1]


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

    def append_durable(self, entry: dict[str, Any]) -> None:
        """Durably append one security-critical row under a single-writer contract."""
        if not all(
            hasattr(os, name) and type(getattr(os, name)) is int
            for name in ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
        ):
            raise ValueError("durable ledger filesystem capabilities are unavailable")
        redacted = _redact(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **entry},
            _known_secrets(),
        )
        try:
            data = (
                json.dumps(redacted, ensure_ascii=False, allow_nan=False) + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("durable ledger row is not finite JSON") from exc
        if not 1 <= len(data) <= _MAX_DURABLE_LEDGER_ROW_BYTES:
            raise ValueError("durable ledger row exceeds the size limit")

        root_descriptor: int | None = None
        parent_descriptor: int | None = None
        file_descriptor: int | None = None
        try:
            directory_flags = (
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            root_descriptor = _open_directory_path(self.root, directory_flags)
            created_parent = False
            try:
                os.mkdir(".attest", mode=0o700, dir_fd=root_descriptor)
                created_parent = True
            except FileExistsError:
                pass
            parent_descriptor = os.open(
                ".attest", directory_flags, dir_fd=root_descriptor
            )
            if created_parent:
                os.fsync(root_descriptor)

            append_flags = os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW
            created_file = False
            try:
                file_descriptor = os.open(
                    "ledger.jsonl", append_flags, dir_fd=parent_descriptor
                )
            except FileNotFoundError:
                file_descriptor = os.open(
                    "ledger.jsonl",
                    append_flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                created_file = True
            metadata = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size < 0
                or metadata.st_size + len(data) > _MAX_DURABLE_LEDGER_BYTES
            ):
                raise ValueError(
                    "durable ledger must be a bounded single-link regular file"
                )
            remaining = memoryview(data)
            while remaining:
                written = os.write(file_descriptor, remaining)
                if written <= 0:
                    raise OSError("short durable ledger write")
                remaining = remaining[written:]
            os.fsync(file_descriptor)
            if created_file:
                os.fsync(parent_descriptor)
        finally:
            for descriptor in (file_descriptor, parent_descriptor, root_descriptor):
                if descriptor is not None:
                    os.close(descriptor)

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

    def entries_strict(self) -> list[dict[str, Any]]:
        """Fresh same-FD snapshot for current measurement authority.

        Historical readers retain ``entries``.  Current outcome construction
        rejects malformed, duplicate-key, non-finite, linked, or racing ledger
        bytes instead of silently skipping them.
        """

        required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
        if any(
            not hasattr(os, name)
            or type(getattr(os, name)) is not int
            or getattr(os, name) == 0
            for name in required
        ):
            raise ValueError("strict ledger filesystem capabilities are unavailable")
        descriptors: list[int] = []
        try:
            directory_flags = (
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            root_descriptor = _open_directory_path(self.root, directory_flags)
            descriptors.append(root_descriptor)
            try:
                parent_descriptor = os.open(
                    ".attest", directory_flags, dir_fd=root_descriptor
                )
            except FileNotFoundError:
                return []
            descriptors.append(parent_descriptor)
            try:
                file_descriptor = os.open(
                    "ledger.jsonl",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent_descriptor,
                )
            except FileNotFoundError:
                return []
            descriptors.append(file_descriptor)
            before = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 <= before.st_size <= _MAX_DURABLE_LEDGER_BYTES
            ):
                raise ValueError("strict ledger must be a bounded single-link regular file")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(file_descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise ValueError("strict ledger changed while it was read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                raise ValueError("strict ledger grew while it was read")
            after = os.fstat(file_descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ValueError("strict ledger changed while it was read")
            data = b"".join(chunks)
        except OSError as exc:
            raise ValueError("strict ledger path is missing or unsafe") from exc
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
        if not data:
            return []
        if not data.endswith(b"\n"):
            raise ValueError("strict ledger contains a truncated JSON row")
        entries: list[dict[str, Any]] = []
        for encoded_line in data.splitlines(keepends=True):
            if len(encoded_line) > _MAX_DURABLE_LEDGER_ROW_BYTES:
                raise ValueError("strict ledger row exceeds the size limit")
            if encoded_line == b"\n":
                raise ValueError("strict ledger contains an empty row")
            try:
                line = encoded_line[:-1].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("strict ledger is not UTF-8 JSON") from exc
            try:
                value = json.loads(
                    line,
                    object_pairs_hook=_strict_object_pairs,
                    parse_constant=_reject_nonfinite_constant,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError("strict ledger contains malformed JSON") from exc
            if type(value) is not dict:
                raise ValueError("strict ledger row must be an exact object")
            _require_finite_json(value)
            entries.append(value)
        return entries

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
        """Record a human label for a surfaced finding.

        Labels and their precision polarity:
          - 'fix'     -> true  (finding was correct, developer applied the fix)
          - 'good'    -> true  (finding was correct)
          - 'wontfix' -> true  (finding was CORRECT but deliberately not acted
                         on -- out of scope, known, intentional, deferred; the
                         tool was right, so this must not be miscounted as a
                         false positive)
          - 'wrong'   -> false (finding was incorrect: a genuine false positive)
          - 'dismiss' -> ambiguous, legacy only. Historically 'dismiss'
                         conflated 'wrong' and 'wontfix', so its polarity
                         cannot be recovered after the fact. It is still
                         accepted for backward compatibility but is excluded
                         from precision entirely (see surfaced_precision) --
                         silently folding it into either bucket would corrupt
                         the precision SLA and the alpha auto-tighten rule.
        """
        polarity = _LABEL_POLARITY.get(feedback)
        if polarity is None:
            raise ValueError("feedback must be fix, good, wrong, wontfix, or dismiss")
        self.append(
            {
                "kind": "feedback",
                "finding_id": finding_id,
                "feedback": feedback,
                "label_polarity": polarity,
            }
        )

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
        evidence_class: str | None = None,
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
            "evidence_class": evidence_class,
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

    def surfaced_precision(
        self,
        window: int = PRECISION_WINDOW,
        *,
        entries: list[dict[str, Any]] | None = None,
        surfaced_ids: tuple[str, ...] | None = None,
    ) -> tuple[float | None, int]:
        """Precision over the last `window` surfaced findings that have
        feedback labels. Returns (precision or None, n_labeled)."""
        if type(window) is not int or window <= 0:
            raise ValueError("precision window must be an exact positive integer")
        entries = self.entries_strict() if entries is None else entries
        canonical_ids, first_surface = _surfaced_projection(entries)
        if surfaced_ids is None:
            surfaced_ids = canonical_ids
        elif surfaced_ids != canonical_ids:
            raise ValueError("surfaced finding population does not match ledger evidence")
        else:
            surfaced_ids = canonical_ids
        # ambiguous labels (legacy 'dismiss') are excluded from BOTH the
        # numerator and the denominator -- never silently counted as either
        # a true or a false label.
        labeled = _labeled_surfaced(
            entries, surfaced_ids, first_surface, window=window
        )
        if not labeled:
            return None, 0
        precision = sum(1 for _, polarity in labeled if polarity == "true") / len(labeled)
        return precision, len(labeled)

    def surfaced_finding_ids(
        self, entries: list[dict[str, Any]] | None = None
    ) -> tuple[str, ...]:
        """Return the exact finding population used by surfaced precision."""

        return _surfaced_finding_ids(
            self.entries_strict() if entries is None else entries
        )

    def maybe_tighten_alpha(self, alpha: float, enabled: bool) -> tuple[float, str | None]:
        """MVP auto-tighten rule: rolling surfaced precision < 90% (with at
        least 10 labels) halves alpha, floored at 0.01. Recorded in the ledger
        (`label_count` is the precision-bearing population snapshot);
        configurable off."""
        if not enabled:
            return alpha, None
        entries = self.entries_strict()
        surfaced_ids, first_surface = _surfaced_projection(entries)
        all_labeled = _labeled_surfaced(entries, surfaced_ids, first_surface)
        rolling_labeled = _labeled_surfaced(
            entries,
            surfaced_ids,
            first_surface,
            window=PRECISION_WINDOW,
        )
        precision_state = tuple(sorted(rolling_labeled))
        last_tighten_index = next(
            (
                index
                for index in range(len(entries) - 1, -1, -1)
                if entries[index].get("kind") == "alpha_tightened"
            ),
            None,
        )
        # Watermark: never re-halve on the same rolling precision population.
        # Reconstructing it from the historical prefix avoids trusting the
        # legacy label_count field and keeps the gate aligned with the window.
        if last_tighten_index is not None:
            watermark = _watermark(entries, last_tighten_index)
            if watermark is None or precision_state == watermark:
                return alpha, None
        n = len(rolling_labeled)
        precision = (
            None
            if not rolling_labeled
            else sum(
                polarity == "true" for _finding_id, polarity in rolling_labeled
            )
            / n
        )
        if precision is None or n < 10 or precision >= PRECISION_TARGET:
            return alpha, None
        new_alpha = max(ALPHA_FLOOR, alpha / 2)
        if new_alpha >= alpha:
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
                "label_count": len(all_labeled),
                "note": note,
            }
        )
        return new_alpha, note

    def current_alpha(self, configured: float) -> float:
        """Configured alpha, overridden by any recorded tightenings."""
        alpha = _alpha_number(configured, "configured alpha")
        for e in self.entries_strict():
            if e.get("kind") != "alpha_tightened":
                continue
            start = _alpha_number(e.get("from"), "alpha transition from")
            end = _alpha_number(e.get("to"), "alpha transition to")
            expected = max(ALPHA_FLOOR, start / 2)
            if end != expected or end >= start:
                raise ValueError("alpha transition violates the factory tightening chain")
            if start == alpha:
                alpha = end
        return alpha
