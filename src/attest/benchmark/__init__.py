"""Preregistered real-data benchmark records and scoring."""

from attest.benchmark.matcher import MatchResult, match_findings
from attest.benchmark.metrics import BenchmarkReport, aggregate, wilson_interval
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    Prediction,
    RunRecord,
    TruthDefect,
    load_manifest,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkManifest",
    "BenchmarkReport",
    "MatchResult",
    "Prediction",
    "RunRecord",
    "TruthDefect",
    "load_manifest",
    "match_findings",
    "aggregate",
    "wilson_interval",
]
