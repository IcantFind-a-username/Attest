"""G-RELEASE-001 operational drills, minimal set: kill switch and rollback.

Offline and free. No model call, no credential, no network beyond a git
repository this script creates in a temporary directory. Every drill drives
the product's own code path -- `resolve_review_policy`, `run_review`,
`verify_bundle` -- rather than restating what those functions are supposed to
do, and every drill carries a negative control, because a drill that cannot
fail proves nothing.

    python scripts/release/drill.py --all
    python scripts/release/drill.py --all --record docs/acceptance/<date>-drills.md

The remaining seven drills named by G-RELEASE-001 (revoked credential, GitHub
outage, executor unavailable, budget exhaustion, superseded pull request,
malicious same-repository change, verifier failure) are not implemented here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.types import AcceptedReceipt  # noqa: E402
from attest.review.config import (  # noqa: E402
    DISABLED_REASON,
    ReviewConfig,
    resolve_review_policy,
)
from attest.review.evidence import verify_bundle  # noqa: E402
from attest.review.proposer import ProviderResult  # noqa: E402
from attest.review.run import run_review  # noqa: E402


@dataclass
class Drill:
    name: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, what: str, passed: bool, detail: str = "") -> None:
        self.checks.append((what, bool(passed), detail))

    @property
    def passed(self) -> bool:
        return all(passed for _, passed, _ in self.checks)


class ScriptedProvider:
    """Replays one proposal and one reproduction; counts every call so a drill
    can assert that nothing was bought."""

    def __init__(self) -> None:
        self.calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls += 1
        if "focused pytest reproduction" in system:
            payload = json.dumps(
                {
                    "test_body": "import runpy\n\n"
                    "def test_average_handles_empty_input():\n"
                    "    average = runpy.run_path('app.py')['average']\n"
                    "    assert average([]) == 0\n"
                }
            )
        else:
            payload = json.dumps(
                {
                    "findings": [
                        {
                            "claim": "average() divides by zero when items is empty.",
                            "anchor": {"file": "app.py", "line": 6},
                            "failure_scenario": "average([]) raises ZeroDivisionError",
                            "falsification_plan": (
                                "call average([]) and require a safe empty result"
                            ),
                        }
                    ]
                }
            )
        return ProviderResult(text=payload, input_tokens=10, output_tokens=10)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _planted_repo(
    root: Path, *, base_policy: str | None, head_policy: str | None
) -> tuple[str, str]:
    """A regression a reproduction can certify: `average` is correct on base and
    divides by zero on head. `base_policy`/`head_policy` write `.attest.toml`
    on each side, so a drill can put a different answer on each."""
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "drill@example.com")
    _git(root, "config", "user.name", "Release drill")
    (root / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    if base_policy is not None:
        (root / ".attest.toml").write_text(base_policy, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    (root / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    if head_policy is not None:
        (root / ".attest.toml").write_text(head_policy, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "regress average to divide by zero")
    return base_sha, _git(root, "rev-parse", "HEAD")


def drill_kill_switch(workspace: Path) -> Drill:
    """`.attest.toml` on the base branch stops every review of a pull request
    into it, and the head of that pull request cannot flip it back on."""
    drill = Drill("kill switch")

    repo = workspace / "kill-switch"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(
        repo, base_policy="enabled = false\n", head_policy="enabled = true\n"
    )

    # 1. the trust root: CI resolves the policy at the merge base, and the head
    #    checkout's file -- which says `true` -- is never consulted
    resolved = resolve_review_policy(repo, base_sha, None)
    drill.check(
        "base policy owns the switch; the head cannot flip it",
        resolved.config.enabled is False,
        f"resolved enabled={resolved.config.enabled} from {resolved.source}",
    )

    # 2. the review itself stops before any model call and buys nothing
    provider = ScriptedProvider()
    run = run_review(repo, base_sha, resolved.config, provider, verify=True)
    drill.check("review defers", run.deferred_reason == DISABLED_REASON, str(run.deferred_reason))
    drill.check("no model call", provider.calls == 0, f"{provider.calls} call(s)")
    drill.check("nothing spent", run.budget.spent_usd == 0.0, f"${run.budget.spent_usd:.6f}")
    drill.check("no candidate reached ranking", not run.results, f"{len(run.results)} result(s)")
    drill.check(
        "no evidence bundle written",
        not list((repo / ".attest" / "evidence").glob("*")),
        ".attest/evidence is empty",
    )

    # negative control: the same repository with the switch on must proceed,
    # otherwise the checks above would pass for the wrong reason
    control = workspace / "kill-switch-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy="enabled = true\n", head_policy=None)
    control_policy = resolve_review_policy(control, control_base, None)
    control_provider = ScriptedProvider()
    control_run = run_review(control, control_base, control_policy.config, control_provider)
    drill.check(
        "negative control: the switch on lets the review run",
        control_provider.calls > 0 and control_run.deferred_reason != DISABLED_REASON,
        f"{control_provider.calls} call(s), deferred={control_run.deferred_reason!r}",
    )
    return drill


def drill_rollback(workspace: Path) -> Drill:
    """A bundle written by this version verifies offline; a bundle whose schema
    version an older verifier would not know is *rejected*, never misread. That
    is what makes rolling the action ref back safe."""
    drill = Drill("rollback")

    repo = workspace / "rollback"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    provider = ScriptedProvider()
    run = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        verify=True,
        verification_timeout_s=180.0,
    )
    evidence = repo / ".attest" / "evidence"
    bundles = sorted(p for p in evidence.glob("*/*") if p.is_dir()) if evidence.is_dir() else []
    drill.check(
        "a review of a real regression writes an evidence bundle",
        bool(bundles),
        f"{len(bundles)} bundle(s); deferred={run.deferred_reason!r}",
    )
    if not bundles:
        return drill
    bundle = bundles[0]

    drill.check(
        "the bundle verifies offline as written",
        isinstance(verify_bundle(bundle), AcceptedReceipt),
        str(type(verify_bundle(bundle)).__name__),
    )

    # a version this verifier does not know must be refused, not read anyway:
    # that is the property a rollback to an earlier action ref relies on
    unknown = workspace / "bundle-unknown-version"
    shutil.copytree(bundle, unknown)
    manifest_path = unknown / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "attest.evidence-bundle.v999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    drill.check(
        "an unknown bundle schema version is rejected, not misread",
        not isinstance(verify_bundle(unknown), AcceptedReceipt),
        str(type(verify_bundle(unknown)).__name__),
    )

    # negative control for the verifier itself: a flipped byte must also reject,
    # otherwise "rejected" above would say nothing about the verifier's teeth
    tampered = workspace / "bundle-tampered"
    shutil.copytree(bundle, tampered)
    target = tampered / "test_repro.py"
    data = bytearray(target.read_bytes())
    data[0] = (data[0] + 1) % 256
    target.write_bytes(bytes(data))
    drill.check(
        "negative control: a flipped byte is rejected",
        not isinstance(verify_bundle(tampered), AcceptedReceipt),
        str(type(verify_bundle(tampered)).__name__),
    )

    # the documented rollback target must exist in this repository
    doc = (ROOT / "docs" / "operations" / "install-ref.md").read_text(encoding="utf-8")
    named = [line for line in doc.splitlines() if "oldest ref" in line]
    ref = ""
    for line in named:
        for token in line.replace("`", " ").split():
            if token.startswith("v0.") or token.startswith("v1."):
                ref = token
                break
    resolved_ref = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    drill.check(
        "the documented oldest rollback target resolves",
        bool(ref) and resolved_ref.returncode == 0,
        f"{ref or '(none named)'} -> {resolved_ref.stdout.strip() or resolved_ref.stderr.strip()}",
    )
    return drill



class FailingProvider:
    """A provider that always raises, with the message a real outage returns."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls += 1
        raise RuntimeError(self.message)


def _bundles(repo: Path) -> list[Path]:
    evidence = repo / ".attest" / "evidence"
    return sorted(p for p in evidence.glob("*/*") if p.is_dir()) if evidence.is_dir() else []


def _ledger_text(repo: Path) -> str:
    path = repo / ".attest" / "ledger.jsonl"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def drill_revoked_credential(workspace: Path) -> Drill:
    """The model credential is revoked mid-flight. The review must defer with a
    stated reason rather than raise, publish nothing, execute no head code, and
    never write the credential's value anywhere a human or a log can read it."""
    drill = Drill("revoked credential")

    secret = "sk-ant-drill-0000000000000000000000000000"
    repo = workspace / "revoked-credential"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    provider = FailingProvider(f"401 authentication_error: invalid x-api-key {secret}")

    previous = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = secret
    try:
        run = run_review(
            repo, base_sha, ReviewConfig(k_samples=2, tier0_commands=[]), provider, verify=True
        )
    finally:
        if previous is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = previous

    drill.check(
        "the review defers with a stated reason, it does not raise",
        run.deferred_reason is not None,
        str(run.deferred_reason),
    )
    drill.check("the credential was actually used", provider.calls > 0, f"{provider.calls} call(s)")
    drill.check("nothing is published", not run.published, f"{len(run.published)} published")
    drill.check("no evidence bundle is written", not _bundles(repo), f"{len(_bundles(repo))}")
    drill.check(
        "no head code is executed",
        not (repo / ".attest" / "repro").exists(),
        ".attest/repro does not exist",
    )
    rendered = str(run.deferred_reason) + " ".join(run.notes)
    drill.check(
        "the credential value is in neither the ledger nor the author-visible text",
        secret not in _ledger_text(repo) and secret not in rendered,
        "redacted",
    )

    # negative control: the same repository with a working provider must reach a
    # receipt, or every check above would pass for the wrong reason
    control = workspace / "revoked-credential-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy=None, head_policy=None)
    control_run = run_review(
        control,
        control_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    drill.check(
        "negative control: a working credential reaches a receipt",
        bool(control_run.certified) and bool(_bundles(control)),
        f"{len(control_run.certified)} certified, {len(_bundles(control))} bundle(s)",
    )
    return drill


DRILLS = {
    "kill-switch": drill_kill_switch,
    "rollback": drill_rollback,
    "revoked-credential": drill_revoked_credential,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--all", action="store_true", help="run every implemented drill")
    parser.add_argument("--only", default=None, help=f"one of {', '.join(DRILLS)}")
    parser.add_argument(
        "--offline", action="store_true", help="accepted and ignored: every drill is offline"
    )
    parser.add_argument("--record", default=None, help="write the result table to this path")
    args = parser.parse_args(argv)

    names = [args.only] if args.only else list(DRILLS)
    if args.only and args.only not in DRILLS:
        parser.error(f"unknown drill {args.only!r}")

    results: list[Drill] = []
    with tempfile.TemporaryDirectory(prefix="attest-drill-") as workspace:
        # the strict ledger refuses a path with a symlinked ancestor, and on
        # macOS the system temporary directory is one
        root = Path(workspace).resolve()
        for name in names:
            drill = DRILLS[name](root)
            results.append(drill)
            print(f"\n== {drill.name}: {'PASS' if drill.passed else 'FAIL'}")
            for what, passed, detail in drill.checks:
                mark = "ok  " if passed else "FAIL"
                print(f"   {mark} {what}" + (f"  [{detail}]" if detail else ""))

    if args.record:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        lines = [
            "# G-RELEASE-001 operational drills (kill switch, rollback)",
            "",
            f"Run {stamp} at `{head[:7]}` by `scripts/release/drill.py`. Offline: no model call,",
            "no credential, no network. Seven of the nine named drills are not implemented.",
            "",
            "| drill | check | result | detail |",
            "|---|---|---|---|",
        ]
        for drill in results:
            for what, passed, detail in drill.checks:
                verdict = "pass" if passed else "**fail**"
                lines.append(f"| {drill.name} | {what} | {verdict} | {detail} |")
        lines.append("")
        Path(args.record).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nrecorded -> {args.record}")

    return 0 if all(drill.passed for drill in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
