"""C-05 selection interface; C-01 supplies no selection implementation."""

from __future__ import annotations

from typing import Protocol

from .types import CertifiedFinding


class CertifiedSelection(Protocol):
    def select(
        self, findings: tuple[CertifiedFinding, ...]
    ) -> tuple[CertifiedFinding, ...]: ...
