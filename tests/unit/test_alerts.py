from dyor import alerts


def _r(token, score, tier, flags=()):
    return {"token": token, "final_score": score, "tier": tier, "flags": list(flags)}


def test_score_change_drop_and_rise():
    prev = [_r("a", 0.70, "B — qualified"), _r("b", 0.40, "C — watchlist")]
    curr = [_r("a", 0.55, "C — watchlist"), _r("b", 0.60, "B — qualified")]
    found = {al.kind: al for al in alerts.score_change_alerts(prev, curr, drop=0.1, rise=0.15)}
    assert "score_drop" in found and found["score_drop"].subject == "a"
    assert "score_rise" in found and found["score_rise"].subject == "b"


def test_tier_change_direction_severity():
    prev = [_r("a", 0.7, "B — qualified")]
    curr = [_r("a", 0.3, "D — avoid")]
    al = alerts.tier_change_alerts(prev, curr)[0]
    assert al.kind == "tier_change" and al.severity == "warn"  # B → D is worse


def test_new_flag_is_critical():
    prev = [_r("a", 0.7, "B", [])]
    curr = [_r("a", 0.0, "D", ["dead_token"])]
    al = alerts.new_flag_alerts(prev, curr)[0]
    assert al.kind == "new_flag" and al.severity == "critical" and "dead_token" in al.message


def test_new_flag_not_refired_when_already_present():
    prev = [_r("a", 0.0, "D", ["dead_token"])]
    curr = [_r("a", 0.0, "D", ["dead_token"])]
    assert alerts.new_flag_alerts(prev, curr) == []


def test_unlock_and_narrative_thresholds():
    recs = [{"token": "x", "unlock_overhang": 0.8}, {"token": "y", "unlock_overhang": 0.2}]
    ua = alerts.unlock_alerts(recs, threshold=0.5)
    assert len(ua) == 1 and ua[0].subject == "x"

    cats = [{"name": "AI", "change_24h": 18.0}, {"name": "RWA", "change_24h": 3.0}]
    na = alerts.narrative_alerts(cats, threshold=10.0)
    assert len(na) == 1 and na[0].subject == "AI"


def test_evaluate_sorts_critical_first():
    prev = [_r("a", 0.7, "B", [])]
    curr = [_r("a", 0.5, "C", ["no_audit"])]  # both a new_flag (critical) and score_drop (warn)
    found = alerts.evaluate(prev, curr)
    assert found[0].severity == "critical"
    assert {a.kind for a in found} >= {"new_flag", "score_drop", "tier_change"}


def test_format_empty():
    assert alerts.format_alerts([]) == "no alerts"


class _CountingConn:
    """Proxy so we can observe when the DuckDB connection is actually open
    (the real object's `close` is read-only and can't be patched)."""

    def __init__(self, con, state):
        self._con, self._state = con, state
        state["open"] += 1
        state["peak"] = max(state["peak"], state["open"])

    def __getattr__(self, name):
        return getattr(self._con, name)

    def close(self):
        self._state["open"] -= 1
        self._con.close()


def _refresh_env(monkeypatch, tmp_path, records):
    """Point db.connect at a temp store and stub the collector; returns the
    connection-state dict so a test can assert on lock lifetime."""
    import duckdb

    from dyor.store import db
    from dyor.store.db import _SCHEMA

    state = {"open": 0, "peak": 0, "peak_during_collect": 0}

    def fake_connect(path=None):
        con = duckdb.connect(str(tmp_path / "t.duckdb"))
        con.execute(_SCHEMA)
        return _CountingConn(con, state)

    monkeypatch.setattr(db, "connect", fake_connect)

    class FakeCollector:
        errors: list = []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def collect(self, targets=None):
            state["peak_during_collect"] = max(state["peak_during_collect"], state["open"])
            return list(records)

    monkeypatch.setattr("dyor.collect.Collector", FakeCollector)
    return state


def test_refresh_does_not_hold_db_lock_during_collect(monkeypatch, tmp_path):
    """DuckDB is single-writer ACROSS PROCESSES: refresh must not keep a
    connection open while collecting, or the API is locked out for the whole
    run (screener 500s, analyze silently loses its peer set)."""
    import argparse

    from dyor import cli

    state = _refresh_env(
        monkeypatch, tmp_path, [{"token": "aave", "_class": "defi", "float_ratio": 0.9}]
    )
    assert cli._cmd_refresh(argparse.Namespace(top_n=None, category=None, no_narratives=True)) == 0
    assert state["peak_during_collect"] == 0   # no lock held across the collect
    assert state["open"] == 0                  # and nothing leaked


def test_refresh_refuses_to_persist_an_empty_collect(monkeypatch, tmp_path):
    """An empty collect is a failure — persisting it would make an empty run the
    latest one and blank the screener."""
    import argparse

    from dyor import cli
    from dyor.store import db

    _refresh_env(monkeypatch, tmp_path, [])
    assert cli._cmd_refresh(argparse.Namespace(top_n=None, category=None, no_narratives=True)) == 1
    con = db.connect()
    try:
        assert db.latest_records(con) == []
    finally:
        con.close()
