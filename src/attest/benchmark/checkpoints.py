"""Crash-safe, exactly-once checkpoints for provider subcalls.

The provider interface is synchronous, so ``dispatched`` without a durable
response is inherently uncertain. Such a record becomes ``ambiguous_cost`` on
resume and is never called again automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Any

from attest.review.budget import CHARS_PER_TOKEN
from attest.review.config import load_pricing
from attest.review.proposer import Provider, ProviderResult

CALL_CHECKPOINT_SCHEMA_VERSION = "3"
CALL_ARTIFACT_SCHEMA_VERSION = "2"
CALL_COST_SCHEMA_VERSION = "2"
STATE_RESERVED = "reserved"
STATE_DISPATCHED = "dispatched"
STATE_RESPONSE_PERSISTED = "response_persisted"
STATE_CONSUMED = "consumed"
STATE_AMBIGUOUS_COST = "ambiguous_cost"
CALL_STATES = frozenset(
    {
        STATE_RESERVED,
        STATE_DISPATCHED,
        STATE_RESPONSE_PERSISTED,
        STATE_CONSUMED,
        STATE_AMBIGUOUS_COST,
    }
)
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


class AmbiguousCostError(RuntimeError):
    """A call may have reached the provider but has no durable response."""


class CheckpointedProvider:
    """Persist every provider call transition and replay only durable responses."""

    def __init__(
        self,
        inner: Provider,
        *,
        root: Path,
        trial_id: str,
        model_id: str,
        binding_sha256: str,
        on_transition: Callable[[str, str], None] | None = None,
    ) -> None:
        if not trial_id:
            raise ValueError("trial_id must be non-empty")
        if _DIGEST_PATTERN.fullmatch(binding_sha256) is None:
            raise ValueError("binding_sha256 must be a lowercase SHA-256 digest")
        pricing = load_pricing()
        try:
            model = pricing["models"][model_id]
        except KeyError:
            raise ValueError(f"no pricing for model {model_id!r}") from None
        self._input_price = float(model["input_per_mtok"]) / 1e6
        self._output_price = float(model["output_per_mtok"]) / 1e6
        self._inner = inner
        self._root = root
        self._trial_id = trial_id
        self._model_id = model_id
        self._binding_sha256 = binding_sha256
        self._on_transition = on_transition
        self._calls_dir = root / "calls"
        self._artifacts_dir = root / "artifacts"
        self._costs_path = root / "costs.jsonl"
        self._calls_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._index = 0
        self._index_lock = Lock()
        self._ledger_lock = Lock()
        self._ambiguous_call_ids: set[str] = set()
        paths = sorted(self._calls_dir.glob("*.json"))
        checkpoints: list[dict[str, object]] = []
        for path in paths:
            checkpoint = self._load(path)
            checkpoints.append(checkpoint)
            if checkpoint["state"] in {STATE_CONSUMED, STATE_AMBIGUOUS_COST}:
                self._assert_terminal_reconciliation(checkpoint, path)
        self._assert_no_orphan_evidence(checkpoints)

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        request = {
            "system_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "schema_sha256": _digest(schema),
            "max_tokens": max_tokens,
            "timeout_s": timeout_s,
        }
        request_sha256 = _digest(request)
        with self._index_lock:
            ordinal = self._index
            self._index += 1
        call_id = f"{self._trial_id}:{ordinal}"
        path = self._calls_dir / f"{ordinal:06d}.json"

        if path.exists():
            checkpoint = self._load(path)
            if checkpoint["trial_id"] != self._trial_id:
                raise ValueError(
                    f"call checkpoint {path.name} belongs to a different trial"
                )
            if checkpoint["request_sha256"] != request_sha256:
                raise ValueError(
                    f"call checkpoint {path.name} request drifted before provider execution"
                )
            state = checkpoint["state"]
            if state == STATE_DISPATCHED:
                checkpoint = self._recover_or_mark_ambiguous(path, checkpoint)
                state = checkpoint["state"]
            if state == STATE_AMBIGUOUS_COST:
                self._assert_terminal_reconciliation(checkpoint, path)
                self._ambiguous_call_ids.add(call_id)
                raise AmbiguousCostError(
                    f"call {call_id} is ambiguous_cost; automatic replay is blocked"
                )
            if state in {STATE_RESPONSE_PERSISTED, STATE_CONSUMED}:
                response = self._response(checkpoint, path)
                if state == STATE_RESPONSE_PERSISTED:
                    checkpoint = self._consume(path, checkpoint)
                else:
                    self._assert_terminal_reconciliation(checkpoint, path)
                return response
            if state != STATE_RESERVED:
                raise ValueError(f"call checkpoint {path.name} has unsupported state {state!r}")
        else:
            checkpoint = {
                "schema_version": CALL_CHECKPOINT_SCHEMA_VERSION,
                "trial_id": self._trial_id,
                "call_id": call_id,
                "ordinal": ordinal,
                "model_id": self._model_id,
                "binding_sha256": self._binding_sha256,
                "request_sha256": request_sha256,
                "state": STATE_RESERVED,
                "reserved_usd": (
                    (len(system) + len(prompt)) / CHARS_PER_TOKEN * self._input_price
                    + max_tokens * self._output_price
                ),
                "response": None,
                "response_sha256": None,
                "cost_usd": None,
                "artifact_path": None,
                "artifact_sha256": None,
            }
            self._commit(path, checkpoint)

        checkpoint["state"] = STATE_DISPATCHED
        self._commit(path, checkpoint)
        try:
            response = self._inner.sample(
                system,
                prompt,
                schema,
                max_tokens,
                timeout_s=timeout_s,
            )
        except BaseException:
            self._finalize_ambiguous(path, checkpoint)
            raise
        response_payload = {
            "text": response.text,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }
        artifact = self._artifact_payload(
            checkpoint,
            outcome="settled",
            response=response_payload,
            cost_usd=(
                response.input_tokens * self._input_price
                + response.output_tokens * self._output_price
            ),
        )
        artifact_path, artifact_sha256 = self._write_artifact(
            _ordinal(checkpoint), artifact
        )
        checkpoint.update(
            {
                "state": STATE_RESPONSE_PERSISTED,
                "response": response_payload,
                "response_sha256": _digest(response_payload),
                "cost_usd": artifact["cost_usd"],
                "artifact_path": artifact_path,
                "artifact_sha256": artifact_sha256,
            }
        )
        self._commit(path, checkpoint)
        self._consume(path, checkpoint)
        return response

    def raise_if_ambiguous(self) -> None:
        """Withhold the enclosing result if product code caught a provider error."""
        self.reconciliation_records()

    def reconciliation_records(self) -> tuple[dict[str, object], ...]:
        """Return one verified spend/artifact join row per terminal paid call."""
        records: list[dict[str, object]] = []
        ambiguous: list[str] = []
        checkpoints: list[dict[str, object]] = []
        for path in sorted(self._calls_dir.glob("*.json")):
            checkpoint = self._load(path)
            state = checkpoint["state"]
            if state == STATE_DISPATCHED:
                checkpoint = self._recover_or_mark_ambiguous(path, checkpoint)
                state = checkpoint["state"]
            if state == STATE_RESPONSE_PERSISTED:
                checkpoint = self._consume(path, checkpoint)
                state = checkpoint["state"]
            if state == STATE_RESERVED:
                raise ValueError(
                    f"call {checkpoint['call_id']} is reserved but incomplete; claims remain "
                    "withheld"
                )
            self._assert_terminal_reconciliation(checkpoint, path)
            checkpoints.append(checkpoint)
            record = self._expected_cost_row(checkpoint)
            records.append(record)
            if state == STATE_AMBIGUOUS_COST:
                ambiguous.append(str(checkpoint["call_id"]))
        self._assert_no_orphan_evidence(checkpoints)
        ambiguous.extend(self._ambiguous_call_ids)
        if ambiguous:
            call_ids = ", ".join(sorted(set(ambiguous)))
            raise AmbiguousCostError(
                f"ambiguous_cost provider call(s) {call_ids}; claims remain withheld"
            )
        return tuple(records)

    def _consume(
        self, path: Path, checkpoint: dict[str, object]
    ) -> dict[str, object]:
        self._verify_artifact(checkpoint)
        self._settle_once(checkpoint)
        checkpoint["state"] = STATE_CONSUMED
        self._commit(path, checkpoint)
        return checkpoint

    def _finalize_ambiguous(
        self, path: Path, checkpoint: dict[str, object]
    ) -> dict[str, object]:
        artifact = self._artifact_payload(
            checkpoint,
            outcome=STATE_AMBIGUOUS_COST,
            response=None,
            cost_usd=None,
        )
        artifact_path, artifact_sha256 = self._write_artifact(
            _ordinal(checkpoint), artifact
        )
        checkpoint.update(
            {
                "state": STATE_DISPATCHED,
                "response": None,
                "response_sha256": None,
                "cost_usd": None,
                "artifact_path": artifact_path,
                "artifact_sha256": artifact_sha256,
            }
        )
        self._settle_once(checkpoint, outcome=STATE_AMBIGUOUS_COST)
        checkpoint["state"] = STATE_AMBIGUOUS_COST
        self._commit(path, checkpoint)
        self._ambiguous_call_ids.add(str(checkpoint["call_id"]))
        return checkpoint

    def _recover_or_mark_ambiguous(
        self, path: Path, checkpoint: dict[str, object]
    ) -> dict[str, object]:
        artifact_path = self._artifact_path(_ordinal(checkpoint))
        if not artifact_path.exists():
            return self._finalize_ambiguous(path, checkpoint)
        artifact = self._load_artifact(artifact_path, checkpoint)
        if artifact["outcome"] == STATE_AMBIGUOUS_COST:
            relative = artifact_path.relative_to(self._root).as_posix()
            checkpoint.update(
                {
                    "artifact_path": relative,
                    "artifact_sha256": hashlib.sha256(
                        _canonical_bytes(artifact)
                    ).hexdigest(),
                }
            )
            self._settle_once(checkpoint, outcome=STATE_AMBIGUOUS_COST)
            checkpoint["state"] = STATE_AMBIGUOUS_COST
            self._commit(path, checkpoint)
            return checkpoint
        response = artifact.get("response")
        if not isinstance(response, dict):
            raise ValueError(
                f"call artifact {artifact_path.name} has no durable response"
            )
        checkpoint.update(
            {
                "state": STATE_RESPONSE_PERSISTED,
                "response": response,
                "response_sha256": artifact["response_sha256"],
                "cost_usd": artifact["cost_usd"],
                "artifact_path": artifact_path.relative_to(self._root).as_posix(),
                "artifact_sha256": hashlib.sha256(
                    _canonical_bytes(artifact)
                ).hexdigest(),
            }
        )
        self._commit(path, checkpoint)
        return checkpoint

    def _artifact_payload(
        self,
        checkpoint: Mapping[str, object],
        *,
        outcome: str,
        response: Mapping[str, object] | None,
        cost_usd: float | None,
    ) -> dict[str, object]:
        return {
            "schema_version": CALL_ARTIFACT_SCHEMA_VERSION,
            "trial_id": checkpoint["trial_id"],
            "call_id": checkpoint["call_id"],
            "ordinal": checkpoint["ordinal"],
            "model_id": checkpoint["model_id"],
            "binding_sha256": checkpoint["binding_sha256"],
            "request_sha256": checkpoint["request_sha256"],
            "outcome": outcome,
            "reserved_usd": checkpoint["reserved_usd"],
            "cost_usd": cost_usd,
            "response": None if response is None else dict(response),
            "response_sha256": None if response is None else _digest(response),
        }

    def _artifact_path(self, ordinal: int) -> Path:
        return self._artifacts_dir / f"{ordinal:06d}.json"

    def _write_artifact(
        self, ordinal: int, artifact: Mapping[str, object]
    ) -> tuple[str, str]:
        path = self._artifact_path(ordinal)
        payload = _canonical_bytes(artifact) + b"\n"
        _atomic_write(path, payload)
        return (
            path.relative_to(self._root).as_posix(),
            hashlib.sha256(_canonical_bytes(artifact)).hexdigest(),
        )

    def _load_artifact(
        self, path: Path, checkpoint: Mapping[str, object]
    ) -> dict[str, object]:
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"call artifact {path.name} is missing, unreadable, or corrupt"
            ) from exc
        expected_identity = {
            "schema_version": CALL_ARTIFACT_SCHEMA_VERSION,
            "trial_id": checkpoint["trial_id"],
            "call_id": checkpoint["call_id"],
            "ordinal": checkpoint["ordinal"],
            "model_id": checkpoint["model_id"],
            "binding_sha256": checkpoint["binding_sha256"],
            "request_sha256": checkpoint["request_sha256"],
        }
        if not isinstance(artifact, dict) or any(
            artifact.get(key) != value for key, value in expected_identity.items()
        ):
            raise ValueError(
                f"call artifact {path.name} binding does not match its paid trial"
            )
        if artifact.get("outcome") not in {"settled", STATE_AMBIGUOUS_COST}:
            raise ValueError(f"call artifact {path.name} has an invalid outcome")
        return artifact

    def _verify_artifact(self, checkpoint: Mapping[str, object]) -> dict[str, object]:
        relative = checkpoint.get("artifact_path")
        digest = checkpoint.get("artifact_sha256")
        if not isinstance(relative, str) or relative != (
            f"artifacts/{_ordinal(checkpoint):06d}.json"
        ):
            raise ValueError(
                f"call {checkpoint['call_id']} has an invalid artifact binding"
            )
        path = self._root / relative
        if not path.is_file():
            raise ValueError(f"call artifact {relative} is missing")
        artifact = self._load_artifact(path, checkpoint)
        actual = hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
        if not isinstance(digest, str) or digest != actual:
            raise ValueError(f"call artifact {relative} hash mismatch")
        if artifact.get("cost_usd") != checkpoint.get("cost_usd"):
            raise ValueError(f"call artifact {relative} cost binding mismatch")
        if artifact.get("response_sha256") != checkpoint.get("response_sha256"):
            raise ValueError(f"call artifact {relative} response binding mismatch")
        return artifact

    def _expected_cost_row(
        self,
        checkpoint: Mapping[str, object],
        *,
        outcome: str | None = None,
    ) -> dict[str, object]:
        state = str(checkpoint["state"])
        return {
            "schema_version": CALL_COST_SCHEMA_VERSION,
            "trial_id": checkpoint["trial_id"],
            "call_id": checkpoint["call_id"],
            "ordinal": checkpoint["ordinal"],
            "model_id": checkpoint["model_id"],
            "binding_sha256": checkpoint["binding_sha256"],
            "outcome": (
                outcome
                if outcome is not None
                else STATE_AMBIGUOUS_COST
                if state == STATE_AMBIGUOUS_COST
                else "settled"
            ),
            "reserved_usd": checkpoint["reserved_usd"],
            "cost_usd": checkpoint["cost_usd"],
            "artifact_path": checkpoint["artifact_path"],
            "artifact_sha256": checkpoint["artifact_sha256"],
        }

    def _settle_once(
        self, checkpoint: Mapping[str, object], *, outcome: str | None = None
    ) -> None:
        expected = self._expected_cost_row(checkpoint, outcome=outcome)
        with self._ledger_lock:
            rows = _cost_rows(self._costs_path)
            matches = [row for row in rows if row.get("call_id") == checkpoint["call_id"]]
            if len(matches) > 1:
                raise ValueError(
                    f"call {checkpoint['call_id']} appears more than once in its spend rows"
                )
            if matches:
                if matches[0] != expected:
                    raise ValueError(
                        f"call {checkpoint['call_id']} spend row identity or binding mismatch"
                    )
                return
            rows.append(expected)
            _atomic_write(
                self._costs_path,
                b"".join(_canonical_bytes(row) + b"\n" for row in rows),
            )

    def _assert_terminal_reconciliation(
        self, checkpoint: Mapping[str, object], path: Path
    ) -> None:
        self._verify_artifact(checkpoint)
        rows = _cost_rows(self._costs_path)
        matches = [row for row in rows if row.get("call_id") == checkpoint["call_id"]]
        if not matches:
            raise ValueError(f"call {checkpoint['call_id']} has no spend row")
        if len(matches) > 1:
            raise ValueError(
                f"call {checkpoint['call_id']} appears more than once in its spend rows"
            )
        if matches[0] != self._expected_cost_row(checkpoint):
            raise ValueError(
                f"call checkpoint {path.name} spend row identity or binding mismatch"
            )

    def _assert_no_orphan_evidence(
        self, checkpoints: list[dict[str, object]]
    ) -> None:
        by_call_id = {str(row["call_id"]): row for row in checkpoints}
        by_ordinal = {_ordinal(row): row for row in checkpoints}
        seen_spend: set[str] = set()
        for row in _cost_rows(self._costs_path):
            call_id = row.get("call_id")
            if not isinstance(call_id, str) or call_id not in by_call_id:
                raise ValueError(f"orphan spend row {call_id!r} has no call checkpoint")
            if call_id in seen_spend:
                raise ValueError(f"call {call_id} appears more than once in its spend rows")
            seen_spend.add(call_id)
            checkpoint = by_call_id[call_id]
            artifact_path = self._artifact_path(_ordinal(checkpoint))
            artifact = self._load_artifact(artifact_path, checkpoint)
            artifact_sha256 = hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
            if (
                row.get("schema_version") != CALL_COST_SCHEMA_VERSION
                or row.get("trial_id") != checkpoint["trial_id"]
                or row.get("ordinal") != checkpoint["ordinal"]
                or row.get("model_id") != checkpoint["model_id"]
                or row.get("binding_sha256") != checkpoint["binding_sha256"]
                or row.get("artifact_path")
                != artifact_path.relative_to(self._root).as_posix()
                or row.get("artifact_sha256") != artifact_sha256
                or row.get("outcome") != artifact.get("outcome")
                or row.get("cost_usd") != artifact.get("cost_usd")
                or row.get("reserved_usd") != artifact.get("reserved_usd")
            ):
                raise ValueError(f"call {call_id} spend row identity or binding mismatch")
        for artifact_path in sorted(self._artifacts_dir.glob("*.json")):
            try:
                ordinal = int(artifact_path.stem)
            except ValueError:
                raise ValueError(
                    f"orphan artifact {artifact_path.name} has no call checkpoint"
                ) from None
            artifact_checkpoint = by_ordinal.get(ordinal)
            if artifact_checkpoint is None or artifact_path.name != f"{ordinal:06d}.json":
                raise ValueError(
                    f"orphan artifact {artifact_path.name} has no call checkpoint"
                )
            if artifact_checkpoint["state"] == STATE_RESERVED:
                raise ValueError(
                    f"orphan artifact {artifact_path.name} precedes provider dispatch"
                )
            self._load_artifact(artifact_path, artifact_checkpoint)

    def _load(self, path: Path) -> dict[str, object]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"call checkpoint {path.name} is unreadable or corrupt") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"call checkpoint {path.name} must contain an object")
        version = raw.get("schema_version")
        if version != CALL_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported call checkpoint schema version {version!r}; supported version "
                f"is {CALL_CHECKPOINT_SCHEMA_VERSION}. Use the compatible reader or start a "
                "new trial; never coerce old paid-call state."
            )
        if raw.get("state") not in CALL_STATES:
            raise ValueError(f"call checkpoint {path.name} has an unknown state")
        trial_id = raw.get("trial_id")
        call_id = raw.get("call_id")
        ordinal = raw.get("ordinal")
        if (
            not isinstance(trial_id, str)
            or not isinstance(call_id, str)
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 0
        ):
            raise ValueError(f"call checkpoint {path.name} has invalid trial identity")
        if (
            trial_id != self._trial_id
            or call_id != f"{trial_id}:{ordinal}"
            or path.name != f"{ordinal:06d}.json"
        ):
            raise ValueError(
                f"call checkpoint {path.name} identity does not match its trial, ordinal, "
                "and artifact path"
            )
        if (
            raw.get("model_id") != self._model_id
            or raw.get("binding_sha256") != self._binding_sha256
        ):
            raise ValueError(
                f"call checkpoint {path.name} model or predeclaration binding drifted"
            )
        request_sha256 = raw.get("request_sha256")
        if not isinstance(request_sha256, str) or _DIGEST_PATTERN.fullmatch(
            request_sha256
        ) is None:
            raise ValueError(f"call checkpoint {path.name} has invalid request digest")
        state = raw["state"]
        reserved = raw.get("reserved_usd")
        if (
            isinstance(reserved, bool)
            or not isinstance(reserved, (int, float))
            or not math.isfinite(float(reserved))
            or float(reserved) < 0
        ):
            raise ValueError(f"call checkpoint {path.name} has invalid reserved cost")
        if state in {STATE_RESPONSE_PERSISTED, STATE_CONSUMED}:
            self._response(raw, path)
            cost = raw.get("cost_usd")
            if (
                isinstance(cost, bool)
                or not isinstance(cost, (int, float))
                or not math.isfinite(float(cost))
                or float(cost) < 0
            ):
                raise ValueError(f"call checkpoint {path.name} has invalid settled cost")
        elif state != STATE_AMBIGUOUS_COST and any(
            raw.get(key) is not None
            for key in ("response", "response_sha256", "cost_usd")
        ):
            raise ValueError(f"call checkpoint {path.name} has response data before settlement")
        if state in {
            STATE_RESPONSE_PERSISTED,
            STATE_CONSUMED,
            STATE_AMBIGUOUS_COST,
        }:
            relative = raw.get("artifact_path")
            digest = raw.get("artifact_sha256")
            if (
                not isinstance(relative, str)
                or not isinstance(digest, str)
                or _DIGEST_PATTERN.fullmatch(digest) is None
            ):
                raise ValueError(
                    f"call checkpoint {path.name} has an invalid artifact binding"
                )
        return raw

    def _response(self, checkpoint: Mapping[str, object], path: Path) -> ProviderResult:
        response = checkpoint.get("response")
        digest = checkpoint.get("response_sha256")
        if (
            not isinstance(response, dict)
            or not isinstance(digest, str)
            or _digest(response) != digest
        ):
            raise ValueError(f"call checkpoint {path.name} response artifact hash mismatch")
        text = response.get("text")
        input_tokens = response.get("input_tokens")
        output_tokens = response.get("output_tokens")
        if (
            not isinstance(text, str)
            or not isinstance(input_tokens, int)
            or isinstance(input_tokens, bool)
            or input_tokens < 0
            or not isinstance(output_tokens, int)
            or isinstance(output_tokens, bool)
            or output_tokens < 0
        ):
            raise ValueError(f"call checkpoint {path.name} has an invalid response artifact")
        return ProviderResult(text, input_tokens, output_tokens)

    def _commit(self, path: Path, checkpoint: Mapping[str, object]) -> None:
        payload = _canonical_bytes(checkpoint) + b"\n"
        _atomic_write(path, payload)
        if self._on_transition is not None:
            self._on_transition(str(checkpoint["call_id"]), str(checkpoint["state"]))


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Mapping[str, object] | dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _ordinal(checkpoint: Mapping[str, object]) -> int:
    value = checkpoint.get("ordinal")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("call checkpoint has an invalid ordinal")
    return value


def _cost_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("paid-call spend rows are unreadable") from exc
    rows: list[dict[str, object]] = []
    for line in lines:
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("paid-call spend rows are corrupt") from exc
        if not isinstance(row, dict):
            raise ValueError("paid-call spend row must be an object")
        rows.append(row)
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    """Expose either the prior complete file or one complete replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
