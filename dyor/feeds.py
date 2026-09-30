"""Which record fields each feed produces, and carrying them forward when a feed
fails on a live analysis.

An outage is a fact about data delivery, not about the token. Before this, a
feed that errored on a live collect left its features None; the pipeline then
dropped those domains and redistributed their weight, so during the Santiment
budget outage Ethereum read 76 (B) live while the board — collected when the
feed worked — said 52 (C). A reader quoting the live number was quoting the
outage (2026-09-30). Now the last stored values are carried forward, the feed
is marked `stale` (a fifth feed state) and an advisory says so.
"""

from __future__ import annotations

from typing import Any

from dyor.classes import FEATURE_DIRECTION

# feed → the record fields it produces (scored features AND gate inputs).
FEED_FIELDS: dict[str, list[str]] = {
    "defillama": ["price_to_fees", "price_to_sales", "mc_tvl", "real_yield", "value_accrual", "audited"],
    "santiment": ["address_growth", "dev_commit_trend", "dev_activity", "dev_activity_events", "social_trend"],
    "github": ["days_since_last_commit"],
    "ethplorer": ["top10_concentration"],
    "sourcify": ["contract_verified"],
    "cryptorank": ["unlock_overhang", "unlock_pct_of_volume", "num_vc_backers", "had_public_sale"],
    "coingecko": ["fdv_mcap_ratio", "float_ratio", "social_sentiment", "watchlist_users",
                  "daily_volume_usd", "drawdown_from_ath_pct"],
}

# feed → the `_inputs` entries (the ledger's raw figures) it produces.
FEED_INPUT_KEYS: dict[str, list[str]] = {
    "defillama": ["fees", "revenue", "holders_revenue", "value_accrual_window", "tvl", "audited"],
    "santiment": ["santiment"],
    "github": ["last_push", "github_account"],
    "ethplorer": ["top10_shares_pct"],
    "cryptorank": ["unlock"],
}

# scored feature → feed (derived, so the two tables cannot drift apart).
FEATURE_SOURCE: dict[str, str] = {
    f: feed for feed, fields in FEED_FIELDS.items() for f in fields if f in FEATURE_DIRECTION
}

FEED_STATES = ("ok", "empty", "error", "off", "stale")


def carry_forward(record: dict[str, Any], stored: dict[str, Any] | None,
                  stored_at: str | None) -> list[str]:
    """For every feed that ERRORED in `record` but was `ok` in `stored`, copy that
    feed's fields (only where the fresh record has none) and its ledger inputs,
    and mark the feed `stale`. `record["_stale"]` = {feed: stored_at} so the
    report can say how old the carried values are. Returns the feeds carried.
    A feed that is `empty` or `off` is NOT carried: those are facts about the
    token, not delivery failures."""
    if not stored:
        return []
    feeds = record.get("_feeds") or {}
    stored_feeds = stored.get("_feeds") or {}
    stored_stale = stored.get("_stale") or {}
    carried: list[str] = []
    dates: dict[str, str | None] = {}
    for feed, status in list(feeds.items()):
        # A stored row that is itself `stale` already holds carried values (a
        # carried live record gets persisted in place); carry from it too, and
        # keep the ORIGINAL date — otherwise the second analysis during an
        # outage found no `ok` row, dropped the domains and scored 11 points
        # differently from the first (sweep drift check, 2026-09-30).
        if status != "error" or stored_feeds.get(feed) not in ("ok", "stale"):
            continue
        dates[feed] = stored_stale.get(feed) or stored_at
        for key in FEED_FIELDS.get(feed, []):
            if record.get(key) is None and stored.get(key) is not None:
                record[key] = stored[key]
        stored_inputs = stored.get("_inputs") or {}
        if stored_inputs:
            inputs = record.setdefault("_inputs", {})
            for key in FEED_INPUT_KEYS.get(feed, []):
                if inputs.get(key) in (None, {}) and stored_inputs.get(key) is not None:
                    inputs[key] = stored_inputs[key]
        if feed == "github" and not record.get("_github_account") and stored.get("_github_account"):
            record["_github_account"] = stored["_github_account"]
        feeds[feed] = "stale"
        carried.append(feed)
    if carried:
        record["_feeds"] = feeds
        record["_stale"] = {f: dates[f] for f in carried}
    return carried


def domains_for_feeds(feeds: list[str], feature_spec: dict[str, list[tuple[str, bool]]]) -> list[str]:
    """Which of a class's domains draw on the given feeds (for the advisory)."""
    fields = {f for feed in feeds for f in FEED_FIELDS.get(feed, [])}
    return [d for d, feats in feature_spec.items() if any(f in fields for f, _ in feats)]
