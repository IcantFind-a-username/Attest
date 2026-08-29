"""Configuration: factory defaults, pricing table, and per-repo .attest.toml."""

from __future__ import annotations

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
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        if self.budget_usd <= 0:
            raise ValueError("budget must be positive")
        if self.k_samples < 1:
            raise ValueError("k_samples must be >= 1")
        if not self.model:
            self.model = str(load_pricing()["default_model"])


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
