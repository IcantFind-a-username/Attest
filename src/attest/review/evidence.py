"""Content-addressed evidence bundles and their offline verifier (V-01).

A bundle is the complete, bounded, secret-free record of one accepted
differential certification: the task, policy, subject and receipt as
canonical JSON, the exact test bytes that ran, and one directory per run with
its command template, interpreter, environment digest, structured counts,
bounded stdout/stderr and JUnit. Every run record is content-addressed: the
receipt's ``artifact_digest`` for a run *is* the digest of that run's record,
and the record names the digests of its files. ``verify_bundle`` recomputes
every digest and binding from the files alone and then asks the pure C-01
validator, so flipping any byte anywhere in the bundle is rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from attest.certification.binding import BindingObservation
from attest.certification.types import (
    AcceptedReceipt,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    ExecutionRun,
)
from attest.certification.validate import ReceiptRejection, validate_receipt
from attest.execution.provenance import seal, verify_seal
from attest.review.executor import ExecutionOutcome, ExecutionResult, classify_failure_signature

EVIDENCE_BUNDLE_SCHEMA_VERSION = "attest.evidence-bundle.v1"
RUN_RECORD_SCHEMA_VERSION = "attest.run-record.v1"
MAX_ARTIFACT_TEXT_CHARS = 64_000


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def _bounded(text: str) -> str:
    if len(text) <= MAX_ARTIFACT_TEXT_CHARS:
        return text
    marker = "[...truncated...]\n"
    return marker + text[-(MAX_ARTIFACT_TEXT_CHARS - len(marker)) :]


def run_record(
    side: str, index: int, run: ExecutionResult, *, revision_sha: str
) -> dict[str, object]:
    """The content-addressed record of one run; its digest is the artifact digest."""
    failed = run.outcome is ExecutionOutcome.REPRODUCED
    files = {
        "stdout.txt": sha256_bytes(_bounded(run.stdout).encode("utf-8")),
        "stderr.txt": sha256_bytes(_bounded(run.stderr).encode("utf-8")),
        "junit.xml": sha256_bytes(_bounded(run.junit_xml).encode("utf-8")),
    }
    return {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "run_id": f"{side}-{index}",
        "side": side,
        "revision_sha": revision_sha,
        "outcome": "failed" if failed else "passed",
        "exit_code": run.exit_code,
        "reason": run.reason,
        "failure_class": classify_failure_signature(run).value if failed else None,
        "command_template": list(run.command_template),
        "interpreter": run.interpreter,
        "interpreter_version": run.interpreter_version,
        "environment_digest": run.environment_digest,
        "executor_profile": run.executor_profile,
        "executor_digest": run.executor_digest,
        "test_file_digest": run.test_file_digest,
        "test_node": run.test_node,
        "collected_count": run.collected_count,
        "skipped_count": run.skipped_count,
        "xfailed_count": run.xfailed_count,
        "network_blocked": run.network_blocked,
        "fresh_state": run.fresh_state,
        "files": files,
    }


def execution_run_from_record(record: dict[str, object]) -> ExecutionRun:
    failed = record["outcome"] == "failed"
    return ExecutionRun(
        run_id=str(record["run_id"]),
        revision_sha=str(record["revision_sha"]),
        outcome=str(record["outcome"]),
        artifact_digest=canonical_digest(record),
        collected_count=int(record["collected_count"]),  # type: ignore[call-overload]
        skipped_count=int(record["skipped_count"]),  # type: ignore[call-overload]
        xfailed_count=int(record["xfailed_count"]),  # type: ignore[call-overload]
        failure_signature=(
            sha256_bytes(str(record["failure_class"]).encode("utf-8")) if failed else None
        ),
    )


def receipt_body(receipt: CertificationReceipt) -> dict[str, object]:
    body = asdict(receipt)
    body["head_runs"] = [asdict(run) for run in receipt.head_runs]
    body["base_runs"] = [asdict(run) for run in receipt.base_runs]
    del body["provenance_digest"]
    return body


def provenance_digest(receipt: CertificationReceipt) -> str:
    return canonical_digest(receipt_body(receipt))


@dataclass(frozen=True)
class WrittenBundle:
    path: Path
    manifest_digest: str
    seal_key_id: str = ""  # V-03: the controller key that sealed it ("" = unsealed)


def write_bundle(
    root: Path,
    *,
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
    test_bytes: bytes,
    runs: list[tuple[str, int, ExecutionResult, str]],  # (side, index, run, revision)
    binding: BindingObservation | None = None,
    key: bytes | None = None,
) -> WrittenBundle:
    """Persist the bundle under ``root/.attest/evidence/<task>/<candidate>/``."""
    directory = root / ".attest" / "evidence" / receipt.task_id / receipt.candidate_id
    directory.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    def put(relative: str, data: bytes) -> None:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[relative] = sha256_bytes(data)

    put("task.json", canonical_bytes(asdict(task)))
    put("policy.json", canonical_bytes(asdict(policy)))
    put("subject.json", canonical_bytes(asdict(subject)))
    put("receipt.json", canonical_bytes(asdict(receipt)))
    put("test_repro.py", test_bytes)
    if binding is not None:
        put("binding.json", canonical_bytes(asdict(binding)))
    for side, index, run, revision in runs:
        record = run_record(side, index, run, revision_sha=revision)
        run_id = str(record["run_id"])
        put(f"runs/{run_id}/stdout.txt", _bounded(run.stdout).encode("utf-8"))
        put(f"runs/{run_id}/stderr.txt", _bounded(run.stderr).encode("utf-8"))
        put(f"runs/{run_id}/junit.xml", _bounded(run.junit_xml).encode("utf-8"))
        put(f"runs/{run_id}/run.json", canonical_bytes(record))
    manifest = {"schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION, "files": files}
    manifest_bytes = canonical_bytes(manifest)
    (directory / "manifest.json").write_bytes(manifest_bytes)
    manifest_digest = sha256_bytes(manifest_bytes)
    key_id = ""
    if key is not None:
        # V-03: the controller seals what it wrote; the seal sits beside the
        # manifest, outside it, and names the receipt it belongs to
        sealed = seal(manifest_digest, receipt.provenance_digest, key)
        (directory / "seal.json").write_bytes(canonical_bytes(sealed))
        key_id = str(sealed["key_id"])
    return WrittenBundle(path=directory, manifest_digest=manifest_digest, seal_key_id=key_id)


@dataclass(frozen=True)
class BundleRejection:
    reasons: tuple[str, ...]


def _load(directory: Path, relative: str) -> dict[str, Any] | None:
    try:
        value = json.loads((directory / relative).read_bytes())
    except (OSError, ValueError):
        return None
    return dict(value) if isinstance(value, dict) else None


def verify_bundle(
    directory: Path, *, key: bytes | None = None, require_seal: bool = False
) -> AcceptedReceipt | ReceiptRejection | BundleRejection:
    """Recompute every digest and binding from the files, then validate.

    No ranking input, no repository access, no subprocess: the bundle alone
    must prove the receipt. Any byte that disagrees with a recorded digest, any
    run that disagrees with its siblings, and any receipt field that disagrees
    with the recomputed evidence rejects. With the controller ``key`` the seal
    is verified too (V-03); ``require_seal`` rejects an unverified seal.
    """
    reasons: list[str] = []
    manifest = _load(directory, "manifest.json")
    if manifest is None or manifest.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        return BundleRejection(("manifest missing or unknown schema",))
    try:
        manifest_digest = sha256_bytes((directory / "manifest.json").read_bytes())
    except OSError:
        return BundleRejection(("manifest unreadable",))
    files = manifest.get("files")
    if not isinstance(files, dict):
        return BundleRejection(("manifest files missing",))
    for relative, digest in files.items():
        try:
            actual = sha256_bytes((directory / str(relative)).read_bytes())
        except OSError:
            reasons.append(f"missing file {relative}")
            continue
        if actual != digest:
            reasons.append(f"digest mismatch for {relative}")
    names = ("task", "policy", "subject", "receipt")
    loaded: dict[str, dict[str, Any] | None] = {
        name: _load(directory, f"{name}.json") for name in names
    }
    task_raw, policy_raw, subject_raw, receipt_raw = (loaded[name] for name in names)
    if task_raw is None or policy_raw is None or subject_raw is None or receipt_raw is None:
        return BundleRejection((*reasons, "task/policy/subject/receipt unreadable"))
    try:
        task = CertificationTask(**task_raw)
        policy_raw["allowed_executor_profiles"] = tuple(policy_raw["allowed_executor_profiles"])
        policy_raw["allowed_evidence_classes"] = tuple(policy_raw["allowed_evidence_classes"])
        policy = CertificationPolicy(**policy_raw)
        subject = CertificationSubject(**subject_raw)
        receipt_raw["head_runs"] = tuple(ExecutionRun(**run) for run in receipt_raw["head_runs"])
        receipt_raw["base_runs"] = tuple(ExecutionRun(**run) for run in receipt_raw["base_runs"])
        receipt = CertificationReceipt(**receipt_raw)
    except (TypeError, ValueError, KeyError) as exc:
        return BundleRejection((*reasons, f"malformed bundle value: {type(exc).__name__}"))

    try:
        test_bytes = (directory / "test_repro.py").read_bytes()
    except OSError:
        return BundleRejection((*reasons, "test bytes missing"))
    if sha256_bytes(test_bytes) != receipt.test_digest:
        reasons.append("test bytes do not match receipt.test_digest")

    records: list[dict[str, object]] = []
    for run in (*receipt.head_runs, *receipt.base_runs):
        record = _load(directory, f"runs/{run.run_id}/run.json")
        if record is None:
            reasons.append(f"run record missing for {run.run_id}")
            continue
        if canonical_digest(record) != run.artifact_digest:
            reasons.append(f"run record digest mismatch for {run.run_id}")
        recomputed = execution_run_from_record(record)
        if recomputed != run:
            reasons.append(f"run record disagrees with receipt for {run.run_id}")
        record_files = record.get("files")
        if not isinstance(record_files, dict):
            reasons.append(f"run record files missing for {run.run_id}")
        else:
            for name, digest in record_files.items():
                if files.get(f"runs/{run.run_id}/{name}") != digest:
                    reasons.append(f"run file digest mismatch for {run.run_id}/{name}")
        if record.get("test_file_digest") != receipt.test_digest:
            reasons.append(f"run {run.run_id} executed different test bytes")
        if record.get("test_node") != receipt.test_node:
            reasons.append(f"run {run.run_id} executed a different node")
        if record.get("environment_digest") != receipt.environment_digest:
            reasons.append(f"run {run.run_id} ran in a different environment")
        interpreter = f"{record.get('interpreter')}\n{record.get('interpreter_version')}"
        if sha256_bytes(interpreter.encode("utf-8")) != receipt.interpreter_digest:
            reasons.append(f"run {run.run_id} used a different interpreter")
        if record.get("executor_profile") != receipt.executor_profile:
            reasons.append(f"run {run.run_id} ran under a different executor profile")
        if record.get("executor_digest") != receipt.executor_digest:
            reasons.append(f"run {run.run_id} ran under a different executor backend")
        if record.get("fresh_state") is not True:
            reasons.append(f"run {run.run_id} did not start from fresh writable state")
        records.append(record)
    templates = {json.dumps(record.get("command_template")) for record in records}
    if len(templates) > 1:
        reasons.append("runs used different commands")
    if provenance_digest(receipt) != receipt.provenance_digest:
        reasons.append("provenance digest does not match the receipt body")
    if key is not None:
        reasons.extend(
            verify_seal(
                _load(directory, "seal.json"), manifest_digest, receipt.provenance_digest, key
            )
        )
    elif require_seal:
        reasons.append("controller seal not verified: no key supplied")
    if receipt.binding_policy_version:
        binding_raw = _load(directory, "binding.json")
        if binding_raw is None:
            reasons.append("binding observation missing")
        else:
            try:
                binding_raw["changed_lines"] = tuple(binding_raw["changed_lines"])
                binding_raw["executed_changed_lines"] = tuple(binding_raw["executed_changed_lines"])
                observation = BindingObservation(**binding_raw)
            except (TypeError, ValueError, KeyError):
                reasons.append("binding observation malformed")
            else:
                if observation.digest() != receipt.binding_digest:
                    reasons.append("binding observation does not match receipt.binding_digest")
                if observation.policy_version != receipt.binding_policy_version:
                    reasons.append("binding observation policy differs from the receipt")
    if reasons:
        return BundleRejection(tuple(reasons))
    return validate_receipt(task, policy, subject, receipt)
