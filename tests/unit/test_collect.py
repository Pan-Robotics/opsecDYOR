"""Unit tests for the pure half of the ingest-to-score path (`build_record`).

No network: feeds raw-shaped API dicts in, asserts computed metric records out.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from dyor.collect import (
    annualized,
    build_record,
    days_since,
    parse_unlock,
    same_window_pair,
)

MARKET = {
    "id": "aave",
    "market_cap": 1_000_000_000,
    "circulating_supply": 15_000_000,
    "total_supply": 16_000_000,
    "max_supply": 16_000_000,
    "total_volume": 200_000_000,
    "fully_diluted_valuation": 1_066_666_667,
    "ath_change_percentage": -40.0,
}


def test_annualized_prefers_total1y():
    assert annualized({"total1y": 100, "total30d": 1}) == 100


def test_annualized_scales_shorter_window():
    assert annualized({"total7d": 7}) == pytest.approx(7 * 365 / 7)


def test_annualized_missing_is_none():
    assert annualized(None) is None
    assert annualized({}) is None
    assert annualized({"total1y": 0}) is None  # zero is not usable


def test_annualized_handles_list_response():
    # DefiLlama returns [] for a dataType a protocol doesn't have — must not raise
    assert annualized([]) is None
    assert same_window_pair([], {"total1y": 10}) == (None, None)


def test_build_record_fundamentals():
    rec = build_record(
        "aave", MARKET,
        fees={"total1y": 100_000_000},      # P/F = 1e9 / 1e8 = 10
        revenue={"total30d": 5_000_000},
        holders_revenue={"total7d": 1_000_000},
        tvl=500_000_000,                     # MC/TVL = 2.0
    )
    assert rec["token"] == "aave"
    assert rec["price_to_fees"] == pytest.approx(10.0)
    assert rec["mc_tvl"] == pytest.approx(2.0)
    # P/S = 1e9 / (5e6 * 365/30)
    assert rec["price_to_sales"] == pytest.approx(1e9 / (5_000_000 * 365 / 30))
    # real yield = annualized holders (1e6 * 365/7) / mc
    assert rec["real_yield"] == pytest.approx((1_000_000 * 365 / 7) / 1e9)


def test_build_record_tokenomics_and_gate_inputs():
    rec = build_record("aave", MARKET)
    assert rec["fdv_mcap_ratio"] == pytest.approx(16_000_000 / 15_000_000)
    assert rec["float_ratio"] == pytest.approx(15_000_000 / 16_000_000)
    assert rec["daily_volume_usd"] == 200_000_000
    assert rec["drawdown_from_ath_pct"] == pytest.approx(40.0)


def test_build_record_missing_defi_data_is_none():
    rec = build_record("aave", MARKET)  # no fees/revenue/tvl
    assert rec["price_to_fees"] is None
    assert rec["price_to_sales"] is None
    assert rec["mc_tvl"] is None


def test_build_record_drawdown_clamped_at_ath():
    rec = build_record("x", {**MARKET, "ath_change_percentage": 0.0})
    assert rec["drawdown_from_ath_pct"] == 0.0


def test_build_record_value_accrual_and_dev():
    rec = build_record(
        "aave", MARKET,
        revenue={"total1y": 10_000_000},
        holders_revenue={"total1y": 3_000_000},   # 30% of revenue → token sink
        last_push_iso=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    )
    assert rec["value_accrual"] == pytest.approx(0.30)
    assert rec["days_since_last_commit"] == pytest.approx(2.0, abs=0.1)


def test_build_record_santiment_signals_passthrough():
    rec = build_record(
        "aave", MARKET,
        address_growth=0.12, dev_commit_trend=0.4, social_trend=-0.2,
    )
    assert rec["address_growth"] == 0.12
    assert rec["dev_commit_trend"] == 0.4
    assert rec["social_trend"] == -0.2


def test_build_record_santiment_signals_default_none():
    rec = build_record("aave", MARKET)
    assert rec["address_growth"] is None
    assert rec["dev_commit_trend"] is None
    assert rec["social_trend"] is None


def test_build_record_overhang_and_concentration_passthrough():
    rec = build_record("aave", MARKET, unlock_overhang=0.78, top10_concentration=0.34)
    assert rec["unlock_overhang"] == 0.78
    assert rec["top10_concentration"] == 0.34


def test_holder_concentration_from_shares():
    from dyor.collect import holder_concentration

    holders = [{"share": 13.5}, {"share": 8.0}, {"share": 4.0}, {"share": 1.0}]
    # top-2 shares (13.5 + 8.0) / 100 = 0.215
    assert holder_concentration(holders, n=2) == pytest.approx(0.215)
    assert holder_concentration([], n=10) is None
    assert holder_concentration(None) is None


def test_build_record_contract_verified_passthrough():
    rec = build_record("aave", MARKET, contract_verified=True)
    assert rec["contract_verified"] is True
    assert build_record("aave", MARKET)["contract_verified"] is None


def test_is_not_found_classification():
    import httpx

    from dyor.collect import _is_not_found

    def http_error(code):
        req = httpx.Request("GET", "https://x")
        return httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, request=req))

    assert _is_not_found(http_error(404)) is True
    assert _is_not_found(http_error(400)) is True          # DefiLlama unavailable dataType
    assert _is_not_found(http_error(500)) is False         # real server error
    assert _is_not_found(RuntimeError('slug "joule-2" is not an existing slug')) is True
    assert _is_not_found(RuntimeError("failed after 5 attempts")) is False  # exhausted retries


def test_feed_status_states():
    from dyor.collect import _feed_status

    assert _feed_status(False, None, False) == "off"        # not configured
    assert _feed_status(True, None, True) == "error"        # configured + failed
    assert _feed_status(True, None, False) == "empty"       # configured, no data
    assert _feed_status(True, [1, 2], False) == "ok"        # configured, has data
    assert _feed_status(True, [], False) == "empty"         # empty list = no data


def test_vc_backing_extracts_facts():
    from dyor.collect import vc_backing

    coin = {"fundIds": [22, 41, 58], "crowdsales": [{"type": "ICO"}]}
    assert vc_backing(coin) == {"num_backers": 3, "had_public_sale": True}
    assert vc_backing({"fundIds": [], "crowdsales": []}) == {"num_backers": 0, "had_public_sale": False}
    assert vc_backing(None) == {}


def test_build_record_market_snapshot():
    rec = build_record("aave", {**MARKET, "current_price": 75.5,
                                "price_change_percentage_24h": -2.0})
    m = rec["_market"]
    assert m["price"] == 75.5
    assert m["market_cap"] == MARKET["market_cap"]
    assert m["fdv"] == MARKET["fully_diluted_valuation"]
    assert m["volume_24h"] == MARKET["total_volume"]
    assert m["price_change_24h_pct"] == -2.0
    # _market is informational — must not count toward scored-feature coverage
    from dyor.pipeline import FEATURE_SPEC
    all_feats = [f for feats in FEATURE_SPEC.values() for f, _ in feats]
    assert "_market" not in all_feats


def test_build_record_social_sentiment_and_vc():
    rec = build_record(
        "aave", MARKET,
        social_sentiment=0.92, vc={"num_backers": 6, "had_public_sale": True},
    )
    assert rec["social_sentiment"] == 0.92
    assert rec["num_vc_backers"] == 6
    assert rec["had_public_sale"] is True


def test_same_window_pair_matches_window():
    # both have total1y → use it, ignore the mismatched total30d
    assert same_window_pair({"total1y": 3, "total30d": 99}, {"total1y": 10}) == (3, 10)


def test_same_window_pair_skips_window_missing_denominator():
    # denominator lacks total1y but has total30d → pair on total30d
    num = {"total1y": 5, "total30d": 2}
    den = {"total30d": 8}
    assert same_window_pair(num, den) == (2, 8)


def test_same_window_pair_none_when_no_shared_window():
    assert same_window_pair({"total24h": 1}, {"total1y": 10}) == (None, None)
    assert same_window_pair(None, {"total1y": 10}) == (None, None)


def test_value_accrual_uses_same_window_not_independent_annualization():
    # revenue only reports total1y; holders only reports total30d → no shared
    # window → value_accrual must be None, NOT a distorted cross-window ratio.
    rec = build_record(
        "x", MARKET,
        revenue={"total1y": 12_000_000},
        holders_revenue={"total30d": 1_000_000},
    )
    assert rec["value_accrual"] is None


def test_days_since_none_safe():
    assert days_since(None) is None
    assert days_since((datetime.now(timezone.utc) - timedelta(days=10)).isoformat()) == pytest.approx(10, abs=0.1)


def test_days_since_handles_z_suffix():
    iso = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert days_since(iso) == pytest.approx(5, abs=0.2)


def test_parse_unlock_tolerant_of_unknown_shapes():
    assert parse_unlock(None, MARKET) == {}
    assert parse_unlock({}, MARKET) == {}
    assert parse_unlock({"events": []}, MARKET) == {}


def test_parse_unlock_extracts_next_future_event():
    future = datetime.now(timezone.utc).timestamp() + 86400  # tomorrow
    past = datetime.now(timezone.utc).timestamp() - 86400
    market = {**MARKET, "current_price": 100.0, "circulating_supply": 1_000_000}
    out = parse_unlock(
        {"events": [
            {"timestamp": past, "amount": 999},       # ignored (past)
            {"timestamp": future, "amount": 5_000},   # the next unlock
        ]},
        market,
    )
    assert out["next_unlock_usd"] == pytest.approx(500_000)       # 5000 * $100
    assert out["pct_of_supply"] == pytest.approx(0.005)           # 5000 / 1e6


def test_record_is_scorable():
    # the produced record must flow through the pipeline without error
    from dyor.pipeline import score_universe

    rec = build_record("aave", MARKET, fees={"total1y": 1e8}, tvl=5e8)
    results = score_universe([rec, build_record("uni", {**MARKET, "id": "uni"})])
    assert len(results) == 2
    assert all(0.0 <= r.final_score <= 1.0 or math.isnan(r.final_score) for r in results)


def test_santiment_query_served_from_cache(tmp_path, monkeypatch, sample_config):
    """POSTs are cached on (url, query+variables) — the free tier is 1000
    calls/month, so a repeat query within TTL must not hit the network."""
    import httpx

    from dyor.ingestion import santiment as san_mod

    monkeypatch.setattr(san_mod, "PROJECT_ROOT", tmp_path)
    client = san_mod.SantimentClient(sample_config)
    calls = {"n": 0}

    def fake_post(url, json=None):
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"data": {"getMetric": {"timeseriesData": [{"datetime": "d", "value": 1}]}}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(client._client, "post", fake_post)
    first = client.query("{q}", {"slug": "aave"})
    second = client.query("{q}", {"slug": "aave"})
    client.close()
    assert first == second
    assert calls["n"] == 1


def test_santiment_slug_override_applied():
    """gecko_ids that Santiment tracks under a different slug are remapped
    (polkadot/aptos-class basket members were silently 'empty' before)."""
    from dyor.ingestion.santiment import SLUG_OVERRIDES

    assert SLUG_OVERRIDES["polkadot"] == "polkadot-new"
    assert SLUG_OVERRIDES["starknet"] == "starknet-token"


def test_santiment_caches_untracked_slug_misses(tmp_path, monkeypatch, sample_config):
    """~65% of our gecko_ids aren't Santiment slugs and each failed lookup still
    costs a call against the ~1000/month free tier. A known miss must not be
    re-queried."""
    import httpx

    from dyor.ingestion import santiment as san_mod

    monkeypatch.setattr(san_mod, "PROJECT_ROOT", tmp_path)
    client = san_mod.SantimentClient(sample_config)
    calls = {"n": 0}

    def fake_post(url, json=None):
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"errors": [{"message": 'Can\'t fetch daily_active_addresses for project '
                                         'with slug kpk, Reason: "The slug \\"kpk\\" is not '
                                         'an existing slug."'}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(client._client, "post", fake_post)
    assert client.daily_active_addresses("kpk", "2026-01-01", "2026-01-28") == []
    assert client.daily_active_addresses("kpk", "2026-02-01", "2026-02-28") == []
    client.close()
    assert calls["n"] == 1  # second lookup served from the miss cache


def test_santiment_does_not_cache_transient_failures(tmp_path, monkeypatch, sample_config):
    """Rate limits, quota exhaustion and subscription limits must stay loud —
    caching them would silently zero a feed for a month."""
    import httpx
    import pytest

    from dyor.ingestion import santiment as san_mod

    monkeypatch.setattr(san_mod, "PROJECT_ROOT", tmp_path)
    client = san_mod.SantimentClient(sample_config)

    def fake_post(url, json=None):
        return httpx.Response(
            200,
            json={"errors": [{"message": "API rate limit exceeded for your subscription"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(client._client, "post", fake_post)
    with pytest.raises(RuntimeError):
        client.daily_active_addresses("aave", "2026-01-01", "2026-01-28")
    with pytest.raises(RuntimeError):   # still raises, not cached away
        client.daily_active_addresses("aave", "2026-01-01", "2026-01-28")
    client.close()
