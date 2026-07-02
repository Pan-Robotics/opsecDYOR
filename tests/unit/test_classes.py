import math

import pytest

from dyor.classes import STATIC_WEIGHTS, class_profile, classify_asset
from dyor.pipeline import score_universe


def test_classify_known_ids():
    assert classify_asset(gecko_id="bitcoin") == "monetary"
    assert classify_asset(gecko_id="solana") == "l1"          # empty cats → id net
    assert classify_asset(gecko_id="usd-coin") == "stablecoin"
    assert classify_asset(gecko_id="dogecoin") == "meme"


def test_l1_id_beats_has_fees():
    # Ethereum has DefiLlama fee data but is a platform, not a DeFi app.
    assert classify_asset(gecko_id="ethereum", has_fees=True,
                          coingecko_categories=["Smart Contract Platform"]) == "l1"


def test_classify_by_categories():
    assert classify_asset(gecko_id="x", coingecko_categories=["Layer 1 (L1)"]) == "l1"
    assert classify_asset(gecko_id="x", coingecko_categories=["Meme", "Dog-Themed"]) == "meme"
    assert classify_asset(gecko_id="x", coingecko_categories=["USD Stablecoin"]) == "stablecoin"
    assert classify_asset(gecko_id="x", coingecko_categories=["Decentralized Finance (DeFi)"]) == "defi"


def test_stablecoin_issuer_is_not_a_stablecoin():
    # Aave has the "Stablecoin Issuer" category (it issues GHO) but is a DeFi app.
    assert classify_asset(
        gecko_id="aave",
        coingecko_categories=["Stablecoin Issuer", "Lending/Borrowing Protocols",
                              "Decentralized Finance (DeFi)"],
        has_fees=True, price=75.0,
    ) == "defi"


def test_stablecoin_requires_peg_when_price_known():
    # a $75 token tagged with a stablecoin category is NOT a stablecoin
    assert classify_asset(gecko_id="x", coingecko_categories=["USD Stablecoin"], price=75.0) != "stablecoin"
    # a $1.00 token with that category is
    assert classify_asset(gecko_id="x", coingecko_categories=["USD Stablecoin"], price=1.0) == "stablecoin"


def test_classify_priority_meme_over_l1():
    # dogecoin is tagged BOTH "Smart Contract Platform" and "Meme" → meme wins
    assert classify_asset(gecko_id="z", coingecko_categories=["Smart Contract Platform", "Meme"]) == "meme"


def test_classify_defi_via_fees_then_general_fallback():
    assert classify_asset(gecko_id="z", has_fees=True) == "defi"
    assert classify_asset(gecko_id="z", defillama_category="Lending") == "defi"
    assert classify_asset(gecko_id="z") == "general"  # no signal at all


def test_class_profiles_weights_sum_to_one():
    for name in ("defi", "l1", "monetary", "meme", "stablecoin", "general"):
        prof = class_profile(name)
        assert abs(sum(prof.weights.values()) - 1.0) < 1e-9, name


def test_monetary_profile_excludes_fundamental():
    prof = class_profile("monetary")
    assert "fundamental" not in prof.feature_spec
    assert "fundamental" not in prof.weights
    assert "tokenomics" in prof.feature_spec  # scarcity lives here


def test_monetary_token_not_penalized_for_missing_revenue():
    # A monetary asset with NO P/F should not have a 'fundamental' domain at all,
    # so missing revenue can't drag it down — it's scored on scarcity/onchain.
    btc = {"token": "btc", "_class": "monetary",
           "inflation_rate": 0.018, "float_ratio": 0.95, "fdv_mcap_ratio": 1.05,
           "unlock_overhang": 0.0, "top10_concentration": 0.10, "address_growth": 0.2,
           "reserve_trend": -0.5, "social_trend": 0.3, "social_sentiment": 0.9,
           "dev_commit_trend": 0.4}
    peer = {"token": "ltc", "_class": "monetary",
            "inflation_rate": 0.08, "float_ratio": 0.80, "fdv_mcap_ratio": 1.2,
            "unlock_overhang": 0.1, "top10_concentration": 0.30, "address_growth": -0.1,
            "reserve_trend": 0.2, "social_trend": -0.2, "social_sentiment": 0.5,
            "dev_commit_trend": 0.1}
    res = {r.token: r for r in score_universe([btc, peer])}
    assert "fundamental" not in res["btc"].domain_scores
    # btc dominates its monetary peer on scarcity + adoption
    assert res["btc"].final_score > res["ltc"].final_score
    assert res["btc"].coverage == 1.0  # all monetary-spec features present


def test_unknown_class_defaults_to_general():
    prof = class_profile("nonsense-class")
    assert prof.name == "general"
    assert "fundamental" in prof.feature_spec


def test_defi_missing_core_fundamental_is_penalized():
    # A DeFi token with NO fundamental data (no fees/revenue/TVL) is penalized:
    # its fundamental domain is floored, not renormalized away.
    no_fund = {"token": "ghostdex", "_class": "defi",
               "fdv_mcap_ratio": 1.1, "float_ratio": 0.9, "value_accrual": 0.5,
               "top10_concentration": 0.2, "address_growth": 0.3,
               "social_sentiment": 0.8, "dev_commit_trend": 0.5}
    peer = {"token": "realdex", "_class": "defi",
            "price_to_fees": 8, "price_to_sales": 10, "mc_tvl": 1.5, "real_yield": 0.06,
            "fdv_mcap_ratio": 1.1, "float_ratio": 0.9, "value_accrual": 0.5,
            "top10_concentration": 0.2, "address_growth": 0.3,
            "social_sentiment": 0.8, "dev_commit_trend": 0.5}
    res = {r.token: r for r in score_universe([no_fund, peer])}
    ghost = res["ghostdex"]
    assert ghost.domain_scores["fundamental"] == 0.0          # floored, not NaN
    assert any("penalized" in a for a in ghost.advisories)
    assert ghost.final_score < res["realdex"].final_score     # and it costs the score


def test_monetary_missing_fundamental_not_penalized():
    # Monetary has no 'fundamental' in its spec, so it's never penalized for it.
    btc = {"token": "btc", "_class": "monetary",
           "inflation_rate": 0.018, "float_ratio": 0.95, "top10_concentration": 0.1,
           "address_growth": 0.2, "social_sentiment": 0.9, "dev_commit_trend": 0.4}
    res = score_universe([btc, {"token": "x", "_class": "monetary", "float_ratio": 0.5}])[0]
    assert "fundamental" not in res.domain_scores
    assert not any("penalized" in a for a in res.advisories)


def test_penalty_override_param_beats_config(sample_config):
    # config default penalizes; the runtime param can turn it OFF for this call
    no_fund = {"token": "g", "_class": "defi", "fdv_mcap_ratio": 1.1, "value_accrual": 0.5}
    peer = {"token": "p", "_class": "defi", "value_accrual": 0.1}
    on = next(r for r in score_universe([no_fund, peer], sample_config, penalize_missing_core=True) if r.token == "g")
    off = next(r for r in score_universe([no_fund, peer], sample_config, penalize_missing_core=False) if r.token == "g")
    assert on.domain_scores.get("fundamental") == 0.0     # floored
    assert math.isnan(off.domain_scores.get("fundamental", float("nan")))  # renormalized away
    assert any("penalized" in a for a in on.advisories)
    assert not any("penalized" in a for a in off.advisories)


def test_penalty_can_be_disabled(sample_config):
    cfg = {**sample_config, "scoring": {**sample_config["scoring"], "penalize_missing_core": False}}
    no_fund = {"token": "g", "_class": "defi", "fdv_mcap_ratio": 1.1, "value_accrual": 0.5}
    res = score_universe([no_fund, {"token": "p", "_class": "defi", "value_accrual": 0.1}], cfg)
    g = next(r for r in res if r.token == "g")
    assert "fundamental" not in g.domain_scores or math.isnan(g.domain_scores.get("fundamental", float("nan")))
