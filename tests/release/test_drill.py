"""G-RELEASE-001: the two implemented operational drills, and the proof that
they can fail. A drill suite that passes against a broken switch is worse than
no drill suite, because it is evidence for a claim it never tested."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.release.drill import drill_kill_switch, drill_rollback


def test_the_kill_switch_and_rollback_drills_pass_offline(tmp_path: Path) -> None:
    kill_switch = drill_kill_switch(tmp_path.resolve())
    assert kill_switch.passed, kill_switch.checks
    rollback = drill_rollback(tmp_path.resolve())
    assert rollback.passed, rollback.checks


def test_the_kill_switch_drill_fails_when_the_head_can_flip_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control on the drill itself: with the base policy read from
    the head checkout instead of the merge base -- the exact bypass the switch
    exists to prevent -- the drill must report a failure, not a pass."""
    from scripts.release import drill as drill_module

    def head_policy(repo: Path, merge_base_sha: str, caller, overrides=None):  # type: ignore[no-untyped-def]
        from attest.review.config import resolve_review_policy as real

        return real(repo, "HEAD", caller, overrides)

    monkeypatch.setattr(drill_module, "resolve_review_policy", head_policy)
    result = drill_kill_switch(tmp_path.resolve())
    assert not result.passed
    assert any(
        not passed and "head cannot flip it" in what for what, passed, _ in result.checks
    )


def test_the_rollback_drill_fails_when_the_verifier_accepts_an_unknown_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for rollback: a verifier that reads a bundle whose
    schema version it does not know is exactly what makes rolling the action ref
    back unsafe, and the drill must say so."""
    from scripts.release import drill as drill_module

    real_verify = drill_module.verify_bundle

    def lenient(directory: Path, **kwargs: object) -> object:
        manifest_path = directory / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("schema_version", "")).endswith(".v999"):
                manifest["schema_version"] = "attest.evidence-bundle.v1"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        verdict = real_verify(directory, **kwargs)  # type: ignore[arg-type]
        return verdict

    monkeypatch.setattr(drill_module, "verify_bundle", lenient)
    result = drill_rollback(tmp_path.resolve())
    assert not result.passed
    assert any(
        not passed and "unknown bundle schema version" in what
        for what, passed, _ in result.checks
    )
