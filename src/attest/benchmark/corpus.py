"""Metadata-only BugsInPy import and isolated corpus validation."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from attest.benchmark.schema import load_manifest, verify_descriptor_bytes

_MAX_CHANGED_LINES = 400
_INFO_LINE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"\s*$')
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
_DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass(frozen=True)
class RunOutcome:
    """Bounded result of one isolated corpus test command."""

    returncode: int
    output: bytes
    timed_out: bool


class CorpusRunner(Protocol):
    """Execution boundary for generic prepared-corpus validation."""

    def run(self, source_id: str, argv: tuple[str, ...], cwd: Path) -> RunOutcome:
        """Run one test command without a shell."""


class SubprocessCorpusRunner:
    """Run argv-only tests with caller-selected interpreters and bounded resources."""

    def __init__(
        self,
        interpreters: Mapping[str, tuple[str, ...]],
        *,
        timeout_s: float = 60,
        max_output_bytes: int = 65_536,
    ) -> None:
        if timeout_s <= 0 or max_output_bytes <= 0:
            raise ValueError("runner limits must be positive")
        self._interpreters = dict(interpreters)
        self._timeout_s = timeout_s
        self._max_output_bytes = max_output_bytes

    def run(self, source_id: str, argv: tuple[str, ...], cwd: Path) -> RunOutcome:
        if not argv:
            raise ValueError("test argv must not be empty")
        interpreter = self._interpreters.get(source_id)
        if interpreter is None:
            raise ValueError(f"no interpreter configured for {source_id}")
        command = (*interpreter, *argv[1:]) if argv[0] == "{python}" else argv
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
        }
        environment.update(
            {
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "NO_PROXY": "*",
                "no_proxy": "*",
            }
        )
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            output, _ = process.communicate(timeout=self._timeout_s)
            return RunOutcome(process.returncode, output[: self._max_output_bytes], False)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            return RunOutcome(process.returncode, output[: self._max_output_bytes], True)


def validate_corpus(manifest: Path, root: Path, runner: CorpusRunner) -> dict[str, Any]:
    """Validate generic prepared pairs with a repeated differential-test oracle."""
    typed = load_manifest(manifest)
    document = _json_object(manifest)
    runtime_rows = document.get("runtime")
    if not isinstance(runtime_rows, list):
        raise ValueError("manifest runtime must be a list")
    runtimes: dict[str, dict[str, Any]] = {}
    for value in runtime_rows:
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            raise ValueError("runtime row must contain case_id")
        case_id = value["case_id"]
        if case_id in runtimes:
            raise ValueError("duplicate runtime case_id")
        runtimes[case_id] = value
    if set(runtimes) != {case.case_id for case in typed.cases}:
        raise ValueError("runtime rows must exactly cover manifest cases")

    by_pair: dict[str, list[Any]] = {}
    for case in typed.cases:
        by_pair.setdefault(case.pair_id, []).append(case)
    results: list[dict[str, Any]] = []
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
        except (OSError, subprocess.CalledProcessError, ValueError):
            results.append(
                {"pair_id": pair_id, "status": "excluded", "reason": "integrity_failure"}
            )
    validated = sum(result["status"] == "validated" for result in results)
    return {
        "manifest": manifest.name,
        "validated_pairs": validated,
        "excluded_pairs": len(results) - validated,
        "results": results,
    }


def _verify_pair_integrity(
    root: Path,
    replay: Any,
    control: Any,
    runtimes: Mapping[str, dict[str, Any]],
) -> None:
    patch_path = _contained_file(root, replay.patch.relative_path)
    test_path = _contained_file(root, replay.tests.relative_path)
    if not verify_descriptor_bytes(replay.patch, patch_path.read_bytes()):
        raise ValueError("patch hash mismatch")
    if not verify_descriptor_bytes(replay.tests, test_path.read_bytes()):
        raise ValueError("test hash mismatch")
    for case, commit in ((replay, replay.buggy_commit), (control, control.fixed_commit)):
        cwd = _runtime_cwd(root, runtimes[case.case_id])
        if _git(cwd, "rev-parse", "HEAD") != commit:
            raise ValueError("checkout commit mismatch")


def _run_three(
    case: Any,
    runtime: dict[str, Any],
    root: Path,
    runner: CorpusRunner,
) -> list[RunOutcome]:
    argv_value = runtime.get("test_argv")
    if (
        not isinstance(argv_value, list)
        or not argv_value
        or any(not isinstance(value, str) or not value for value in argv_value)
    ):
        raise ValueError("test_argv must be a non-empty string list")
    argv = tuple(argv_value)
    cwd = _runtime_cwd(root, runtime)
    outcomes: list[RunOutcome] = []
    for _ in range(3):
        outcome = runner.run(case.source_id, argv, cwd)
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


def _runtime_cwd(root: Path, runtime: dict[str, Any]) -> Path:
    value = runtime.get("cwd")
    if not isinstance(value, str) or not value:
        raise ValueError("runtime cwd must be a relative path")
    path = root / value
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("runtime cwd escapes corpus root") from exc
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError("runtime cwd must be a real directory")
    return resolved


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
                        f"{base['source_id']}/replay"
                        if role == "historical_bug_replay"
                        else f"{base['source_id']}/control"
                    ),
                    "test_argv": candidate["test_argv"],
                    "python_version": candidate["python_version"],
                }
            )
        for index, location in enumerate(base["changed_locations"], start=1):
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
        "test_argv": test_argv,
        "case": {
            "pair_id": pair_id,
            "source_id": source_id,
            "provenance_kind": "historical_fix",
            "source_license": declared_license,
            "buggy_commit": buggy_commit,
            "fixed_commit": fixed_commit,
            "patch": {
                "relative_path": relative_patch,
                "sha256": hashlib.sha256(patch_bytes).hexdigest(),
                "normalization": "bytes",
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
        text = contents.decode("utf-8", errors="strict")
    except (_Excluded, OSError, UnicodeDecodeError):
        return None
    if "MIT License" in text and "Permission is hereby granted" in text:
        identifier = "MIT"
    elif "Apache License" in text and "Version 2.0" in text:
        identifier = "Apache-2.0"
    elif "Redistribution and use in source and binary forms" in text:
        identifier = "BSD-3-Clause"
    else:
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
    if (
        "Permission is hereby granted, free of charge" in text
        and 'THE SOFTWARE IS PROVIDED "AS IS"' in text
    ) or ("MIT License" in text and "Permission is hereby granted" in text):
        return "MIT"
    if "Apache License" in text and "Version 2.0" in text:
        return "Apache-2.0"
    if "Redistribution and use in source and binary forms" in text:
        return "BSD-3-Clause"
    return None


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
    locations: list[dict[str, object]] = []
    current: str | None = None
    changed_lines = 0
    for line in patch.splitlines():
        path_match = _DIFF_PATH.fullmatch(line)
        if path_match:
            if path_match.group(1) != path_match.group(2):
                raise _Excluded("renamed_file")
            current = path_match.group(1)
            if not current.endswith(".py"):
                raise _Excluded("non_python_change")
            if current.startswith("/") or ".." in Path(current).parts or "\\" in current:
                raise _Excluded("unsafe_patch_path")
            continue
        hunk = _HUNK.match(line)
        if hunk and current:
            start = int(hunk.group(1))
            count = int(hunk.group(2) or "1")
            changed_lines += count
            locations.append(
                {
                    "path": current,
                    "start_line": max(1, start),
                    "end_line": max(1, start + count - 1),
                }
            )
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            changed_lines += 1
    if not locations:
        raise _Excluded("missing_python_hunk")
    if changed_lines > _MAX_CHANGED_LINES:
        raise _Excluded("oversized_diff")
    return locations


def _opaque(prefix: str, material: str) -> str:
    return f"{prefix}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def _natural_bug_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
