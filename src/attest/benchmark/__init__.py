"""Preregistered real-data benchmark records and scoring."""

from attest.benchmark.matcher import MatchResult, match_findings
from attest.benchmark.metrics import BenchmarkReport, aggregate, wilson_interval
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    PatchDescriptor,
    Placement,
    Prediction,
    RunRecord,
    TestDescriptor,
    TruthDefect,
    is_scored_placement,
    load_manifest,
    verify_descriptor_bytes,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkManifest",
    "BenchmarkReport",
    "MatchResult",
    "PatchDescriptor",
    "Placement",
    "Prediction",
    "RunRecord",
    "TestDescriptor",
    "TruthDefect",
    "is_scored_placement",
    "load_manifest",
    "match_findings",
    "aggregate",
    "wilson_interval",
    "verify_descriptor_bytes",
]
