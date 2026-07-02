from dyor.narratives import rank_categories

CATS = [
    {"name": "AI", "market_cap": 5e9, "market_cap_change_24h": 8.0,
     "volume_24h": 1e9, "top_3_coins_id": ["a", "b", "c", "d"]},
    {"name": "RWA", "market_cap": 3e9, "market_cap_change_24h": 2.0,
     "volume_24h": 5e8, "top_3_coins_id": ["x", "y"]},
    {"name": "DePIN", "market_cap": 1e9, "market_cap_change_24h": -3.0,
     "volume_24h": 2e8, "top_3_coins_id": []},
    {"name": "DustCat", "market_cap": 1e6, "market_cap_change_24h": 50.0,
     "volume_24h": 1e4, "top_3_coins_id": []},  # below min_market_cap → filtered
    {"name": "NoData", "market_cap": 9e9, "market_cap_change_24h": None,
     "volume_24h": 1e9},  # missing sort key → filtered
]


def test_ranks_by_momentum_descending():
    ranked = rank_categories(CATS)
    names = [r["name"] for r in ranked]
    assert names == ["AI", "RWA", "DePIN"]  # by 24h change, desc


def test_filters_microcaps_and_missing():
    ranked = rank_categories(CATS)
    names = {r["name"] for r in ranked}
    assert "DustCat" not in names   # below min_market_cap
    assert "NoData" not in names    # missing change


def test_top_3_trimmed_to_three():
    ranked = rank_categories(CATS)
    ai = next(r for r in ranked if r["name"] == "AI")
    assert ai["top_3"] == ["a", "b", "c"]


def test_top_limit_and_sort_by_market_cap():
    # Sorting by market_cap, "NoData" is valid (only its change_24h is missing)
    # and at 9e9 is the largest; DustCat is still filtered (below min_market_cap).
    ranked = rank_categories(CATS, by="market_cap", top=2)
    assert [r["name"] for r in ranked] == ["NoData", "AI"]
    assert len(ranked) == 2
