"""The backtest must not hold a DuckDB connection while scoring (the anchor opens its own)."""
from __future__ import annotations

from types import SimpleNamespace

import dyor.backtest as bt


class _Con:
    def __init__(self, log):
        self.log = log
        self.open = True

    def close(self):
        self.open = False
        self.log.append("close")


def test_connection_is_read_only_and_closed_before_scoring(monkeypatch):
    log: list[str] = []
    con_holder: dict[str, _Con] = {}

    def fake_connect(read_only=False):
        log.append(f"connect(read_only={read_only})")
        con_holder["con"] = _Con(log)
        return con_holder["con"]

    recs = [{"token": "aave", "_market": {"price": 100.0}}, {"token": "uniswap", "_market": {"price": 5.0}}]
    fake_db = SimpleNamespace(connect=fake_connect, runs=lambda con: [("run-1", "t"), ("run-2", "t")],
                              records_for_run=lambda con, run_id: recs)
    monkeypatch.setattr("dyor.store.db.connect", fake_db.connect)
    monkeypatch.setattr("dyor.store.db.runs", fake_db.runs)
    monkeypatch.setattr("dyor.store.db.records_for_run", fake_db.records_for_run)

    def fake_score(records, config):
        assert con_holder["con"].open is False, "scoring started while the database connection was still open"
        log.append("score")
        return [SimpleNamespace(token=r["token"], final_score=50.0, tier="B (qualified)") for r in records]
    monkeypatch.setattr("dyor.pipeline.score_universe", fake_score)

    samples, version = bt._load_samples(None)
    assert log[0] == "connect(read_only=True)"
    assert log.index("close") < log.index("score")
    assert len(samples) == 4 and version == "run-1,run-2"
    assert samples[0] == ("B", "aave", 100.0)


def test_backtest_uses_cache_within_ttl(monkeypatch):
    bt._CACHE.clear()
    calls = {"n": 0}

    def fake_load(config):
        calls["n"] += 1
        return [("A", "aave", 100.0)], "run-1"

    class _CG:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def markets(self, tokens): return [{"id": t, "current_price": 110.0} for t in tokens]

    monkeypatch.setattr(bt, "_load_samples", fake_load)
    monkeypatch.setattr("dyor.ingestion.coingecko.CoinGeckoClient", _CG)
    first = bt.backtest(None, use_cache=True)
    second = bt.backtest(None, use_cache=True)
    assert calls["n"] == 1 and second is first
    assert first["by_tier"]["A"]["avg_return"] == 0.1 and first["by_tier"]["A"]["win_rate"] == 1.0
    bt._CACHE.clear()
