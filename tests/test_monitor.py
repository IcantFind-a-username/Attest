from attest.core import WinnersCurseMonitor


def test_no_alarm_when_healthy() -> None:
    m = WinnersCurseMonitor()
    for _ in range(100):
        m.record("A", 0.2, 0.2, 1.0)
        m.record("B", 0.1, 0.12, 0.5)
    assert m.alarms() == []


def test_optimism_alarm_fires() -> None:
    m = WinnersCurseMonitor()
    for _ in range(40):
        m.record("B", estimated_log_e=0.5, realized_log_e=0.1, spend=0.5)
    alarms = m.alarms()
    kinds = {a["kind"] for a in alarms}
    assert "winners_curse_optimism" in kinds
    opt = next(a for a in alarms if a["kind"] == "winners_curse_optimism")
    assert opt["judge"] == "B"
    assert opt["mean_realized_minus_estimated"] < -0.15


def test_optimism_needs_min_samples() -> None:
    m = WinnersCurseMonitor()
    for _ in range(29):
        m.record("B", 0.5, 0.1, 0.5)
    assert m.alarms() == []


def test_spend_share_drift_alarm() -> None:
    m = WinnersCurseMonitor(window=200)
    # first half: A dominates spend; second half: B dominates
    for _ in range(100):
        m.record("A", 0.1, 0.1, 1.0)
    for _ in range(100):
        m.record("B", 0.1, 0.1, 1.0)
    kinds = [a["kind"] for a in m.alarms()]
    assert kinds.count("spend_share_drift") == 2  # A down, B up


def test_window_trims_old_records() -> None:
    m = WinnersCurseMonitor(window=50)
    for _ in range(40):
        m.record("B", 0.5, 0.1, 0.5)  # pessimistic gap, would alarm at n>=30
    for _ in range(50):
        m.record("B", 0.2, 0.2, 0.5)  # healthy records push the bad ones out
    assert all(a["kind"] != "winners_curse_optimism" for a in m.alarms())


def test_no_intervention_interface() -> None:
    # the monitor exposes only record/alarms: nothing that could mutate the
    # engine's purchasing behavior (MVP scope: alarm to ledger only)
    public = [n for n in dir(WinnersCurseMonitor) if not n.startswith("_")]
    assert sorted(public) == [
        "alarms",
        "drift_threshold",
        "min_samples",
        "optimism_threshold",
        "record",
        "window",
    ]
