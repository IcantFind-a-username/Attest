"""Behavioral tests for the default engine (po_calib): purchase-order betting
with tables learned only from the all-buy exploration slice.

Exact values are deterministic (fixed stream + engine seeds) and were observed
from the implementation, then frozen; the bound assertions are the properties
that actually matter (validity, accuracy, redundancy discount).
"""

import pytest

from attest.core import Engine, EngineConfig, make_stream
from attest.core.engine import summarize


def _run(
    acc: tuple[float, float, float],
    gamma: float,
    alpha: float,
    seed_stream: int,
    seed_engine: int = 7,
    variant: str = "po_calib",
):
    stream = make_stream(*acc, gamma, seed=seed_stream, n=2000, warmup=0)
    eng = Engine(EngineConfig(alpha=alpha, seed=seed_engine, variant=variant))
    results = eng.run_stream(stream)
    return eng, results, summarize(results)


NULL = (0.5, 0.5, 0.5)
INFO = (0.8, 0.75, 0.7)


def test_null_validity_alpha_010() -> None:
    _, _, s = _run(NULL, 0.0, 0.1, seed_stream=2000)
    assert s["false_cert_rate"] <= 0.1  # the e-process guarantee, with margin:
    assert s["false_cert_rate"] == pytest.approx(0.0005)
    assert s["cert_rate"] == pytest.approx(0.0010)


def test_null_validity_alpha_010_with_clone() -> None:
    _, _, s = _run(NULL, 0.9, 0.1, seed_stream=2090)
    assert s["false_cert_rate"] <= 0.1
    assert s["false_cert_rate"] == pytest.approx(0.0095)


@pytest.mark.parametrize(("gamma", "seed"), [(0.0, 2000), (0.9, 2090)])
def test_null_validity_alpha_005_zero_certs(gamma: float, seed: int) -> None:
    _, _, s = _run(NULL, gamma, 0.05, seed_stream=seed)
    assert s["cert_rate"] == 0.0
    assert s["false_cert_rate"] == 0.0


def test_informative_certifies_accurately() -> None:
    _, _, s = _run(INFO, 0.0, 0.1, seed_stream=1000)
    assert s["cert_rate"] == pytest.approx(0.2610)
    assert s["cert_acc"] == pytest.approx(0.9272, abs=1e-3)
    assert s["cert_acc"] >= 0.9
    assert s["false_cert_rate"] < 0.1


def test_redundancy_discount_cuts_cost() -> None:
    # gamma=0.99: C clones B; uniform all-buy would cost 1.65/task
    _, _, s = _run(INFO, 0.99, 0.1, seed_stream=1099)
    assert s["avg_cost"] < 1.5
    assert s["cert_acc"] >= 0.9


def test_deterministic_given_seeds() -> None:
    _, _, a = _run(INFO, 0.0, 0.1, seed_stream=1000, seed_engine=5)
    _, _, b = _run(INFO, 0.0, 0.1, seed_stream=1000, seed_engine=5)
    assert a == b


def test_calibration_slice_is_the_only_table_source() -> None:
    eng, results, s = _run(INFO, 0.0, 0.1, seed_stream=1000)
    explored = sum(1 for _, r in results if r.explored)
    # full update on every explore task: each judge's marginal gains exactly one
    # count per explore task, and nothing else ever updates the tables
    for j in ("A", "B", "C"):
        assert eng.tables.marg[j].sum() == explored
    assert eng.tables.trip is not None
    assert eng.tables.trip.sum() == explored


def test_adaptive_variant_learns_from_every_task() -> None:
    eng, results, _ = _run(INFO, 0.0, 0.1, seed_stream=1000, variant="po_adaptive")
    n_purchases = sum(len(r.order) for _, r in results)
    total_counts = (
        sum(t.sum() for t in eng.tables.marg.values())
        + sum(t.sum() for t in eng.tables.pair.values())
        + (eng.tables.trip.sum() if eng.tables.trip is not None else 0)
    )
    # usage-matched: exactly one table cell increments per purchase
    assert total_counts == n_purchases


def test_canonical_variant_runs() -> None:
    _, _, s = _run(INFO, 0.0, 0.1, seed_stream=1000, variant="canonical")
    assert s["cert_rate"] > 0.0
    assert s["false_cert_rate"] < 0.1


def test_monitor_records_purchases() -> None:
    eng, results, _ = _run(INFO, 0.0, 0.1, seed_stream=1000)
    n_purchases = sum(len(r.order) for _, r in results)
    assert len(eng.monitor._buf) == min(n_purchases, eng.monitor.window)
    assert isinstance(eng.monitor.alarms(), list)


def test_no_spurious_optimism_alarms_on_healthy_run() -> None:
    """Regression (D-012): estimates are signed expected log-e, commensurable
    with realized log LR — a healthy engine must not alarm."""
    for gamma, seed in [(0.0, 1000), (0.99, 1099)]:
        eng, _, _ = _run(INFO, gamma, 0.1, seed_stream=seed)
        kinds = [a["kind"] for a in eng.monitor.alarms()]
        assert "winners_curse_optimism" not in kinds, (gamma, kinds)


def test_exploration_cools_when_marginals_fill() -> None:
    """Regression (D-003 revised): the hot->cold transition must actually
    happen — under the null the marginal cells fill fast and eps drops."""
    eng, results, s = _run(NULL, 0.0, 0.1, seed_stream=2000)
    assert eng.tables.min_marginal_count() >= eng.config.cell_target
    assert s["explore_rate"] < 0.095  # below pure-hot ~0.10: cooling occurred


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        EngineConfig(variant="nope")
    with pytest.raises(ValueError):
        EngineConfig(alpha=0.0)
    with pytest.raises(ValueError):
        EngineConfig(judges=("A", "B", "C", "D"))  # D has no price
    with pytest.raises(ValueError):  # 4 judges rejected even when all priced
        EngineConfig(judges=("A", "B", "C", "D"), prices=dict.fromkeys("ABCD", 1.0))
    with pytest.raises(ValueError):
        EngineConfig(judges=())
    with pytest.raises(ValueError):  # dogfood finding: zero price divides VOI
        EngineConfig(prices={"A": 1.0, "B": 0.5, "C": 0.0})
    with pytest.raises(ValueError):  # dogfood finding: zero smoothing -> NaN
        EngineConfig(smoothing=0.0)


def test_task_result_shape() -> None:
    stream = make_stream(*INFO, 0.0, seed=1000, n=5, warmup=0)
    eng = Engine(EngineConfig(seed=7))
    res = eng.review_task(lambda j: int(stream.verdicts[j][0]))
    assert res.decision in (0, 1, None)
    assert set(res.order) == set(res.verdicts)
    assert res.wealth > 0
    for j, cost in res.spend.items():
        assert cost == eng.config.prices[j]
