"""Configuration: factory defaults, pricing table, and per-repo .attest.toml."""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


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


def load_config(repo_root: Path) -> ReviewConfig:
    """Merge .attest.toml (if present) over factory defaults."""
    path = repo_root / ".attest.toml"
    if not path.is_file():
        return ReviewConfig()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    known = {
        "alpha",
        "budget_usd",
        "model",
        "k_samples",
        "max_findings",
        "auto_tighten_alpha",
        "tier0_commands",
    }
    kwargs = {k: v for k, v in raw.items() if k in known}
    return ReviewConfig(**kwargs)
