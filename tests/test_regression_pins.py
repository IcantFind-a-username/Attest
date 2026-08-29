"""Regression pins against the seed experiment record (attest-seed RESULTS.md).

Same seeds, same defaults, same iteration order as the validated prototype;
numbers are compared through the same f"{x:.3f}" formatting the record used.
Three pinned families (per handoff): null-validity table, theoretical LR
ceiling, gamma=0.99 redundancy stop-buying. Plus gamma=0 efficiency spot rows
to pin the purchase-order path.
"""

import pytest

from attest.core.demo_compat import metrics, run, theo_max_lr
from attest.core.stream import make_stream


def _fmt(x: float, p: int = 3) -> str:
    if x != x:
        return "n/a"
    if x == float("inf"):
        return "inf"
    return f"{x:.{p}f}"


@pytest.mark.regression
@pytest.mark.parametrize("gamma", [0.0, 0.5, 0.9, 0.99])
def test_null_validity_zero_false_certs(gamma: float) -> None:
    """RESULTS §1: all accuracies 0.5 — zero certifications, zero false certs,
    for both the adaptive engine and the uniform all-buy stress test."""
    stream = make_stream(0.5, 0.5, 0.5, gamma, seed=2000 + int(gamma * 100))
    me = metrics(*run(stream, "engine", 0.05))
    mu = metrics(*run(stream, "uniform", 0.05))
    assert me["cert_rate"] == 0.0
    assert me["false_cert_rate"] == 0.0
    assert mu["cert_rate"] == 0.0
    assert mu["false_cert_rate"] == 0.0


@pytest.mark.regression
@pytest.mark.parametrize(
    ("gamma", "full", "ac"),
    [
        (0.0, "28.00", "9.33"),
        (0.3, "18.59", "10.04"),
        (0.6, "14.67", "10.81"),
        (0.9, "12.52", "11.69"),
        (0.99, "12.05", "11.97"),
    ],
)
def test_theoretical_lr_ceiling(gamma: float, full: str, ac: str) -> None:
    """RESULTS §2: exact best-case LR with true parameters. Once gamma >= 0.3
    the whole pool cannot reach LR 20 — an honest engine must defer."""
    f, a = theo_max_lr(gamma)
    assert _fmt(f, 2) == full
    assert _fmt(a, 2) == ac


@pytest.mark.regression
def test_gamma099_redundancy_stop_buying() -> None:
    """RESULTS §3 row gamma=0.99: the price-aware engine stops buying the
    redundant expensive twin (B spend share 0.006) and keeps the cheap clone;
    the price-blind variant drops the clone instead. Learned agreement 0.988."""
    stream = make_stream(0.8, 0.75, 0.7, 0.99, seed=1000 + int(0.99 * 100))
    e = metrics(*run(stream, "engine", 0.05))
    p = metrics(*run(stream, "priceblind", 0.05))
    assert _fmt(e["share_a"]) == "0.864"
    assert _fmt(e["share_b"]) == "0.006"
    assert _fmt(e["share_c"]) == "0.130"
    assert _fmt(e["agree_bc"]) == "0.988"
    assert _fmt(e["avg_cost"], 2) == "1.28"
    assert _fmt(p["share_a"]) == "0.666"
    assert _fmt(p["share_b"]) == "0.333"
    assert _fmt(p["share_c"]) == "0.001"


@pytest.mark.regression
def test_gamma0_efficiency_rows() -> None:
    """RESULTS §4a gamma=0 rows: pins the canonical, purchase-order, and
    uniform paths end to end (cert rate / accuracy / avg cost)."""
    stream = make_stream(0.8, 0.75, 0.7, 0.0, seed=1000)
    e = metrics(*run(stream, "engine", 0.05))
    po = metrics(*run(stream, "engine_po", 0.05))
    u = metrics(*run(stream, "uniform", 0.05))
    assert _fmt(e["cert_rate"]) == "0.251"
    assert _fmt(e["cert_acc"]) == "0.962"
    assert _fmt(e["avg_cost"], 2) == "1.63"
    assert _fmt(po["cert_rate"]) == "0.411"
    assert _fmt(po["cert_acc"]) == "0.959"
    assert _fmt(po["avg_cost"], 2) == "1.56"
    assert _fmt(u["cert_rate"]) == "0.360"
    assert _fmt(u["cert_acc"]) == "0.956"
    assert _fmt(u["avg_cost"], 2) == "1.65"
