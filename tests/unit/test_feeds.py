"""A feed outage must not change a token's score or be quotable as if normal
(2026-09-30: Ethereum read 76 (B) live against 52 (C) on the board while
Santiment was over budget, and an agent tweeted the domain scores ×100 with the
DeFi default weights for an L1)."""

from __future__ import annotations

import pytest

from dyor import feeds
from dyor.api.serialize import analysis_summary, analyze_to_dict, class_to_dict, score_to_dict
from dyor.classes import FEATURE_SPECS
from dyor.pipeline import score_universe


def _rec(token, **over):
    base = {"token": token, "_class": "l1", "float_ratio": 0.9, "fdv_mcap_ratio": 1.1,
            "social_sentiment": 0.8, "watchlist_users": 1000, "mc_tvl": 5.0, "price_to_fees": 30.0,
            "address_growth": 0.1, "dev_activity": 40.0, "dev_activity_events": 3600.0,
            "days_since_last_commit": 1.0,
            "_feeds": {"coingecko": "ok", "defillama": "ok", "santiment": "ok", "github": "ok",
                       "ethplorer": "off", "sourcify": "off", "cryptorank": "off"},
            "_inputs": {"santiment": {"window_days": 90, "dev_activity": {"n": 90, "events": 3600.0}},
                        "last_push": "2026-09-26T00:00:00Z"}}
    base.update(over)
    return base


def test_feature_source_is_derived_from_feed_fields():
    for feature, feed in feeds.FEATURE_SOURCE.items():
        assert feature in feeds.FEED_FIELDS[feed]
    assert feeds.FEATURE_SOURCE["dev_activity"] == "santiment" and feeds.FEATURE_SOURCE["mc_tvl"] == "defillama"


def test_carry_forward_copies_only_the_failed_feed_and_marks_it_stale():
    stored = _rec("eth")
    live = _rec("eth", address_growth=None, dev_activity=None, dev_activity_events=None,
                mc_tvl=7.0, _inputs={}, _feeds={**stored["_feeds"], "santiment": "error"})
    carried = feeds.carry_forward(live, stored, "2026-09-27 03:25:42")
    assert carried == ["santiment"]
    assert live["address_growth"] == 0.1 and live["dev_activity"] == 40.0 and live["dev_activity_events"] == 3600.0
    assert live["mc_tvl"] == 7.0                                   # a live value is never overwritten
    assert live["_feeds"]["santiment"] == "stale" and live["_stale"] == {"santiment": "2026-09-27 03:25:42"}
    assert live["_inputs"]["santiment"]["dev_activity"]["events"] == 3600.0   # the ledger's raw figures too
    assert "last_push" not in live["_inputs"]                               # github was fine live


def test_carry_forward_skips_empty_off_and_feeds_the_store_lacks():
    stored = _rec("x", _feeds={"santiment": "empty", "github": "ok", "defillama": "error"})
    live = _rec("x", address_growth=None, _feeds={"santiment": "error", "github": "error", "defillama": "error"})
    live["days_since_last_commit"] = None
    assert feeds.carry_forward(live, stored, None) == ["github"]     # only a feed the store had `ok`
    assert live["days_since_last_commit"] == 1.0 and live["address_growth"] is None
    assert live["_feeds"] == {"santiment": "error", "github": "stale", "defillama": "error"}
    assert feeds.carry_forward(_rec("y"), None, None) == []          # nothing stored → nothing carried


def test_carry_forward_from_an_already_carried_row_keeps_the_original_date():
    """During an outage the first live analysis carries and is persisted as
    `stale`; the second must carry from THAT row (not find no `ok` row and drop
    the domains) and keep the date the values were really collected."""
    first = _rec("eth", _feeds={**_rec("eth")["_feeds"], "santiment": "stale"},
                 _stale={"santiment": "2026-09-27 03:25:42"})
    second = _rec("eth", address_growth=None, dev_activity=None, dev_activity_events=None, _inputs={},
                  _feeds={**_rec("eth")["_feeds"], "santiment": "error"})
    assert feeds.carry_forward(second, first, "2026-09-30 11:40:00") == ["santiment"]
    assert second["address_growth"] == 0.1 and second["_feeds"]["santiment"] == "stale"
    assert second["_stale"] == {"santiment": "2026-09-27 03:25:42"}      # original, not the persist time


def test_domains_for_feeds():
    assert feeds.domains_for_feeds(["santiment"], FEATURE_SPECS["l1"]) == ["onchain", "social", "dev"]  # social_trend too
    assert feeds.domains_for_feeds(["defillama"], FEATURE_SPECS["meme"]) == []


def test_failed_feed_is_an_advisory_and_carried_feed_is_dated(sample_config):
    errored = _rec("a", address_growth=None, dev_activity=None, _feeds={**_rec("a")["_feeds"], "santiment": "error"})
    carried = _rec("b", _stale={"santiment": "2026-09-27 03:25:42"}, _feeds={**_rec("b")["_feeds"], "santiment": "stale"})
    fine = _rec("c")
    res = {r.token: r for r in score_universe([errored, carried, fine], sample_config, reference_anchored=False)}
    adv_a = " ".join(res["a"].advisories)
    assert "santiment feed failed this run" in adv_a and "on-chain, social, developer" in adv_a and "provisional" in adv_a
    adv_b = " ".join(res["b"].advisories)
    assert "carried from the last stored run" in adv_b and "santiment (stored 2026-09-27)" in adv_b
    assert not any("failed" in a or "carried" in a for a in res["c"].advisories)


def test_class_weights_are_per_class():
    assert class_to_dict("l1")["weights"]["fundamental"] == pytest.approx(0.18)
    assert class_to_dict("defi")["weights"]["fundamental"] == pytest.approx(0.30)
    assert "fundamental" not in class_to_dict("monetary")["weights"]
    assert sum(class_to_dict("meme")["weights"].values()) == pytest.approx(1.0)


def test_summary_states_scale_and_class_weights(sample_config):
    from types import SimpleNamespace

    rec = _rec("ethereum", _stale={"santiment": "2026-09-27"}, _feeds={**_rec("e")["_feeds"], "santiment": "stale"})
    peer = _rec("solana", float_ratio=0.5)
    ranked = score_universe([rec, peer], sample_config, reference_anchored=False)
    result = next(r for r in ranked if r.token == "ethereum")
    res = SimpleNamespace(query="eth", resolved=SimpleNamespace(name="Ethereum", symbol="ETH", gecko_id="ethereum",
                                                                  matched_by="id", market_cap_rank=2, chains=[], platforms={},
                                                                  explorer_links=lambda: {}, coingecko_url="", links={}),
                          record=rec, result=result, peer_count=1, errors=[], all_results=ranked,
                          rank=next(i + 1 for i, r in enumerate(ranked) if r.token == "ethereum"), ok=True)
    d = analyze_to_dict(res)
    assert d["scale"] == 100 and d["score"]["scale"] == 100 and d["record"]["class"]["weights"]["fundamental"] == pytest.approx(0.18)
    s = d["summary"]
    assert f"score {d['score']['final_score']}/100" in s and "tier" in s
    assert "fundamentals" in s and "(weight 18%)" in s and "(weight 25%)" in s     # the L1 weights, not 30%
    assert "santiment stale" in s and "All figures are already on a 0–100 scale" in s
    assert d["record"]["stale"] == {"santiment": "2026-09-27"}
    # the domain figures quoted are the 0–100 ones, never ×100
    for v in d["score"]["domain_scores"].values():
        if v is not None:
            assert 0 <= v <= 100
    assert analysis_summary(res, score_to_dict(result), d["record"], None).endswith("do not rescale.")


def test_mcp_instructions_and_methodology_state_the_scale():
    from dyor import mcp_server

    assert "0–100" in mcp_server.INSTRUCTIONS and "never multiply" in mcp_server.INSTRUCTIONS
    m = mcp_server.methodology()
    assert m["scale"] == 100 and m["class_weights"]["l1"]["fundamental"] == pytest.approx(0.18)
    assert m["tiers"][0]["min"] in (80, 80.0)
