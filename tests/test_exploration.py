import numpy as np

from attest.core import ExplorationSchedule, Tables


def _filled_tables(count: int) -> Tables:
    t = Tables()
    for _ in range(count):
        for th in (0, 1):
            for va in (0, 1):
                for vb in (0, 1):
                    for vc in (0, 1):
                        t.update(th, {"A": va, "B": vb, "C": vc})
    return t


def test_rate_hot_until_cell_target() -> None:
    sched = ExplorationSchedule(eps_hot=0.10, eps_cold=0.02, cell_target=30)
    assert sched.rate(Tables()) == 0.10
    # pair cells gain 2 per full sweep: 14 sweeps -> 28 < 30 still hot
    assert sched.rate(_filled_tables(14)) == 0.10
    # 15 sweeps -> 30 >= 30 -> cold
    assert sched.rate(_filled_tables(15)) == 0.02


def test_should_explore_matches_rate() -> None:
    sched = ExplorationSchedule(eps_hot=1.0, eps_cold=0.0, cell_target=30)
    rng = np.random.default_rng(0)
    assert sched.should_explore(rng, Tables()) is True
    full = _filled_tables(15)
    assert sched.should_explore(rng, full) is False


def test_empirical_explore_frequency() -> None:
    sched = ExplorationSchedule(eps_hot=0.10, eps_cold=0.02, cell_target=30)
    rng = np.random.default_rng(42)
    t = Tables()
    hits = sum(sched.should_explore(rng, t) for _ in range(10000))
    assert 800 <= hits <= 1200  # ~10%
