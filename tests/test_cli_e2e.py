"""End-to-end CLI test on a real temp git repo with a mock provider."""

import hashlib
import json
import subprocess
from pathlib import Path

import anthropic
import pytest

from attest.cli.main import main
from attest.review.candidates import CandidateStore
from attest.review.config import load_pricing
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.schema import Finding

CLEAN = """def total(items):
    return sum(items)
"""

BUGGY = """def total(items):
    return sum(items)


def average(items):
    result = sum(items) / len(items)
    return result
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text(CLEAN, encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text(BUGGY, encoding="utf-8")
    return tmp_path


def _payload(*findings: dict) -> str:
    return json.dumps({"findings": list(findings)})


def _event_path(repo: Path, tmp_path: Path) -> Path:
    base_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    event = {
        "number": 9,
        "repository": {"full_name": "octo/widgets"},
        "pull_request": {
            "base": {"sha": base_sha},
            "head": {"sha": base_sha, "repo": {"full_name": "octo/widgets"}},
        },
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    return path


FINDING_A = {
    "claim": "average() divides by zero when items is empty.",
    "anchor": {"file": "app.py", "line": 6},
    "failure_scenario": "average([]) raises ZeroDivisionError",
    "falsification_plan": "call average([]) and observe the exception",
}
FINDING_A2 = {
    "claim": "Division by zero in average() when items is an empty list.",
    "anchor": {"file": "app.py", "line": 6},
    "failure_scenario": "average([]) -> ZeroDivisionError",
    "falsification_plan": "run average([])",
}


@pytest.fixture
def mocks(tmp_path: Path) -> list[str]:
    p1 = tmp_path / "m1.json"
    p2 = tmp_path / "m2.json"
    p3 = tmp_path / "m3.json"
    p1.write_text(_payload(FINDING_A), encoding="utf-8")
    p2.write_text(_payload(FINDING_A2), encoding="utf-8")
    p3.write_text(_payload(), encoding="utf-8")
    return [str(p1), str(p2), str(p3)]


def test_review_verify_feedback_stats(repo: Path, mocks: list[str], capsys) -> None:
    # --- review: 2 of 3 samples assert the finding -> drawer (S=2.64 < 10)
    rc = main(["--repo", str(repo), "review", "--k", "3", "--mock", *mocks])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no findings cleared the evidence bar" in out
    assert "drawer (1 candidate(s)" in out
    assert "reachable only" in out  # feasibility transparency note
    assert "divides by zero" in out or "Division by zero" in out

    ledger_path = repo / ".attest" / "ledger.jsonl"
    assert ledger_path.is_file()
    entries = [json.loads(x) for x in ledger_path.read_text().splitlines() if x.strip()]
    reviews = [e for e in entries if e["kind"] == "review"]
    assert len(reviews) == 1
    assert reviews[0]["action"] == "drawer"
    assert reviews[0]["channels_bought"] == ["S"]
    finding_id = reviews[0]["finding_id"]
    # CandidateStore must skip malformed legacy/corrupt rows so a valid stored
    # candidate remains verifiable.
    candidates_path = repo / ".attest" / "candidates.jsonl"
    candidates_path.write_text(
        '{"task_id": "incomplete"}\n' + candidates_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # --- verify: reproduction pushes wealth past the gate
    rc = main(
        [
            "--repo",
            str(repo),
            "verify",
            finding_id,
            "--reproduced",
            "--evidence",
            "python -c average([]) -> ZeroDivisionError",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "self-report recorded" in out
    assert "surface" not in out

    # --- feedback + stats: a self-report never enters the surfaced population
    rc = main(["--repo", str(repo), "feedback", finding_id, "--good"])
    capsys.readouterr()
    assert rc == 0
    rc = main(["--repo", str(repo), "stats"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "runs: 1" in out
    assert "surfaced: 0" in out
    assert "self-reports: 1 (manual; excluded from precision)" in out
    assert "surfaced precision: undefined" in out


def test_stats_uses_the_same_deduplicated_surface_population_as_precision(
    repo: Path, capsys
) -> None:
    ledger = Ledger(repo)
    ledger.record_review("task-1", "finding-1", ["S"], 0.0, 12.0, "surface")
    ledger.record_review(
        "task-1", "finding-1", ["V"], 0.0, 60.0, "verified_surface"
    )
    ledger.record_feedback("finding-1", "good")

    assert main(["--repo", str(repo), "stats"]) == 0

    out = capsys.readouterr().out
    assert "findings evaluated: 2; surfaced: 1\n" in out
    assert "surfaced precision: 1.0 (1 labeled)" in out
    assert "abstention rate: undefined (no review runs)" in out
    assert "silence precision: undefined (no labeled silent outcomes)" in out


def test_stats_marks_majority_abstention_as_anomaly(repo: Path, capsys) -> None:
    ledger = Ledger(repo)
    for task_id in ("task-1", "task-2", "task-3"):
        ledger.append(
            {
                "kind": "review_run",
                "task_id": task_id,
                "spend_usd": 0.0,
            }
        )
    ledger.record_review("task-1", "finding-1", ["S"], 0.0, 12.0, "surface")

    assert main(["--repo", str(repo), "stats"]) == 0

    out = capsys.readouterr().out
    assert "abstention rate: 0.666667 (2/3 runs) — ANOMALY (> 0.5)" in out
    assert "silence precision: undefined (no labeled silent outcomes)" in out


def test_feedback_flags_record_distinct_labels(repo: Path, capsys) -> None:
    """--wrong and --wontfix must be distinguishable in the ledger, and the
    legacy --dismiss flag must still work (marked ambiguous)."""
    ledger_path = repo / ".attest" / "ledger.jsonl"
    flag_to_label = {
        "--fix": "fix",
        "--good": "good",
        "--wrong": "wrong",
        "--wontfix": "wontfix",
        "--dismiss": "dismiss",
    }
    for flag, label in flag_to_label.items():
        rc = main(["--repo", str(repo), "feedback", f"finding-{label}", flag])
        capsys.readouterr()
        assert rc == 0

    entries = [json.loads(x) for x in ledger_path.read_text().splitlines() if x.strip()]
    by_finding = {e["finding_id"]: e for e in entries if e["kind"] == "feedback"}
    expected_polarity = {
        "fix": "true",
        "good": "true",
        "wrong": "false",
        "wontfix": "true",
        "dismiss": "ambiguous",
    }
    for label, polarity in expected_polarity.items():
        entry = by_finding[f"finding-{label}"]
        assert entry["feedback"] == label
        assert entry["label_polarity"] == polarity


def test_review_budget_defer(repo: Path, mocks: list[str], capsys) -> None:
    rc = main(["--repo", str(repo), "review", "--k", "3", "--budget", "0.000001", "--mock", *mocks])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DEFER: budget:" in out
    entries = [
        json.loads(x)
        for x in (repo / ".attest" / "ledger.jsonl").read_text().splitlines()
        if x.strip()
    ]
    assert any(e["kind"] == "defer" for e in entries)


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "-1"])
def test_ci_rejects_nonfinite_or_nonpositive_verification_timeout(timeout: str) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["ci", "--event-path", "event.json", "--verification-timeout", timeout])

    assert caught.value.code == 2


def test_review_no_diff(repo: Path, mocks: list[str], capsys) -> None:
    subprocess.run(["git", "-C", str(repo), "checkout", "--", "app.py"], check=True)
    rc = main(["--repo", str(repo), "review", "--mock", mocks[0]])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no diff" in out


def test_review_no_diff_does_not_construct_a_real_client(repo: Path, capsys, monkeypatch) -> None:
    subprocess.run(["git", "-C", str(repo), "checkout", "--", "app.py"], check=True)

    def unexpected_client(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("real client should not be constructed")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected_client)

    rc = main(["--repo", str(repo), "review"])

    assert rc == 0
    assert "no diff" in capsys.readouterr().out


def test_mock_without_files_rejected(repo: Path) -> None:
    # regression: `--mock` with zero files must NEVER fall through to the
    # real paid API — argparse rejects it outright
    with pytest.raises(SystemExit):
        main(["--repo", str(repo), "review", "--mock"])


def test_invalid_cli_override_rejected(repo: Path, mocks: list[str], capsys) -> None:
    # regression: CLI overrides must go through config validation
    rc = main(["--repo", str(repo), "review", "--alpha", "5.0", "--mock", *mocks])
    assert rc == 2
    assert "alpha" in capsys.readouterr().err


def test_verify_unknown_id(repo: Path, capsys) -> None:
    rc = main(["--repo", str(repo), "verify", "0000000000", "--reproduced"])
    assert rc == 2


def test_verify_uses_the_selected_task_for_duplicate_finding_ids(repo: Path, capsys) -> None:
    finding = Finding(
        claim="average() divides by zero when items is empty.",
        file="app.py",
        line=6,
        failure_scenario="average([]) raises ZeroDivisionError",
        falsification_plan="call average([]) and observe the exception",
    )
    store = CandidateStore(repo)
    store.append("first-task", 0.1, [GateResult(finding=finding, wealth=2.0)])
    store.append("second-task", 0.1, [GateResult(finding=finding, wealth=0.2)])

    rc = main(
        [
            "--repo",
            str(repo),
            "verify",
            finding.finding_id,
            "--task-id",
            "first-task",
            "--reproduced",
        ]
    )

    assert rc == 0
    assert "self-report recorded: reproduced" in capsys.readouterr().out
    entries = [
        json.loads(line) for line in (repo / ".attest" / "ledger.jsonl").read_text().splitlines()
    ]
    assert entries[-1]["kind"] == "self_report"
    assert entries[-1]["task_id"] == "first-task"


def test_unreachable_gate_refused(repo: Path, mocks: list[str], capsys) -> None:
    rc = main(["--repo", str(repo), "review", "--alpha", "0.001", "--k", "3", "--mock", *mocks])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unreachable" in err


def test_unreachable_gate_does_not_construct_a_real_client(repo: Path, capsys, monkeypatch) -> None:
    def unexpected_client(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("real client should not be constructed")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected_client)

    rc = main(["--repo", str(repo), "review", "--alpha", "0.001"])

    assert rc == 2
    assert "unreachable" in capsys.readouterr().err


def test_ci_rejects_missing_github_token(
    repo: Path, tmp_path: Path, mocks: list[str], capsys, monkeypatch
) -> None:
    event_path = _event_path(repo, tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    rc = main(
        [
            "--repo",
            str(repo),
            "ci",
            "--event-path",
            str(event_path),
            "--mock",
            mocks[0],
        ]
    )

    assert rc == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_ci_rejects_malformed_pull_request_event(
    repo: Path, tmp_path: Path, mocks: list[str], capsys, monkeypatch
) -> None:
    event_path = tmp_path / "malformed-event.json"
    event_path.write_text('{"repository": {}}', encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")

    rc = main(
        [
            "--repo",
            str(repo),
            "ci",
            "--event-path",
            str(event_path),
            "--mock",
            mocks[0],
        ]
    )

    assert rc == 2
    assert "event" in capsys.readouterr().err.lower()


def test_ci_mock_provider_routes_offline_and_prints_one_json_result(
    repo: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    from attest.github.client import GitHubClient, PreparedGitHubWrite
    from attest.review import ci as ci_module

    event_path = _event_path(repo, tmp_path)
    event_payload = json.loads(event_path.read_text(encoding="utf-8"))
    expected_head_sha = event_payload["pull_request"]["head"]["sha"]
    expected_task_id = "cli-e2e-task"
    empty_payload = tmp_path / "empty.json"
    empty_payload.write_text(_payload(), encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")
    monkeypatch.setenv("GITHUB_API_URL", "http://127.0.0.1:9")

    def unexpected_client(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("offline --mock must not construct a paid API client")

    def prepare_status(
        self, repository, number, marker, body  # noqa: ANN001
    ) -> PreparedGitHubWrite:
        return PreparedGitHubWrite(
            method="POST",
            path=f"/repos/{repository}/issues/{number}/comments",
            payload={"body": f"{marker}\n{body}"},
        )

    def execute_status(self, request):  # noqa: ANN001
        return {"id": 1}

    def unexpected_review(self, repository, number, commit_id, comments):  # noqa: ANN001
        raise AssertionError("negative control must not post an inline review")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected_client)
    monkeypatch.setattr(ci_module, "make_task_id", lambda _seed: expected_task_id)
    monkeypatch.setattr(GitHubClient, "prepare_issue_comment", prepare_status)
    monkeypatch.setattr(GitHubClient, "execute_prepared_write", execute_status)
    monkeypatch.setattr(GitHubClient, "create_review", unexpected_review)

    rc = main(
        [
            "--repo",
            str(repo),
            "ci",
            "--event-path",
            str(event_path),
            "--verification-timeout",
            "15",
            "--budget",
            "0.1",
            "--model",
            str(load_pricing()["default_model"]),
            "--k",
            "1",
            "--mock",
            str(empty_payload),
        ]
    )

    assert rc == 0
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    result = json.loads(output)
    assert set(result) == {
        "task_id",
        "candidate_count",
        "surfaced_count",
        "deferred_reason",
        "spend_usd",
        "elapsed_s",
        "publication_events",
        "task_delivery_events",
        "delivery_transcript",
    }
    assert result["candidate_count"] == 0
    assert result["surfaced_count"] == 0
    assert result["deferred_reason"] is None
    assert result["task_id"] == expected_task_id
    assert result["publication_events"] == []

    task_events = result["task_delivery_events"]
    assert type(task_events) is list and len(task_events) == 1
    event = task_events[0]
    assert set(event) == {
        "event_id",
        "attempt_id",
        "attempt_ordinal",
        "repository",
        "pull_request_number",
        "head_sha",
        "channel",
        "members",
        "terminal_status",
        "body_sha256",
        "request_sha256",
        "outcome",
        "remote_response_id",
        "delivered_at_s",
        "deadline_s",
    }
    assert event["attempt_ordinal"] == 0
    assert event["repository"] == "octo/widgets"
    assert event["pull_request_number"] == 9
    assert event["channel"] == "status_summary"
    assert event["members"] == []
    assert event["terminal_status"] == "completed"
    assert event["outcome"] == "succeeded"
    assert event["remote_response_id"] == "1"
    assert type(event["delivered_at_s"]) is float
    assert event["delivered_at_s"] >= 0.0
    assert event["deadline_s"] is None
    assert event["head_sha"] == expected_head_sha
    for key in ("body_sha256", "request_sha256"):
        assert type(event[key]) is str
        assert len(event[key]) == 64
        assert set(event[key]) <= set("0123456789abcdef")
    expected_attempt_id = hashlib.sha256(
        f"{expected_task_id}:0:{event['request_sha256']}".encode()
    ).hexdigest()
    assert event["attempt_id"] == expected_attempt_id
    assert event["event_id"] == hashlib.sha256(
        f"{expected_attempt_id}:task_delivery".encode()
    ).hexdigest()

    transcript = result["delivery_transcript"]
    assert type(transcript) is dict
    assert set(transcript) == {
        "schema_version",
        "protocol",
        "task_id",
        "expected_attempt_count",
        "last_attempt_ordinal",
        "transcript_sha256",
    }
    assert type(transcript["schema_version"]) is int
    assert transcript["schema_version"] == 1
    assert transcript["protocol"] == "attest.delivery-transcript.v1"
    assert transcript["task_id"] == expected_task_id
    assert type(transcript["expected_attempt_count"]) is int
    assert transcript["expected_attempt_count"] == 1
    assert type(transcript["last_attempt_ordinal"]) is int
    assert transcript["last_attempt_ordinal"] == 0
    assert type(transcript["transcript_sha256"]) is str
    assert len(transcript["transcript_sha256"]) == 64
    assert set(transcript["transcript_sha256"]) <= set("0123456789abcdef")


def test_ci_mock_without_files_is_rejected(repo: Path, tmp_path: Path) -> None:
    event_path = _event_path(repo, tmp_path)

    with pytest.raises(SystemExit):
        main(["--repo", str(repo), "ci", "--event-path", str(event_path), "--mock"])


def test_ci_invalid_model_override_remains_a_cli_error(
    repo: Path, tmp_path: Path, mocks: list[str], capsys, monkeypatch
) -> None:
    from attest.github.client import GitHubClient

    event_path = _event_path(repo, tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")
    monkeypatch.setattr(
        GitHubClient,
        "upsert_issue_comment",
        lambda self, repository, number, marker, body: {"id": 1},
    )

    rc = main(
        [
            "--repo",
            str(repo),
            "ci",
            "--event-path",
            str(event_path),
            "--model",
            "not-a-model",
            "--k",
            "1",
            "--mock",
            mocks[0],
        ]
    )

    assert rc == 2
    assert "pricing" in capsys.readouterr().err


def test_manual_reproduction_moves_no_finding_and_no_precision_window(
    repo: Path, mocks: list[str], capsys
) -> None:
    """G-CERT-003: a self-reported reproduction is a note, not evidence.

    ``attest verify --reproduced`` must not move the finding across any
    threshold, must not enter the author-visible population or the precision
    window that drives alpha auto-tightening, and legacy ``verified_*`` rows
    must stay readable in their own namespace without being upgraded.
    """
    assert main(["--repo", str(repo), "review", "--k", "3", "--mock", *mocks]) == 0
    capsys.readouterr()
    ledger = Ledger(repo)
    review = next(row for row in ledger.entries_strict() if row["kind"] == "review")
    finding_id = str(review["finding_id"])

    rc = main(
        ["--repo", str(repo), "verify", finding_id, "--reproduced", "--evidence", "ran it"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "self-report" in out
    assert "surface" not in out
    assert "wealth" not in out

    rows = ledger.entries_strict()
    assert not [
        row
        for row in rows
        if row["kind"] == "review" and str(row["action"]).startswith("verified_")
    ]
    self_reports = [row for row in rows if row["kind"] == "self_report"]
    assert [row["finding_id"] for row in self_reports] == [finding_id]
    assert self_reports[0]["reproduced"] is True
    assert self_reports[0]["evidence"] == "ran it"
    assert ledger.surfaced_finding_ids() == ()

    assert main(["--repo", str(repo), "feedback", finding_id, "--good"]) == 0
    capsys.readouterr()
    assert ledger.surfaced_precision() == (None, 0)
    assert ledger.current_alpha(0.1) == 0.1

    # legacy rows: readable, in their own namespace, never upgraded
    ledger.record_review("legacy-task", "legacy-1", ["V"], 0.0, 60.0, "verified_surface")
    ledger.record_feedback("legacy-1", "good")
    assert ledger.surfaced_finding_ids() == ()
    assert ledger.surfaced_precision() == (None, 0)
    assert [row["namespace"] for row in ledger.self_reports()] == [
        "self_reported",
        "legacy_self_reported_unknown",
    ]

    assert main(["--repo", str(repo), "stats"]) == 0
    out = capsys.readouterr().out
    assert "surfaced: 0" in out
    assert "self-reports: 2 (manual; excluded from precision)" in out
