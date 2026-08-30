"""Universal paid-call checkpoints are crash-safe and fail closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.checkpoints import (
    CALL_ROLE_BENCHMARK_ORACLE,
    CALL_ROLE_PRODUCT,
    STATE_AMBIGUOUS_COST,
    STATE_CONSUMED,
    STATE_DISPATCHED,
    STATE_RESERVED,
    STATE_RESPONSE_PERSISTED,
    AmbiguousCostError,
    CheckpointedProvider,
    paid_call_totals,
)
from attest.review.proposer import ProviderResult


class _Provider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise TimeoutError("outcome unknown")
        return ProviderResult("{\"findings\": []}", 100, 20)


class _Crash(RuntimeError):
    pass


def _sample(provider: CheckpointedProvider) -> ProviderResult:
    return provider.sample("system", "prompt", {"type": "object"}, 200)


def _wrapper(
    inner: _Provider,
    root: Path,
    *,
    model_id: str = "claude-sonnet-5",
    binding_sha256: str = "a" * 64,
    on_transition: Any = None,
) -> CheckpointedProvider:
    return CheckpointedProvider(
        inner,
        root=root,
        trial_id="trial-1",
        model_id=model_id,
        binding_sha256=binding_sha256,
        role=CALL_ROLE_PRODUCT,
        on_transition=on_transition,
    )


def test_completed_response_replays_without_duplicate_dispatch(tmp_path: Path) -> None:
    first = _Provider()
    response = _sample(_wrapper(first, tmp_path))

    replay = _Provider()
    again = _sample(_wrapper(replay, tmp_path))

    assert again == response
    assert first.calls == 1
    assert replay.calls == 0
    rows = list((tmp_path / "calls").glob("*.json"))
    assert len(rows) == 1
    checkpoint = json.loads(rows[0].read_text(encoding="utf-8"))
    assert checkpoint["state"] == STATE_CONSUMED
    assert checkpoint["trial_id"] == "trial-1"
    assert checkpoint["call_id"]
    assert checkpoint["response_sha256"]
    assert checkpoint["cost_usd"] > 0


def test_completed_call_reconciles_trial_spend_and_artifact_one_to_one(
    tmp_path: Path,
) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)

    records = provider.reconciliation_records()

    assert len(records) == 1
    assert records[0]["trial_id"] == "trial-1"
    assert records[0]["call_id"] == "trial-1:0"
    assert records[0]["model_id"] == "claude-sonnet-5"
    assert records[0]["binding_sha256"] == "a" * 64
    assert records[0]["role"] == CALL_ROLE_PRODUCT
    assert records[0]["outcome"] == "settled"
    assert records[0]["cost_usd"] > 0
    assert records[0]["artifact_path"] == "artifacts/000000.json"
    assert len(str(records[0]["artifact_sha256"])) == 64


def test_paid_call_roles_are_immutable_and_costs_are_disjoint(tmp_path: Path) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    _sample(provider.for_role(CALL_ROLE_BENCHMARK_ORACLE))

    records = provider.reconciliation_records()
    totals = paid_call_totals(records)

    assert [row["role"] for row in records] == [
        CALL_ROLE_PRODUCT,
        CALL_ROLE_BENCHMARK_ORACLE,
    ]
    assert totals.product_usd == pytest.approx(float(records[0]["cost_usd"]))
    assert totals.oracle_usd == pytest.approx(float(records[1]["cost_usd"]))
    assert totals.total_usd == pytest.approx(
        totals.product_usd + totals.oracle_usd
    )
    for ordinal, role in enumerate(
        (CALL_ROLE_PRODUCT, CALL_ROLE_BENCHMARK_ORACLE)
    ):
        checkpoint = json.loads(
            (tmp_path / "calls" / f"{ordinal:06d}.json").read_text(encoding="utf-8")
        )
        artifact = json.loads(
            (tmp_path / "artifacts" / f"{ordinal:06d}.json").read_text(
                encoding="utf-8"
            )
        )
        assert checkpoint["role"] == role
        assert checkpoint["request"]["role"] == role
        assert artifact["role"] == role
        assert artifact["request"]["role"] == role


def test_paid_call_role_is_not_inferred_from_call_order(tmp_path: Path) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider.for_role(CALL_ROLE_BENCHMARK_ORACLE))
    _sample(provider)

    records = provider.reconciliation_records()

    assert [row["ordinal"] for row in records] == [0, 1]
    assert [row["role"] for row in records] == [
        CALL_ROLE_BENCHMARK_ORACLE,
        CALL_ROLE_PRODUCT,
    ]


@pytest.mark.parametrize("target", ("checkpoint", "artifact", "spend"))
@pytest.mark.parametrize("role", (None, "unknown", CALL_ROLE_BENCHMARK_ORACLE))
def test_missing_unknown_or_modified_paid_call_role_fails_closed(
    tmp_path: Path, target: str, role: str | None
) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    paths = {
        "checkpoint": tmp_path / "calls" / "000000.json",
        "artifact": tmp_path / "artifacts" / "000000.json",
        "spend": tmp_path / "costs.jsonl",
    }
    path = paths[target]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if role is None:
        payload.pop("role")
    else:
        payload["role"] = role
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="role|binding|hash"):
        _wrapper(_Provider(), tmp_path)


def test_coordinated_role_rewrite_cannot_reclassify_the_original_request(
    tmp_path: Path,
) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    checkpoint_path = tmp_path / "calls" / "000000.json"
    artifact_path = tmp_path / "artifacts" / "000000.json"
    costs_path = tmp_path / "costs.jsonl"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    request_sha256 = checkpoint["request_sha256"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    cost = json.loads(costs_path.read_text(encoding="utf-8"))

    checkpoint["role"] = CALL_ROLE_BENCHMARK_ORACLE
    artifact["role"] = CALL_ROLE_BENCHMARK_ORACLE
    cost["role"] = CALL_ROLE_BENCHMARK_ORACLE
    artifact_sha256 = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    checkpoint["artifact_sha256"] = artifact_sha256
    cost["artifact_sha256"] = artifact_sha256
    checkpoint_path.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
    artifact_path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
    costs_path.write_text(json.dumps(cost) + "\n", encoding="utf-8")

    assert checkpoint["request_sha256"] == request_sha256
    with pytest.raises(ValueError, match="request|role|binding"):
        _wrapper(_Provider(), tmp_path).reconciliation_records()


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("missing_spend", "spend row"),
        ("duplicate_spend", "more than once"),
        ("trial_mismatch", "trial|identity|binding"),
        ("missing_artifact", "artifact.*missing"),
        ("artifact_binding", "artifact.*binding|hash mismatch"),
        ("orphan_spend", "orphan.*spend|no call checkpoint"),
        ("orphan_artifact", "orphan.*artifact|no call checkpoint"),
    ],
)
def test_reconciliation_corruption_fails_closed(
    tmp_path: Path, corruption: str, message: str
) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    costs_path = tmp_path / "costs.jsonl"
    artifact_path = tmp_path / "artifacts" / "000000.json"
    rows = [json.loads(line) for line in costs_path.read_text().splitlines() if line]

    if corruption == "missing_spend":
        costs_path.write_text("", encoding="utf-8")
    elif corruption == "duplicate_spend":
        costs_path.write_text(
            "\n".join(json.dumps(row) for row in [*rows, rows[0]]) + "\n",
            encoding="utf-8",
        )
    elif corruption == "trial_mismatch":
        rows[0]["trial_id"] = "another-trial"
        costs_path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    elif corruption == "missing_artifact":
        artifact_path.unlink()
    elif corruption == "artifact_binding":
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["call_id"] = "trial-1:99"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    elif corruption == "orphan_spend":
        orphan = {**rows[0], "call_id": "trial-1:99", "ordinal": 99}
        costs_path.write_text(
            "\n".join(json.dumps(row) for row in [*rows, orphan]) + "\n",
            encoding="utf-8",
        )
    else:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact.update({"call_id": "trial-1:99", "ordinal": 99})
        (artifact_path.parent / "000099.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )

    with pytest.raises(ValueError, match=message):
        _wrapper(_Provider(), tmp_path)


@pytest.mark.parametrize(
    ("crash_state", "initial_calls", "resume_calls", "terminal_state"),
    [
        (STATE_RESERVED, 0, 1, STATE_CONSUMED),
        (STATE_DISPATCHED, 0, 0, STATE_AMBIGUOUS_COST),
        (STATE_RESPONSE_PERSISTED, 1, 0, STATE_CONSUMED),
        (STATE_CONSUMED, 1, 0, STATE_CONSUMED),
    ],
)
def test_failure_after_every_transition_never_duplicates_dispatch(
    tmp_path: Path,
    crash_state: str,
    initial_calls: int,
    resume_calls: int,
    terminal_state: str,
) -> None:
    first = _Provider()

    def crash(_call_id: str, state: str) -> None:
        if state == crash_state:
            raise _Crash(state)

    with pytest.raises(_Crash, match=crash_state):
        _sample(_wrapper(first, tmp_path, on_transition=crash))
    assert first.calls == initial_calls

    resumed = _Provider()
    if terminal_state == STATE_AMBIGUOUS_COST:
        with pytest.raises(AmbiguousCostError, match="ambiguous_cost"):
            _sample(_wrapper(resumed, tmp_path))
    else:
        _sample(_wrapper(resumed, tmp_path))
    assert resumed.calls == resume_calls
    checkpoint_path = next((tmp_path / "calls").glob("*.json"))
    assert json.loads(checkpoint_path.read_text(encoding="utf-8"))["state"] == terminal_state
    spend_rows = [
        json.loads(line)
        for line in (tmp_path / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(spend_rows) == 1
    assert len(list((tmp_path / "artifacts").glob("*.json"))) == 1


def test_provider_failure_is_durable_ambiguous_cost_and_blocks_retry(tmp_path: Path) -> None:
    failed = _Provider(fail=True)
    with pytest.raises(TimeoutError, match="outcome unknown"):
        _sample(_wrapper(failed, tmp_path))

    resumed = _Provider()
    with pytest.raises(AmbiguousCostError, match="ambiguous_cost"):
        _sample(_wrapper(resumed, tmp_path))
    assert failed.calls == 1
    assert resumed.calls == 0
    checkpoint_path = next((tmp_path / "calls").glob("*.json"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["state"] == STATE_AMBIGUOUS_COST
    assert checkpoint["cost_usd"] is None
    assert checkpoint["reserved_usd"] > 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "costs.jsonl").read_text().splitlines()
        if line
    ]
    assert len(rows) == 1
    assert rows[0]["trial_id"] == "trial-1"
    assert rows[0]["call_id"] == "trial-1:0"
    assert rows[0]["outcome"] == STATE_AMBIGUOUS_COST
    assert rows[0]["cost_usd"] is None


def test_old_checkpoint_schema_fails_with_actionable_version_message(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    calls.mkdir()
    (calls / "old.json").write_text(
        json.dumps(
            {
                "schema_version": "0",
                "trial_id": "trial-1",
                "call_id": "old",
                "request_sha256": "a" * 64,
                "state": STATE_DISPATCHED,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported.*schema version.*0.*supported.*5"):
        _wrapper(_Provider(), tmp_path)


@pytest.mark.parametrize("target", ("artifact", "spend"))
def test_old_paid_evidence_schema_fails_with_actionable_version_message(
    tmp_path: Path, target: str
) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    path = (
        tmp_path / "artifacts" / "000000.json"
        if target == "artifact"
        else tmp_path / "costs.jsonl"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "3"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported.*schema version.*3.*supported.*4"):
        _wrapper(_Provider(), tmp_path)


@pytest.mark.parametrize(
    "changed",
    ("model", "binding"),
)
def test_terminal_call_rejects_model_or_predeclaration_drift(
    tmp_path: Path, changed: str
) -> None:
    _sample(_wrapper(_Provider(), tmp_path))
    resumed = _Provider()

    with pytest.raises(ValueError, match="model|predeclaration|binding"):
        _wrapper(
            resumed,
            tmp_path,
            model_id=("claude-opus-5" if changed == "model" else "claude-sonnet-5"),
            binding_sha256=("b" * 64 if changed == "binding" else "a" * 64),
        )

    assert resumed.calls == 0


def test_call_identity_must_match_trial_ordinal_and_artifact_path(tmp_path: Path) -> None:
    provider = _wrapper(_Provider(), tmp_path)
    _sample(provider)
    _sample(provider)
    second = tmp_path / "calls" / "000001.json"
    checkpoint = json.loads(second.read_text(encoding="utf-8"))
    checkpoint["call_id"] = "trial-1:0"
    second.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(ValueError, match="identity does not match"):
        _wrapper(_Provider(), tmp_path)
