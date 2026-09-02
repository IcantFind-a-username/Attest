"""X-01: strict request/result parsing and result verification."""

from __future__ import annotations

import json
from typing import Any

import pytest

from attest.execution.protocol import (
    ProtocolError,
    decode_request,
    decode_result,
    encode_request,
    encode_result,
    request_digest,
    sha256_hex,
    verify_result,
)
from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    MAX_ARTIFACT_BYTES,
    Artifact,
    DeclaredInput,
    ExecutionRequest,
    ExecutionResultEnvelope,
    ResourceLimits,
)

NONCE = "a" * 32


def request(**overrides: Any) -> ExecutionRequest:
    fields: dict[str, Any] = {
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
        "task_id": "task-1",
        "nonce": NONCE,
        "run_id": "head-1",
        "candidate_id": "cand1",
        "revision_sha": "1" * 40,
        "profile": "local_development_best_effort",
        "interpreter": "/usr/bin/python3",
        "argv_template": ("python", "-m", "pytest", "{tree}/.attest-repro/test_repro.py"),
        "environment": (("ATTEST_OUTPUTS", "{outputs}"), ("PYTHONPATH", "{tree}")),
        "inputs": (DeclaredInput("test_repro.py", sha256_hex(b"x"), 1),),
        "limits": ResourceLimits(60.0, 30, 1024, 16_384),
        "expected_artifacts": ("junit.xml", "stdout.txt"),
    }
    fields.update(overrides)
    return ExecutionRequest(**fields)


def envelope(req: ExecutionRequest, **overrides: Any) -> ExecutionResultEnvelope:
    fields: dict[str, Any] = {
        "protocol_version": EXECUTION_PROTOCOL_VERSION,
        "nonce": req.nonce,
        "request_digest": request_digest(req),
        "run_id": req.run_id,
        "profile": req.profile,
        "backend_digest": "b" * 64,
        "exit_code": 1,
        "timed_out": False,
        "elapsed_s": 0.5,
        "artifacts": (Artifact("junit.xml", sha256_hex(b"<testsuite/>"), 12),),
        "error": "",
    }
    fields.update(overrides)
    return ExecutionResultEnvelope(**fields)


def test_request_round_trips_through_canonical_json() -> None:
    req = request()
    assert decode_request(encode_request(req)) == req
    assert request_digest(req) == sha256_hex(encode_request(req))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.pop("nonce"), "missing field nonce"),
        (lambda raw: raw.update(extra=1), "unexpected field extra"),
        (lambda raw: raw.update(protocol_version="attest.execution-protocol.v0"), "unknown"),
        (lambda raw: raw.update(nonce="zz"), "nonce"),
        (lambda raw: raw.update(run_id="../escape"), "unsafe name"),
        (lambda raw: raw.update(task_id="a/b"), "unsafe name"),
        (lambda raw: raw["inputs"][0].update(name="..\\x"), "unsafe name"),
        (lambda raw: raw["inputs"][0].update(size=MAX_ARTIFACT_BYTES + 1), "out of bounds"),
        (lambda raw: raw["inputs"][0].update(digest="0" * 63), "SHA-256"),
        (lambda raw: raw.update(environment=[["GITHUB_TOKEN", "x"]]), "credential"),
        (lambda raw: raw.update(environment=[["ANTHROPIC_API_KEY", "x"]]), "credential"),
        (lambda raw: raw.update(environment=[["lower", "x"]]), "unsafe name"),
        (lambda raw: raw.update(environment=[["B", "1"], ["A", "2"]]), "canonical"),
        (lambda raw: raw.update(argv_template=[]), "empty"),
        (lambda raw: raw.update(argv_template=["a\x00b"]), "NUL"),
        (lambda raw: raw.update(expected_artifacts=["x", "x"]), "duplicate"),
        (lambda raw: raw.update(revision_sha="HEAD"), "commit id"),
        (lambda raw: raw["limits"].update(wall_timeout_s=float("inf")), "finite"),
        (lambda raw: raw["limits"].update(output_bytes=True), "integer"),
    ],
)
def test_malformed_requests_are_rejected(mutate: Any, message: str) -> None:
    raw = json.loads(encode_request(request()))
    mutate(raw)
    with pytest.raises(ProtocolError, match=message):
        decode_request(raw)


def test_result_round_trips_and_rejects_malformed_values() -> None:
    req = request()
    env = envelope(req)
    assert decode_result(encode_result(env)) == env
    raw = json.loads(encode_result(env))
    raw["artifacts"][0]["name"] = "a/b"
    with pytest.raises(ProtocolError, match="unsafe name"):
        decode_result(raw)
    raw = json.loads(encode_result(env))
    raw["timed_out"] = "no"
    with pytest.raises(ProtocolError, match="boolean"):
        decode_result(raw)


def test_verify_result_accepts_only_a_result_that_answers_the_request() -> None:
    req = request()
    good = envelope(req)
    assert verify_result(req, good, {"junit.xml": b"<testsuite/>"}) == ()


@pytest.mark.parametrize(
    ("overrides", "artifacts", "reason"),
    [
        ({"nonce": "b" * 32}, {"junit.xml": b"<testsuite/>"}, "nonce mismatch"),
        ({"request_digest": "c" * 64}, {"junit.xml": b"<testsuite/>"}, "request digest"),
        ({"run_id": "head-2"}, {"junit.xml": b"<testsuite/>"}, "run id"),
        ({"profile": "other"}, {"junit.xml": b"<testsuite/>"}, "profile mismatch"),
        ({}, {"junit.xml": b"<testsuite>tampered</testsuite>"}, "digest mismatch"),
        ({}, {}, "missing"),
        (
            {"artifacts": (Artifact("secret.txt", sha256_hex(b"s"), 1),)},
            {"secret.txt": b"s"},
            "undeclared artifact",
        ),
        (
            {
                "artifacts": (
                    Artifact("junit.xml", sha256_hex(b"<testsuite/>"), 12),
                    Artifact("junit.xml", sha256_hex(b"<testsuite/>"), 12),
                )
            },
            {"junit.xml": b"<testsuite/>"},
            "duplicate",
        ),
        (
            {"artifacts": (Artifact("junit.xml", sha256_hex(b"x" * 10), MAX_ARTIFACT_BYTES + 1),)},
            {"junit.xml": b"x" * 10},
            "exceeds the bound",
        ),
    ],
)
def test_verify_result_names_every_forgery(
    overrides: dict[str, Any], artifacts: dict[str, bytes], reason: str
) -> None:
    req = request()
    forged = envelope(req, **overrides)
    reasons = verify_result(req, forged, artifacts)
    assert any(reason in item for item in reasons), reasons
