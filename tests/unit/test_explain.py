"""The score ledger (dyor/explain.py), the raw inputs the collector keeps for
it, the per-feed source links, and the 0–100 display scale."""

from __future__ import annotations

import pytest

from dyor.api.serialize import score_to_dict
from dyor.collect import build_record, source_links
from dyor.explain import explain, feature_working, missing_reason
from dyor.pipeline import score_universe

MARKET = {"id": "x", "current_price": 2.0, "market_cap": 1e9, "fully_diluted_valuation": 1.5e9,
          "total_volume": 5e7, "circulating_supply": 5e8, "total_supply": 7.5e8, "max_supply": 7.5e8,
          "ath_change_percentage": -40.0}
SAN = {"window_days": 28, "slug": "x",
       "daily_active_addresses": {"n": 28, "k": 9, "early_mean": 100.0, "late_mean": 110.0, "growth": 0.1},
       "dev_activity": {"n": 28, "k": 9, "early_mean": 10.0, "late_mean": 12.0, "growth": 0.2},
       "social_volume": None}
FEEDS = {"coingecko": "ok", "defillama": "ok", "cryptorank": "off", "ethplorer": "ok",
         "sourcify": "ok", "santiment": "ok", "github": "ok"}


def _rec(token, *, mc=1e9, fees30=2e6, rev30=1e6, hold30=5e5, tvl=4e8, market=None):
    m = {**MARKET, **(market or {}), "id": token, "market_cap": mc}
    rec = build_record(
        token, m, fees={"total30d": fees30}, revenue={"total30d": rev30},
        holders_revenue={"total30d": hold30}, tvl=tvl,
        address_growth=0.1, dev_commit_trend=0.2, dev_activity_events=50.0, santiment_detail=SAN,
        top10_concentration=0.3, top10_shares=[10.0, 8.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.3, 0.1, 0.1],
        social_sentiment=0.7, sentiment_votes_up_pct=70.0, watchlist_users=1000,
        contract_verified=True, audited=True, github_account="x-labs",
        last_push_iso="2026-09-20T00:00:00Z",
    )
    rec["_class"] = "defi"
    rec["_feeds"] = dict(FEEDS)
    return rec


@pytest.fixture
def scored(sample_config):
    recs = [_rec("a"), _rec("b", mc=3e9, fees30=1e6), _rec("c", mc=5e8, fees30=4e6, tvl=2e8)]
    results = {r.token: r for r in score_universe(recs, sample_config, reference_anchored=False)}
    return recs, results


# --- the collector keeps the working ------------------------------------------

def test_build_record_keeps_raw_inputs():
    rec = _rec("a")
    i = rec["_inputs"]
    assert i["fees"] == {"window": "total30d", "days": 30, "total": 2e6, "annualized": pytest.approx(2e6 * 365 / 30)}
    assert i["value_accrual_window"] == {"window": "total30d", "holders_revenue": 5e5, "revenue": 1e6}
    assert i["fdv_mcap_method"] == "supply" and i["market_cap"] == 1e9 and i["tvl"] == 4e8
    assert i["top10_shares_pct"][0] == 10.0 and i["santiment"]["dev_activity"]["k"] == 9
    assert i["github_account"] == "x-labs" and i["last_push"].startswith("2026-09-20")
    # informational only — the pipeline never sees `_inputs` as a feature
    assert not any(k.startswith("_") for k in score_to_dict.__globals__["FEATURE_DIRECTION"])


def test_source_links_per_feed():
    s = source_links("aave", defillama_slug="aave-v3", santiment_slug="aave", github_account="aave",
                     eth_contract="0xabc", verify_address="0xabc", cryptorank_key=None)
    assert s["coingecko"] == "https://www.coingecko.com/en/coins/aave"
    assert s["defillama"] == "https://defillama.com/protocol/aave-v3"
    assert s["santiment"] == "https://app.santiment.net/charts?slug=aave"
    assert s["github"] == "https://github.com/aave" and s["ethplorer"].endswith("/address/0xabc")
    assert s["sourcify"].endswith("/lookup/0xabc") and s["cryptorank"] is None
    # an L1 with no protocol slug links to its DefiLlama chain page; nothing → None
    assert source_links("solana", chain_name="Solana")["defillama"] == "https://defillama.com/chain/Solana"
    assert source_links("x")["defillama"] is None and source_links("x")["github"] is None


# --- the ledger -----------------------------------------------------------------

def test_feature_rows_carry_inputs_formula_value_percentile(scored, sample_config):
    recs, results = scored
    ex = explain(recs[0], results["a"], sample_config)
    rows = {f["feature"]: f for f in ex["features"]}
    pf = rows["price_to_fees"]
    assert pf["status"] == "scored" and pf["direction"] == "lower is better" and pf["source"] == "defillama"
    assert [i["key"] for i in pf["inputs"]] == ["market_cap", "fees_total", "fees_days"]
    assert pf["formula"] == "{market_cap} ÷ ({fees_total} × 365 ÷ {fees_days})"
    assert pf["value"] == pytest.approx(recs[0]["price_to_fees"]) and pf["unit"] == "x"
    assert 0.0 <= pf["percentile"] <= 100.0 and pf["weight"] > 0 and pf["contribution"] is not None
    # a growth feature shows the two window means it was reduced from
    ag = rows["address_growth"]
    assert ag["formula"] == "({daa_late} − {daa_early}) ÷ {daa_early}"
    assert {i["key"]: i["value"] for i in ag["inputs"]} == {"daa_early": 100.0, "daa_late": 110.0, "daa_window": 28}
    # the holder shares that were summed
    assert rows["top10_concentration"]["inputs"][0]["unit"] == "pct_list"
    # every feature of the class spec has a row, scored or not
    assert len(ex["features"]) == sum(len(v) for v in __import__("dyor.classes").classes.FEATURE_SPECS["defi"].values())


def test_contributions_add_up_to_the_score(scored, sample_config):
    recs, results = scored
    ex = explain(recs[0], results["a"], sample_config)
    feat_sum = sum(f["contribution"] or 0 for f in ex["features"])
    dom_sum = sum(d["contribution"] or 0 for d in ex["domains"])
    assert feat_sum == pytest.approx(ex["gate"]["raw_score"], abs=0.2)
    assert dom_sum == pytest.approx(ex["gate"]["raw_score"], abs=0.2)
    present = [d for d in ex["domains"] if d["weight_renormalized"] is not None]
    assert sum(d["weight_renormalized"] for d in present) == pytest.approx(1.0, abs=1e-3)
    # percentages of the composite add to ~100 across the scored features
    assert sum(f["weight"] or 0 for f in ex["features"]) == pytest.approx(100.0, abs=0.5)
    # no gate tripped → final == raw, cap None
    assert ex["gate"]["cap"] is None and ex["gate"]["final_score"] == ex["gate"]["raw_score"]


def test_missing_features_say_why(scored, sample_config):
    recs, results = scored
    ex = explain(recs[0], results["a"], sample_config)
    rows = {f["feature"]: f for f in ex["features"]}
    assert rows["unlock_overhang"]["status"] == "missing" and "CryptoRank Pro" in rows["unlock_overhang"]["missing_reason"]
    assert "DYOR_SANTIMENT_API_KEY" in rows["social_trend"]["missing_reason"]
    assert rows["unlock_overhang"]["inputs"] == [] and rows["unlock_overhang"]["percentile"] is None
    # feed statuses drive the reason when nothing is gated
    assert missing_reason("mc_tvl", None, {"defillama": "empty"}) == "defillama has no data for this token"
    assert missing_reason("mc_tvl", None, {"defillama": "error"}) == "defillama errored this run"
    assert "no identifier" in missing_reason("top10_concentration", None, {"ethplorer": "off"})
    assert "reference basket" in missing_reason("mc_tvl", 2.0, {"defillama": "ok"})


def test_gate_rows_show_evidence_and_cap(sample_config):
    # total supply 20× circulating → FDV/MCAP 20 → extreme_fdv_mcap caps at 40
    recs = [_rec("d", market={"total_supply": 1e10, "max_supply": 1e10}), _rec("a"), _rec("b", mc=3e9)]
    results = {r.token: r for r in score_universe(recs, sample_config, reference_anchored=False)}
    ex = explain(recs[0], results["d"], sample_config)
    rules = {r["rule"]: r for r in ex["gate"]["rules"]}
    assert rules["extreme_fdv_mcap"]["tripped"] is True and rules["extreme_fdv_mcap"]["cap"] == 40.0
    fdv_ev = rules["extreme_fdv_mcap"]["evidence"][0]
    assert fdv_ev["value"] == pytest.approx(20.0) and fdv_ev["threshold"] == "trips when > 10×"
    assert ex["gate"]["cap"] == 40.0 and ex["gate"]["final_score"] <= 40.0
    assert "extreme_fdv_mcap" in ex["gate"]["flags"]
    dead = rules["dead_token"]
    assert dead["tripped"] is False and dead["cap"] == 0.0 and dead["action"] == "zero"
    labels = [e["label"] for e in dead["evidence"]]
    assert labels[0].startswith("Days since last GitHub push (x-labs)") and "24h volume" in labels
    assert rules["anonymous_team"]["active_on_open_data"] is False
    # tier block: thresholds on the 0–100 scale, coverage counts
    assert ex["tier"]["thresholds"][0] == {"label": "A — high conviction", "min": 80}
    assert ex["tier"]["coverage"]["total"] == results["d"].features_total
    assert ex["method"]["scale"] == 100 and ex["method"]["class"] == "defi"


def test_feature_working_without_inputs_is_empty():
    assert feature_working("price_to_fees", {}) == ([], None)
    assert feature_working("price_to_fees", None) == ([], None)
    ins, formula = feature_working("fdv_mcap_ratio", {"fdv_mcap_method": "fdv_over_mcap", "fdv": 2e9, "market_cap": 1e9})
    assert formula == "{fdv} ÷ {market_cap}" and [i["key"] for i in ins] == ["fdv", "market_cap"]
    ins, formula = feature_working("unlock_overhang", {"unlock": {"has_vesting": False}})
    assert formula == "0 — no vesting schedule"


def test_explain_none_without_a_result():
    assert explain({}, None) is None


# --- the display scale ------------------------------------------------------------

def test_score_to_dict_is_on_the_0_100_scale(scored):
    _, results = scored
    r = results["a"]
    d = score_to_dict(r)
    assert d["scale"] == 100
    assert d["final_score"] == pytest.approx(round(r.final_score * 100, 1))
    assert d["raw_score"] == pytest.approx(round(r.raw_score * 100, 1))
    assert d["coverage"] == round(r.coverage * 100)
    assert d["tier_stability"] == round(r.tier_stability * 100)
    assert all(0 <= v <= 100 for v in d["domain_scores"].values() if v is not None)
    # the engine value itself is untouched
    assert 0.0 <= r.final_score <= 1.0
