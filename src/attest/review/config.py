"""Configuration: factory defaults, pricing table, and per-repo .attest.toml."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

POLICY_FILE = ".attest.toml"
POLICY_SOURCE_BASE_FILE = "base:.attest.toml"
POLICY_SOURCE_FACTORY = "factory-defaults"
POLICY_SOURCE_CALLER = "caller"


def load_pricing() -> dict[str, Any]:
    """Factory pricing table shipped with the package."""
    with resources.files("attest.data").joinpath("pricing.toml").open("rb") as f:
        return tomllib.load(f)


@dataclass
class ReviewConfig:
    alpha: float = 0.1
    budget_usd: float = 0.25  # hard cap per review; over-limit -> explicit DEFER
    model: str = ""  # empty -> pricing.toml default_model
    k_samples: int = 5
    max_findings: int = 3  # formal findings cap (formatting only, not a gate)
    auto_tighten_alpha: bool = True
    tier0_commands: list[str] = field(default_factory=lambda: ["ruff"])

    def __post_init__(self) -> None:
        validate_review_config(self)
        if not self.model:
            self.model = str(load_pricing()["default_model"])


def validate_review_config(config: ReviewConfig) -> None:
    """Revalidate a mutable config at every execution boundary."""
    if (
        isinstance(config.alpha, bool)
        or not isinstance(config.alpha, (int, float))
        or not math.isfinite(config.alpha)
        or not 0 < config.alpha < 1
    ):
        raise ValueError("alpha must be a finite number in (0, 1)")
    if (
        isinstance(config.budget_usd, bool)
        or not isinstance(config.budget_usd, (int, float))
        or not math.isfinite(config.budget_usd)
        or config.budget_usd <= 0
    ):
        raise ValueError("budget must be a finite positive number")
    if type(config.k_samples) is not int or config.k_samples < 1:
        raise ValueError("k_samples must be an integer >= 1")
    if type(config.max_findings) is not int or config.max_findings < 1:
        raise ValueError("max_findings must be an integer >= 1")
    if type(config.auto_tighten_alpha) is not bool:
        raise ValueError("auto_tighten_alpha must be a boolean")
    if type(config.tier0_commands) is not list or any(
        type(command) is not str for command in config.tier0_commands
    ):
        raise ValueError("tier0_commands must be a list of strings")


_KNOWN_POLICY_KEYS = {
    "alpha",
    "budget_usd",
    "model",
    "k_samples",
    "max_findings",
    "auto_tighten_alpha",
    "tier0_commands",
}


def _config_from_bytes(raw_bytes: bytes) -> ReviewConfig:
    raw = tomllib.loads(raw_bytes.decode("utf-8"))
    kwargs = {k: v for k, v in raw.items() if k in _KNOWN_POLICY_KEYS}
    return ReviewConfig(**kwargs)


def load_config(repo_root: Path) -> ReviewConfig:
    """Merge the working tree's .attest.toml (if present) over factory defaults.

    Local ``attest review`` only: CI never reads policy from the head checkout
    (see ``resolve_review_policy``).
    """
    path = repo_root / POLICY_FILE
    if not path.is_file():
        return ReviewConfig()
    return _config_from_bytes(path.read_bytes())


def load_policy_bytes_at(repo_root: Path, sha: str) -> bytes | None:
    """The committed .attest.toml at ``sha``; None when that commit has none.

    Any other Git failure is a ValueError: an unreadable trust root must fail
    closed rather than silently become factory defaults.
    """
    spec = f"{sha}:{POLICY_FILE}"
    listed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", sha, "--", POLICY_FILE],
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        raise ValueError(f"cannot read policy at {sha[:12]}: {listed.stderr.strip()[:120]}")
    if not listed.stdout.strip():
        return None
    shown = subprocess.run(
        ["git", "-C", str(repo_root), "show", spec], capture_output=True
    )
    if shown.returncode != 0:
        raise ValueError(f"cannot read policy at {sha[:12]}")
    return shown.stdout


@dataclass(frozen=True)
class ResolvedPolicy:
    """The review policy actually applied, with its trust root recorded."""

    config: ReviewConfig
    source: str  # POLICY_SOURCE_BASE_FILE | POLICY_SOURCE_FACTORY | POLICY_SOURCE_CALLER
    source_digest: str | None  # SHA-256 of the committed policy bytes, if any
    policy_digest: str  # canonical digest of the resolved config and its source


def resolve_review_policy(
    repo_root: Path,
    merge_base_sha: str,
    caller_config: ReviewConfig | None,
    overrides: Mapping[str, object] | None = None,
) -> ResolvedPolicy:
    """Resolve the base-owned policy for one review task.

    The head checkout's ``.attest.toml`` is never consulted. When the caller
    supplies a config it is the protected layer (Action inputs or a benchmark
    harness) and is used as-is; otherwise the committed file at the merge-base
    is the trust root, protected overrides apply on top, and factory defaults
    fill the rest. Any invalid value raises ValueError for the caller to DEFER.
    """
    if caller_config is not None:
        validate_review_config(caller_config)
        config = caller_config
        source = POLICY_SOURCE_CALLER
        source_digest = None
    else:
        raw_bytes = load_policy_bytes_at(repo_root, merge_base_sha)
        if raw_bytes is None:
            config = ReviewConfig()
            source = POLICY_SOURCE_FACTORY
            source_digest = None
        else:
            config = _config_from_bytes(raw_bytes)
            source = POLICY_SOURCE_BASE_FILE
            source_digest = hashlib.sha256(raw_bytes).hexdigest()
        if overrides:
            merged: dict[str, Any] = {**dataclasses.asdict(config), **overrides}
            config = ReviewConfig(**merged)
    resolved = {
        "review": dataclasses.asdict(config),
        "source": source,
        "source_digest": source_digest,
        "merge_base_sha": merge_base_sha,
    }
    digest = hashlib.sha256(
        json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ResolvedPolicy(
        config=config, source=source, source_digest=source_digest, policy_digest=digest
    )
