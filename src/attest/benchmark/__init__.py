"""Preregistered real-data benchmark records and scoring."""

from attest.benchmark.corpus import (
    CorpusRunner,
    RunOutcome,
    SubprocessCorpusRunner,
    import_bugsinpy,
    validate_corpus,
)
from attest.benchmark.matcher import MatchResult, match_findings
from attest.benchmark.metrics import BenchmarkReport, aggregate, wilson_interval
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    BenchmarkSource,
    CorpusExclusion,
    CorpusProvenance,
    PatchDescriptor,
    Placement,
    Prediction,
    RunRecord,
    RuntimeDescriptor,
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
    "BenchmarkSource",
    "CorpusExclusion",
    "CorpusProvenance",
    "CorpusRunner",
    "MatchResult",
    "PatchDescriptor",
    "Placement",
    "Prediction",
    "RunRecord",
    "RunOutcome",
    "RuntimeDescriptor",
    "SubprocessCorpusRunner",
    "TestDescriptor",
    "TruthDefect",
    "is_scored_placement",
    "import_bugsinpy",
    "load_manifest",
    "match_findings",
    "aggregate",
    "wilson_interval",
    "verify_descriptor_bytes",
    "validate_corpus",
]
