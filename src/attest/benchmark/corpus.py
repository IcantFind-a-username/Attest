"""Metadata-only BugsInPy import and isolated corpus validation."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shlex
import signal
import socket
import subprocess
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from attest.benchmark.schema import (
    BenchmarkCase,
    RuntimeDescriptor,
    load_manifest,
    normalize_unified_diff_bytes,
    verify_descriptor_bytes,
)

_MAX_CHANGED_LINES = 400
_INFO_LINE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"\s*$')
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")
_COPYRIGHT_LINE = re.compile(
    r"^copyright(?:\s+(?:\(c\)|©))?\s+"
    r"\d{4}(?:\s*[-–]\s*\d{2,4})?(?:\s*,\s*\d{4}(?:\s*[-–]\s*\d{2,4})?)*"
    r"\s*,?\s+[\w][\w .&,()'/-]{0,199}$",
    re.IGNORECASE,
)
_BSD3_HOLDER_NAME = re.compile(
    r"(?<=Neither the name of )[\w][\w &,()'/-]{0,199}"
    r"(?= nor the names of its contributors may be used)"
)
_LICENSE_BODY_STARTS = {
    "MIT": "Permission is hereby granted, free of charge",
    "BSD-2-Clause": "Redistribution and use in source and binary forms",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}
_LICENSE_BODY_SHA256 = {
    # SHA-256 of whitespace-normalized standard SPDX template bodies after list-marker
    # normalization. Full-body fingerprints make inserted, reordered, or appended terms
    # fail closed without trying to enumerate every unsupported license family.
    "MIT": "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5",
    "BSD-2-Clause": "4f61a7bc7704d3ecdd43d1b61e887d81a5e0468581a08a1a3beac62e0156da13",
    "BSD-3-Clause": "667a5ea561e27c5843aedc905ba64e45471dda8240aa1ca7a09e513363cba5ac",
}
_LICENSE_HEADERS = {
    "MIT": frozenset(
        {
            "mit license",
            "the mit license (mit)",
            "released under the mit licence.",
        }
    ),
    "BSD-2-Clause": frozenset({"bsd 2-clause license"}),
    "BSD-3-Clause": frozenset({"bsd 3-clause license"}),
}


@dataclass(frozen=True)
class RunOutcome:
    """Bounded result of one isolated corpus test command."""

    returncode: int
    output: bytes
    timed_out: bool


@dataclass(frozen=True)
class ValidationReceipt:
    """Manifest-bound allowlist of pairs that passed the differential oracle."""

    schema_version: str
    manifest_sha256: str
    validated_pair_ids: tuple[str, ...]
    validation_results_sha256: str


@dataclass(frozen=True)
class IsolationAdapter:
    """Immutable command wrapper claiming one verifiable isolation capability."""

    capability: str
    wrapper_argv: tuple[str, ...]
    wrapper_sha256: str


class IsolationError(ValueError):
    """The execution boundary could not prove network denial."""


class CorpusRunner(Protocol):
    """Execution boundary for generic prepared-corpus validation."""

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
        """Run one test command without a shell."""


class SubprocessCorpusRunner:
    """Run argv-only tests with caller-selected interpreters and bounded resources."""

    def __init__(
        self,
        interpreters: Mapping[str, tuple[str, ...]],
        *,
        allowed_tools: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
        isolation: IsolationAdapter | None = None,
        timeout_s: float = 60,
        max_output_bytes: int = 65_536,
    ) -> None:
        if timeout_s <= 0 or max_output_bytes <= 0:
            raise ValueError("runner limits must be positive")
        self._interpreters = dict(interpreters)
        self._allowed_tools = dict(allowed_tools or {})
        self._isolation = isolation
        self._isolation_verified = False
        self._timeout_s = timeout_s
        self._max_output_bytes = max_output_bytes

    @property
    def isolation_verified(self) -> bool:
        """Return whether this runner passed its owned-boundary socket probe."""
        if not self._isolation_verified:
            return False
        try:
            self._validated_adapter()
        except IsolationError:
            return False
        return True

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
        interpreter = self._interpreters.get(source_id)
        if interpreter is None:
            raise ValueError(f"no interpreter configured for {source_id}")
        self._verify_isolation(interpreter, cwd)
        prefix = (
            interpreter
            if tool == "python"
            else self._allowed_tools.get((source_id, tool))
        )
        if prefix is None:
            raise ValueError(f"tool is not allowed: {tool}")
        _require_explicit_executable(prefix, tool)
        isolation = self._validated_adapter()
        command = (*isolation.wrapper_argv, *prefix, *args)
        return self._execute(command, cwd, self._timeout_s)

    def _verify_isolation(self, interpreter: tuple[str, ...], cwd: Path) -> None:
        if self._isolation_verified:
            self._validated_adapter()
            return
        isolation = self._validated_adapter()
        _require_explicit_executable(interpreter, "python")
        probe = (
            "import socket,sys; s=socket.socket(); "
            "code=s.connect_ex(('127.0.0.1',int(sys.argv[1]))); "
            "raise SystemExit(73 if code == 0 else 0)"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            command = (
                *isolation.wrapper_argv,
                *interpreter,
                "-c",
                probe,
                str(port),
            )
            outcome = self._execute(command, cwd, min(self._timeout_s, 5.0))
        if outcome.timed_out or outcome.returncode != 0:
            raise IsolationError("network isolation socket probe was not denied")
        self._isolation_verified = True

    def _validated_adapter(self) -> IsolationAdapter:
        isolation = self._isolation
        if isolation is None or isolation.capability != "attest.network-deny.v1":
            raise IsolationError("a verified network isolation capability is required")
        try:
            _require_explicit_executable(isolation.wrapper_argv, "isolation wrapper")
        except ValueError as exc:
            raise IsolationError(str(exc)) from exc
        wrapper = Path(isolation.wrapper_argv[0])
        if (
            re.fullmatch(r"[0-9a-f]{64}", isolation.wrapper_sha256) is None
            or hashlib.sha256(wrapper.read_bytes()).hexdigest()
            != isolation.wrapper_sha256
        ):
            raise IsolationError("isolation wrapper digest does not match")
        return isolation

    def _execute(self, command: tuple[str, ...], cwd: Path, timeout_s: float) -> RunOutcome:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
        }
        environment.update(
            {
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_ADDOPTS": "-p no:cacheprovider",
            }
        )
        start_new_session = os.name == "posix"
        creationflags = (
            int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            if os.name == "nt"
            else 0
        )
        process: subprocess.Popen[bytes] = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        stdout = process.stdout
        assert stdout is not None
        tail = bytearray()

        def drain() -> None:
            while chunk := stdout.read(65_536):
                tail.extend(chunk)
                excess = len(tail) - self._max_output_bytes
                if excess > 0:
                    del tail[:excess]

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout_s
        timed_out = False
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
            reader.join(timeout=max(0.0, deadline - time.monotonic()))
            if reader.is_alive():
                raise subprocess.TimeoutExpired(list(command), timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_owned_process_tree(process)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:  # pragma: no cover - OS-level failure
                process.kill()
                process.wait()
            reader.join(timeout=1)
        finally:
            stdout.close()
        return RunOutcome(process.returncode, bytes(tail), timed_out)


def _require_explicit_executable(prefix: tuple[str, ...], tool: str) -> None:
    if not prefix:
        raise ValueError(f"empty executable mapping for {tool}")
    executable = Path(prefix[0])
    if not executable.is_absolute() or not executable.is_file() or not os.access(
        executable, os.X_OK
    ):
        raise ValueError(f"executable mapping for {tool} must use an absolute executable")


def _kill_owned_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill only the process group/session created for this invocation."""
    if os.name == "posix":
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif os.name == "nt":  # pragma: no cover - exercised on Windows
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif process.poll() is None:  # pragma: no cover - exotic platforms
        process.kill()


def validate_corpus(manifest: Path, root: Path, runner: CorpusRunner) -> dict[str, Any]:
    """Validate generic prepared pairs with a repeated differential-test oracle."""
    typed = load_manifest(manifest)
    runtimes = {runtime.case_id: runtime for runtime in typed.runtime}
    if set(runtimes) != {case.case_id for case in typed.cases}:
        raise ValueError("runtime rows must exactly cover manifest cases")

    by_pair: dict[str, list[Any]] = {}
    for case in typed.cases:
        by_pair.setdefault(case.pair_id, []).append(case)
    results: list[dict[str, Any]] = []
    command_success = True
    for pair_id in sorted(by_pair):
        members = by_pair[pair_id]
        replay = next(case for case in members if case.role == "historical_bug_replay")
        control = next(case for case in members if case.role == "developer_fix_control")
        try:
            _verify_pair_integrity(root, replay, control, runtimes)
            fixed_runs = _run_three(control, runtimes[control.case_id], root, runner)
            fixed_reason = _fixed_failure_reason(fixed_runs)
            if fixed_reason:
                results.append({"pair_id": pair_id, "status": "excluded", "reason": fixed_reason})
                continue
            buggy_runs = _run_three(replay, runtimes[replay.case_id], root, runner)
            buggy_reason, signature = _buggy_failure_reason(buggy_runs)
            if buggy_reason:
                results.append({"pair_id": pair_id, "status": "excluded", "reason": buggy_reason})
                continue
            results.append(
                {
                    "pair_id": pair_id,
                    "status": "validated",
                    "failure_signature": signature,
                    "fixed_runs": [_run_json(outcome) for outcome in fixed_runs],
                    "buggy_runs": [_run_json(outcome) for outcome in buggy_runs],
                }
            )
        except IsolationError:
            command_success = False
            results.append(
                {"pair_id": pair_id, "status": "excluded", "reason": "isolation_unverified"}
            )
        except _IntegrityError as exc:
            results.append({"pair_id": pair_id, "status": "excluded", "reason": exc.reason})
        except (OSError, subprocess.CalledProcessError, ValueError):
            results.append(
                {"pair_id": pair_id, "status": "excluded", "reason": "integrity_failure"}
            )
    validated_pair_ids = sorted(
        result["pair_id"] for result in results if result["status"] == "validated"
    )
    validated = len(validated_pair_ids)
    total = len(results)
    corpus_valid = total > 0 and validated == total
    validation_status = (
        "empty"
        if total == 0
        else "valid"
        if corpus_valid
        else "partial"
        if validated
        else "invalid"
    )
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    validation_results = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "results": results,
    }
    validation_results_bytes = _canonical_json_bytes(validation_results)
    isolation_verified = (
        isinstance(runner, SubprocessCorpusRunner) and runner.isolation_verified
    )
    receipt = (
        _validation_receipt(
            manifest_sha256, validation_results_bytes, validated_pair_ids
        )
        if validated_pair_ids and command_success and isolation_verified
        else None
    )
    return {
        "manifest": manifest.name,
        "manifest_sha256": manifest_sha256,
        "command_success": command_success,
        "corpus_valid": corpus_valid,
        "validation_status": validation_status,
        "scorable": validated > 0 and command_success and isolation_verified,
        "validated_pairs": validated,
        "excluded_pairs": total - validated,
        "results": results,
        "validation_results": validation_results,
        "receipt": receipt,
    }


def _validation_receipt(
    manifest_sha256: str,
    validation_results_bytes: bytes,
    validated_pair_ids: list[str],
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "validated_pair_ids": validated_pair_ids,
        "validation_results_sha256": hashlib.sha256(validation_results_bytes).hexdigest(),
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def load_validation_receipt(
    path: Path, manifest: Path, validation_results: Path
) -> ValidationReceipt:
    """Derive the allowlist from exact manifest-bound validation-results bytes."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("validation receipt must be valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "manifest_sha256",
        "validated_pair_ids",
        "validation_results_sha256",
    }:
        raise ValueError("validation receipt has invalid fields")
    schema_version = value["schema_version"]
    manifest_sha256 = value["manifest_sha256"]
    result_sha256 = value["validation_results_sha256"]
    pair_ids = value["validated_pair_ids"]
    if schema_version != "1":
        raise ValueError("unsupported validation receipt schema")
    if not isinstance(manifest_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", manifest_sha256
    ) is None:
        raise ValueError("validation receipt manifest digest is invalid")
    if manifest_sha256 != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("validation receipt manifest digest does not match")
    if not isinstance(result_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", result_sha256
    ) is None:
        raise ValueError("validation receipt results digest is invalid")
    try:
        results_bytes = validation_results.read_bytes()
        results_value = json.loads(results_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("validation results must be valid JSON") from exc
    if result_sha256 != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("validation results digest does not match receipt")
    if results_bytes != _canonical_json_bytes(results_value):
        raise ValueError("validation results must use canonical JSON encoding")
    if not isinstance(results_value, dict) or set(results_value) != {
        "schema_version",
        "manifest_sha256",
        "results",
    }:
        raise ValueError("validation results have invalid fields")
    if (
        results_value["schema_version"] != "1"
        or results_value["manifest_sha256"] != manifest_sha256
    ):
        raise ValueError("validation results manifest digest does not match")
    result_rows = results_value["results"]
    if not isinstance(result_rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("pair_id"), str)
        or row.get("status") not in {"validated", "excluded"}
        for row in result_rows
    ):
        raise ValueError("validation results rows are invalid")
    result_pair_ids = [row["pair_id"] for row in result_rows]
    manifest_pair_ids = {case.pair_id for case in load_manifest(manifest).cases}
    if len(result_pair_ids) != len(set(result_pair_ids)) or set(result_pair_ids) != (
        manifest_pair_ids
    ):
        raise ValueError("validation results must exactly cover manifest pairs")
    derived_pair_ids = sorted(
        row["pair_id"] for row in result_rows if row["status"] == "validated"
    )
    if (
        not isinstance(pair_ids, list)
        or any(
            not isinstance(pair_id, str)
            or re.fullmatch(r"pair-[0-9a-f]{12}", pair_id) is None
            for pair_id in pair_ids
        )
        or pair_ids != sorted(set(pair_ids))
    ):
        raise ValueError("validation receipt pair ids are invalid")
    if pair_ids != derived_pair_ids:
        raise ValueError("validation receipt validated pair allowlist does not match results")
    if not derived_pair_ids:
        raise ValueError("validation receipt must contain a validated pair")
    return ValidationReceipt(
        schema_version=schema_version,
        manifest_sha256=manifest_sha256,
        validated_pair_ids=tuple(derived_pair_ids),
        validation_results_sha256=result_sha256,
    )


def require_validated_pair(receipt: ValidationReceipt, pair_id: str) -> None:
    """Fail closed unless a downstream evaluator selects a receipted pair."""
    if pair_id not in receipt.validated_pair_ids:
        raise ValueError(f"pair {pair_id} is not in validation receipt")


def _verify_pair_integrity(
    root: Path,
    replay: BenchmarkCase,
    control: BenchmarkCase,
    runtimes: Mapping[str, RuntimeDescriptor],
) -> None:
    patch_path = _contained_file(root, replay.patch.relative_path)
    test_path = _contained_file(root, replay.tests.relative_path)
    if not verify_descriptor_bytes(replay.patch, patch_path.read_bytes()):
        raise _IntegrityError("descriptor_hash_mismatch")
    if not verify_descriptor_bytes(replay.tests, test_path.read_bytes()):
        raise _IntegrityError("descriptor_hash_mismatch")
    if (runtimes[replay.case_id].tool, runtimes[replay.case_id].args) != (
        runtimes[control.case_id].tool,
        runtimes[control.case_id].args,
    ):
        raise _IntegrityError("test_command_mismatch")
    try:
        test_command = _command_from_test_descriptor(test_path.read_bytes())
    except _Excluded as exc:
        raise _IntegrityError("test_command_mismatch") from exc
    if test_command != {
        "tool": runtimes[replay.case_id].tool,
        "args": list(runtimes[replay.case_id].args),
    }:
        raise _IntegrityError("test_command_mismatch")
    for case, commit in ((replay, replay.buggy_commit), (control, control.fixed_commit)):
        cwd = _runtime_cwd(root, runtimes[case.case_id])
        if Path(_git(cwd, "rev-parse", "--show-toplevel")).resolve() != cwd:
            raise _IntegrityError("checkout_root_mismatch")
        if _git(cwd, "rev-parse", "HEAD") != commit:
            raise _IntegrityError("checkout_commit_mismatch")
        if _git(cwd, "status", "--porcelain"):
            raise _IntegrityError("dirty_checkout")
    patch_bytes = patch_path.read_bytes()
    diff_paths = _unified_diff_paths(patch_bytes)
    actual_patch = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-color",
            replay.buggy_commit,
            replay.fixed_commit,
            "--",
            *diff_paths,
        ],
        cwd=_runtime_cwd(root, runtimes[replay.case_id]),
        check=True,
        capture_output=True,
    ).stdout
    if normalize_unified_diff_bytes(actual_patch) != normalize_unified_diff_bytes(
        patch_bytes
    ):
        raise _IntegrityError("patch_mismatch")


def _run_three(
    case: BenchmarkCase,
    runtime: RuntimeDescriptor,
    root: Path,
    runner: CorpusRunner,
) -> list[RunOutcome]:
    cwd = _runtime_cwd(root, runtime)
    outcomes: list[RunOutcome] = []
    for _ in range(3):
        outcome = runner.run(case.source_id, runtime.tool, runtime.args, cwd)
        outcomes.append(outcome)
        if outcome.timed_out:
            break
        if case.role == "developer_fix_control" and outcome.returncode != 0:
            break
    return outcomes


def _fixed_failure_reason(outcomes: list[RunOutcome]) -> str | None:
    if any(outcome.timed_out for outcome in outcomes):
        return "timeout"
    if len(outcomes) != 3 or any(outcome.returncode != 0 for outcome in outcomes):
        return "dependency_or_setup_failure"
    return None


def _buggy_failure_reason(outcomes: list[RunOutcome]) -> tuple[str | None, str]:
    if any(outcome.timed_out for outcome in outcomes):
        return "timeout", ""
    if len(outcomes) != 3 or any(outcome.returncode == 0 for outcome in outcomes):
        return "flaky", ""
    signatures = [_failure_signature(outcome.output) for outcome in outcomes]
    if any(signature is None for signature in signatures):
        return "dependency_or_setup_failure", ""
    if len(set(signatures)) != 1:
        return "inconsistent_failure_signature", ""
    return None, signatures[0] or ""


def _failure_signature(output: bytes) -> str | None:
    text = output.decode("utf-8", errors="replace")
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "modulenotfounderror",
            "importerror while importing",
            "not found:",
            "collected 0",
        )
    ):
        return None
    lines = [
        " ".join(line.split())
        for line in text.splitlines()
        if line.lstrip().startswith(("FAILED ", "ERROR "))
    ]
    if not lines:
        return None
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _run_json(outcome: RunOutcome) -> dict[str, object]:
    return {
        "returncode": outcome.returncode,
        "timed_out": outcome.timed_out,
        "output_sha256": hashlib.sha256(outcome.output).hexdigest(),
    }


def _runtime_cwd(root: Path, runtime: RuntimeDescriptor) -> Path:
    path = root / runtime.cwd
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("runtime cwd escapes corpus root") from exc
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError("runtime cwd must be a real directory")
    return resolved


class _IntegrityError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _command_from_test_descriptor(contents: bytes) -> dict[str, object]:
    try:
        text = contents.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise _Excluded("missing_regression_test") from exc
    commands = [line.strip() for line in text.splitlines() if line.strip()]
    if len(commands) != 1 or any(
        token in commands[0] for token in ("&&", "||", ";", "`", "$(")
    ):
        raise _Excluded("missing_regression_test")
    try:
        argv = shlex.split(commands[0])
    except ValueError as exc:
        raise _Excluded("missing_regression_test") from exc
    if not argv:
        raise _Excluded("missing_regression_test")
    return _typed_command(argv)


def _contained_file(root: Path, relative_path: str) -> Path:
    path = root / relative_path
    if path.is_symlink():
        raise ValueError("artifact symlinks are forbidden")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("artifact path escapes corpus root") from exc
    if not resolved.is_file():
        raise ValueError("artifact must be a file")
    return resolved


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def import_bugsinpy(
    source: Path,
    output: Path,
    limit: int,
    seed: int,
    *,
    project_cache: Path | None = None,
) -> dict[str, Any]:
    """Import deterministic, hash-addressed metadata from a pinned local BugsInPy tree."""
    source = source.resolve()
    project_cache = (project_cache or source.parent / "project-cache").resolve()
    if limit < 0:
        raise ValueError("limit must be non-negative")
    corpus_commit, corpus_url = _pinned_repository(source)
    corpus_license = _license_evidence(source, source / "LICENSE")
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    bug_dirs = sorted(
        source.glob("projects/*/bugs/*"),
        key=lambda path: (path.parts[-3].casefold(), _natural_bug_key(path.name)),
    )
    for bug_dir in bug_dirs:
        upstream_case = f"{bug_dir.parts[-3]}/{bug_dir.name}"
        try:
            candidates.append(
                _import_candidate(source, bug_dir, corpus_commit, project_cache)
            )
        except _Excluded as exc:
            exclusions.append({"upstream_case": upstream_case, "reason": exc.reason})

    candidates.sort(key=lambda item: item["upstream_case"])
    chooser = random.Random(seed)
    chooser.shuffle(candidates)
    selected = candidates[:limit]
    selected.sort(key=lambda item: item["pair_id"])

    cases: list[dict[str, Any]] = []
    truths: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []
    sources_by_id: dict[str, dict[str, Any]] = {}
    for candidate in selected:
        source_entry = candidate["source"]
        source_id = source_entry["source_id"]
        existing_source = sources_by_id.get(source_id)
        if existing_source is None:
            sources_by_id[source_id] = dict(source_entry)
        else:
            existing_commits = existing_source["license_commits_verified"]
            new_commits = source_entry["license_commits_verified"]
            assert isinstance(existing_commits, list) and isinstance(new_commits, list)
            existing_source["license_commits_verified"] = sorted(
                set(existing_commits) | set(new_commits)
            )
        base = candidate["case"]
        replay_id = _opaque("case", candidate["pair_id"] + ":replay")
        control_id = _opaque("case", candidate["pair_id"] + ":control")
        for case_id, role in (
            (replay_id, "historical_bug_replay"),
            (control_id, "developer_fix_control"),
        ):
            case = dict(base)
            case.update({"case_id": case_id, "role": role})
            cases.append(case)
            runtimes.append(
                {
                    "case_id": case_id,
                    "role": role,
                    "cwd": (
                        f"{base['source_id']}/{base['pair_id']}/replay"
                        if role == "historical_bug_replay"
                        else f"{base['source_id']}/{base['pair_id']}/control"
                    ),
                    "command": candidate["command"],
                    "python_version": candidate["python_version"],
                }
            )
        old_locations = [
            location for location in base["changed_locations"] if location["side"] == "old"
        ]
        for index, location in enumerate(old_locations, start=1):
            truths.append(
                {
                    "defect_id": f"truth_{candidate['pair_id'][5:]}_{index}",
                    "case_id": replay_id,
                    "file": location["path"],
                    "start_line": location["start_line"],
                    "end_line": location["end_line"],
                }
            )

    document: dict[str, Any] = {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": corpus_commit,
        "provenance": {
            "kind": "BugsInPy",
            "source_url": corpus_url,
            "license_status": "DETECTED" if corpus_license else "UNSPECIFIED",
            "license": corpus_license[0] if corpus_license else None,
            "license_file": "LICENSE" if corpus_license else None,
            "license_sha256": corpus_license[1] if corpus_license else None,
        },
        "selection": {
            "seed": seed,
            "requested_pair_limit": limit,
            "eligible_pairs": len(candidates),
            "selected_pairs": len(selected),
        },
        "sources": [sources_by_id[key] for key in sorted(sources_by_id)],
        "cases": sorted(cases, key=lambda case: case["case_id"]),
        "truth_defects": sorted(truths, key=lambda truth: truth["defect_id"]),
        "runtime": sorted(runtimes, key=lambda runtime: runtime["case_id"]),
        "exclusions": exclusions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return document


class _Excluded(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _pinned_repository(source: Path) -> tuple[str, str]:
    if not source.is_dir():
        raise ValueError("source must be an existing local git repository")
    try:
        commit = _git(source, "rev-parse", "HEAD")
        top = Path(_git(source, "rev-parse", "--show-toplevel")).resolve()
        status = _git(source, "status", "--porcelain")
        url = _git(source, "remote", "get-url", "origin")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("source must be an existing local git repository") from exc
    if top != source:
        raise ValueError("source must be the git repository root")
    if status:
        raise ValueError("source git repository must be clean")
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        raise ValueError("source commit must be a full hexadecimal object id")
    return commit, url


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _import_candidate(
    source: Path, bug_dir: Path, corpus_commit: str, project_cache: Path
) -> dict[str, Any]:
    project_dir = bug_dir.parents[1]
    project = project_dir.name
    upstream_case = f"{project}/{bug_dir.name}"
    project_info = _read_info(_safe_file(source, project_dir / "project.info"))
    project_url = project_info.get("github_url")
    if not project_url:
        raise _Excluded("missing_source_url")

    info = _read_info(_safe_file(source, bug_dir / "bug.info"))
    buggy_commit = _full_commit(info.get("buggy_commit_id"), "buggy_commit")
    fixed_commit = _full_commit(info.get("fixed_commit_id"), "fixed_commit")
    if buggy_commit == fixed_commit:
        raise _Excluded("identical_commits")
    if not info.get("test_file"):
        raise _Excluded("missing_regression_test")
    license_evidence = _project_license_evidence(
        project_cache / project, project_url, buggy_commit, fixed_commit
    )
    if license_evidence is None:
        raise _Excluded("source_license_missing")
    declared_license, license_name, license_sha256 = license_evidence

    patch_path = _safe_file(source, bug_dir / "bug_patch.txt")
    run_test = _safe_file(source, bug_dir / "run_test.sh")
    _safe_file(source, bug_dir / "bug_buggy.txt")
    _safe_file(source, bug_dir / "bug_fixed.txt")
    patch_bytes = patch_path.read_bytes()
    if b"\x00" in patch_bytes:
        raise _Excluded("binary_patch")
    try:
        patch_text = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _Excluded("binary_patch") from exc
    locations = _changed_locations(patch_text)
    project_checkout = project_cache / project
    if not _project_patch_matches(project_checkout, buggy_commit, fixed_commit, patch_bytes):
        raise _Excluded("patch_mismatch")
    test_bytes = run_test.read_bytes()
    try:
        command_text = test_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise _Excluded("missing_regression_test") from exc
    commands = [line.strip() for line in command_text.splitlines() if line.strip()]
    if len(commands) != 1:
        raise _Excluded("missing_regression_test")
    try:
        test_argv = shlex.split(commands[0])
    except ValueError as exc:
        raise _Excluded("missing_regression_test") from exc
    if not test_argv or any(token in commands[0] for token in ("&&", "||", ";", "`", "$(`")):
        raise _Excluded("missing_regression_test")
    command = _typed_command(test_argv)

    pair_id = _opaque("pair", f"{corpus_commit}:{upstream_case}")
    source_id = _opaque("source", f"{corpus_commit}:{project_url}")
    relative_patch = patch_path.relative_to(source).as_posix()
    relative_test = run_test.relative_to(source).as_posix()
    source_entry = {
        "source_id": source_id,
        "project_url": project_url,
        "source_license": declared_license,
        "license_file": license_name,
        "license_sha256": license_sha256,
        "license_commits_verified": [buggy_commit, fixed_commit],
    }
    return {
        "upstream_case": upstream_case,
        "pair_id": pair_id,
        "source": source_entry,
        "python_version": info.get("python_version", "unknown"),
        "command": command,
        "case": {
            "pair_id": pair_id,
            "source_id": source_id,
            "provenance_kind": "historical_fix",
            "source_license": declared_license,
            "buggy_commit": buggy_commit,
            "fixed_commit": fixed_commit,
            "patch": {
                "relative_path": relative_patch,
                "sha256": hashlib.sha256(normalize_unified_diff_bytes(patch_bytes)).hexdigest(),
                "normalization": "unified_diff",
            },
            "tests": {
                "relative_path": relative_test,
                "sha256": hashlib.sha256(command_text.encode()).hexdigest(),
                "normalization": "normalized_text",
            },
            "changed_locations": locations,
            "split": "test",
        },
    }


def _safe_file(root: Path, path: Path) -> Path:
    if path.is_symlink():
        raise _Excluded("unsafe_symlink")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        if path.name == "run_test.sh":
            raise _Excluded("missing_regression_test") from exc
        raise _Excluded("missing_metadata") from exc
    if not resolved.is_file():
        raise _Excluded("missing_metadata")
    return resolved


def _license_evidence(root: Path, path: Path) -> tuple[str, str] | None:
    try:
        evidence_path = _safe_file(root, path)
        contents = evidence_path.read_bytes()
    except (_Excluded, OSError):
        return None
    identifier = _classify_license(contents)
    if identifier is None:
        return None
    return identifier, hashlib.sha256(contents).hexdigest()


def _project_license_evidence(
    checkout: Path, project_url: str, buggy_commit: str, fixed_commit: str
) -> tuple[str, str, str] | None:
    if not checkout.is_dir():
        return None
    try:
        top = Path(_git(checkout, "rev-parse", "--show-toplevel")).resolve()
        remote = _git(checkout, "remote", "get-url", "origin")
        if top != checkout.resolve() or _normalized_git_url(remote) != _normalized_git_url(
            project_url
        ):
            return None
        for commit in (buggy_commit, fixed_commit):
            _git(checkout, "cat-file", "-e", f"{commit}^{{commit}}")
        paths = set(_git(checkout, "ls-tree", "-r", "--name-only", buggy_commit).splitlines())
        paths &= set(_git(checkout, "ls-tree", "-r", "--name-only", fixed_commit).splitlines())
    except (OSError, subprocess.CalledProcessError):
        return None
    allowed_names = {
        "license",
        "license.txt",
        "license.md",
        "licence",
        "licence.txt",
        "licence.md",
        "copying",
        "copying.txt",
        "copying.md",
    }
    for path in sorted(paths, key=lambda value: (len(Path(value).parts), value.casefold())):
        if Path(path).name.casefold() not in allowed_names:
            continue
        try:
            buggy_bytes = subprocess.run(
                ["git", "show", f"{buggy_commit}:{path}"],
                cwd=checkout,
                check=True,
                capture_output=True,
            ).stdout
            fixed_bytes = subprocess.run(
                ["git", "show", f"{fixed_commit}:{path}"],
                cwd=checkout,
                check=True,
                capture_output=True,
            ).stdout
            buggy_license = _classify_license(buggy_bytes)
            fixed_license = _classify_license(fixed_bytes)
        except (OSError, subprocess.CalledProcessError):
            continue
        if buggy_license is not None and buggy_license == fixed_license:
            return fixed_license, path, hashlib.sha256(fixed_bytes).hexdigest()
    return None


def _normalized_git_url(value: str) -> str:
    return value.removesuffix("/").removesuffix(".git")


def _classify_license(contents: bytes) -> str | None:
    try:
        text = contents.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines()
    matches: set[str] = set()
    for identifier, body_start in _LICENSE_BODY_STARTS.items():
        for index, line in enumerate(lines):
            if not line.strip().startswith(body_start):
                continue
            if not _allowed_license_prefix(lines[:index], identifier):
                continue
            normalized_body = _normalize_license_body(lines[index:])
            digest = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
            if digest == _LICENSE_BODY_SHA256[identifier]:
                matches.add(identifier)
    return next(iter(matches)) if len(matches) == 1 else None


def _allowed_license_prefix(lines: list[str], identifier: str) -> bool:
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.casefold() in _LICENSE_HEADERS[identifier] and not header_seen:
            header_seen = True
            continue
        if _COPYRIGHT_LINE.fullmatch(stripped):
            continue
        if identifier.startswith("BSD-") and stripped.casefold() == "all rights reserved.":
            continue
        return False
    return True


def _normalize_license_body(lines: list[str]) -> str:
    without_list_markers = [
        re.sub(r"^\s*(?:\*|[123][.)])\s+", "", line) for line in lines
    ]
    normalized = " ".join(" ".join(without_list_markers).split())
    return _BSD3_HOLDER_NAME.sub("the copyright holder", normalized)


def _read_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _INFO_LINE.fullmatch(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _full_commit(value: str | None, label: str) -> str:
    if value is None or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise _Excluded(f"invalid_{label}")
    return value


def _changed_locations(patch: str) -> list[dict[str, object]]:
    locations, changed_lines = parse_unified_diff(patch)
    if not locations or not any(location["side"] == "old" for location in locations):
        raise _Excluded("missing_python_hunk")
    if changed_lines > _MAX_CHANGED_LINES:
        raise _Excluded("oversized_diff")
    return locations


def parse_unified_diff(patch: str) -> tuple[list[dict[str, object]], int]:
    """Return contiguous changed ranges on both sides and their exact line count."""
    locations: list[dict[str, object]] = []
    current: str | None = None
    old_line: int | None = None
    new_line: int | None = None
    changed_lines = 0
    group_old = 0
    group_new = 0

    def flush_change_group() -> None:
        nonlocal changed_lines, group_old, group_new
        changed_lines += max(group_old, group_new)
        group_old = group_new = 0

    for line in patch.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        path_match = _DIFF_PATH.fullmatch(line)
        if path_match:
            flush_change_group()
            if path_match.group(1) != path_match.group(2):
                raise _Excluded("renamed_file")
            current = path_match.group(1)
            if not current.endswith(".py"):
                raise _Excluded("non_python_change")
            if current.startswith("/") or ".." in Path(current).parts or "\\" in current:
                raise _Excluded("unsafe_patch_path")
            old_line = new_line = None
            continue
        hunk = _HUNK.match(line)
        if hunk and current:
            flush_change_group()
            old_line = int(hunk.group(1))
            new_line = int(hunk.group(3))
            continue
        if current is None or old_line is None or new_line is None:
            continue
        if line.startswith(" "):
            flush_change_group()
            old_line += 1
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            _append_changed_line(locations, current, "old", old_line)
            old_line += 1
            group_old += 1
        elif line.startswith("+") and not line.startswith("+++"):
            _append_changed_line(locations, current, "new", new_line)
            new_line += 1
            group_new += 1
        elif line.startswith("\\"):
            continue
        else:
            flush_change_group()
    flush_change_group()
    return locations, changed_lines


def _append_changed_line(
    locations: list[dict[str, object]], path: str, side: str, line: int
) -> None:
    if (
        locations
        and locations[-1]["path"] == path
        and locations[-1]["side"] == side
        and locations[-1]["end_line"] == line - 1
    ):
        locations[-1]["end_line"] = line
        return
    locations.append({"path": path, "side": side, "start_line": line, "end_line": line})


def _project_patch_matches(
    checkout: Path, buggy_commit: str, fixed_commit: str, patch_bytes: bytes
) -> bool:
    try:
        paths = _unified_diff_paths(patch_bytes)
        actual = subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--no-color",
                buggy_commit,
                fixed_commit,
                "--",
                *paths,
            ],
            cwd=checkout,
            check=True,
            capture_output=True,
        ).stdout
        return normalize_unified_diff_bytes(actual) == normalize_unified_diff_bytes(patch_bytes)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return False


def _unified_diff_paths(patch_bytes: bytes) -> tuple[str, ...]:
    try:
        text = patch_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("unified diff must be UTF-8 text") from exc
    paths: list[str] = []
    for line in text.splitlines():
        match = _DIFF_PATH.fullmatch(line)
        if match is None:
            continue
        old_path, new_path = match.groups()
        if old_path != new_path or old_path.startswith("/") or ".." in Path(old_path).parts:
            raise ValueError("unified diff contains an unsafe path")
        paths.append(old_path)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("unified diff paths must be non-empty and unique")
    return tuple(paths)


def _typed_command(argv: list[str]) -> dict[str, object]:
    executable, *args = argv
    name = Path(executable).name
    if name in {"python", "python3", "{python}"}:
        return {"tool": "python", "args": args}
    if name == "pytest":
        return {"tool": "python", "args": ["-m", "pytest", *args]}
    if name == "tox":
        return {"tool": "tox", "args": args}
    raise _Excluded("unsupported_test_tool")


def _opaque(prefix: str, material: str) -> str:
    return f"{prefix}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def _natural_bug_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
