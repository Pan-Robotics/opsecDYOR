"""Reference baskets — cached same-class peer sets for fair comparison.

A score is only meaningful relative to its peers; ranking an L1 against DeFi apps
distorts its fundamentals. `build_references` collects a curated basket per asset
class and caches it, so `analyze(peer_mode="class")` can score a token against its
own kind (L1↔L1, DeFi↔DeFi) without a slow live collect every time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from dyor.classes import FEATURE_DIRECTION, REFERENCE_BASKETS
from dyor.config import load_config


def build_references(
    config: dict | None = None,
    classes: list[str] | None = None,
    *,
    use_cache: bool = True,
) -> dict[str, int]:
    """Collect each class's reference basket and cache it. Returns {class: count}."""
    cfg = config if config is not None else load_config()
    from dyor.analyze import _defillama_index
    from dyor.collect import Collector, Target
    from dyor.store import db

    wanted = classes or list(REFERENCE_BASKETS)
    dl_index = _defillama_index(cfg, use_cache)  # gecko_id -> {slug, category}

    # One coins_list call resolves Ethereum contracts for the whole basket, so
    # the anchor carries holder-concentration (Ethplorer) + verification
    # (Sourcify) distributions — without these the anchored classes silently
    # fall back to relative normalization for those features.
    from dyor.ingestion.coingecko import CoinGeckoClient
    from dyor.universe import eth_contracts_from_coins_list
    with CoinGeckoClient(cfg, use_cache=use_cache) as cg:
        eth_contracts = eth_contracts_from_coins_list(cg.coins_list())

    # Reference baskets are known gecko_ids — build Targets DIRECTLY (no per-token
    # CoinGecko /search, which is the rate-limit bottleneck). slug/category come
    # from the DefiLlama index; santiment/cryptorank keys are best-effort = gecko_id.
    def _target(gid: str) -> Target:
        info = dl_index.get(gid, {})
        return Target(gecko_id=gid, defillama_slug=info.get("slug"),
                      santiment_slug=gid, cryptorank_key=gid,
                      eth_contract=eth_contracts.get(gid), category=info.get("category"))

    # Collect into memory first — do NOT hold the DuckDB write-lock during the
    # (minutes-long) collection, or it blocks the API/analyze from reading.
    collected: dict[str, list[dict[str, Any]]] = {}
    with Collector(cfg, use_cache=use_cache) as collector:
        for cls in wanted:
            targets = [_target(gid) for gid in REFERENCE_BASKETS.get(cls, [])]
            collected[cls] = collector.collect(targets) if targets else []

    con = db.connect()
    try:
        counts = {cls: db.upsert_reference(con, cls, recs) for cls, recs in collected.items()}
    finally:
        con.close()
    clear_distribution_cache()  # freshly built baskets → drop stale distributions
    return counts


def reference_peers(asset_class: str | None) -> list[dict[str, Any]]:
    """Cached reference records for a class (empty if not built yet)."""
    if not asset_class:
        return []
    from dyor.store import db

    con = db.connect()
    try:
        return db.reference_records(con, asset_class)
    finally:
        con.close()


def _basket_version(asset_class: str) -> str:
    """Latest updated_at of a class's stored basket — the anchor's version key.

    Read fresh on every lookup (a cheap local DuckDB query) so a long-lived API
    worker picks up a `dyor reference` rebuild done by another process instead
    of serving a process-lifetime-pinned anchor forever.
    """
    try:
        from dyor.store import db

        con = db.connect()
        try:
            row = con.execute(
                "SELECT max(updated_at) FROM reference_records WHERE asset_class = ?",
                [asset_class],
            ).fetchone()
            return str(row[0]) if row and row[0] else ""
        finally:
            con.close()
    except Exception:
        return ""


def reference_distributions(asset_class: str | None) -> dict[str, np.ndarray]:
    """{feature: reference values} for a class — the *fixed* distribution that
    `score_universe(reference_anchored=True)` ranks each token against.

    Built from the curated reference basket ONLY. It must not mix in the latest
    persisted run: doing so moves the yardstick every time any same-class token
    is persisted (an analyze with persist, a screener rebuild, a cron refresh),
    which re-scores tokens whose own data never changed — measured at 29/32
    scores and 6 tier flips from one persist (2026-08-24 integration test). The
    only thing that may move the anchor is an explicit `dyor reference` rebuild.

    Cached per (class, basket version): reproducible within a basket build, and
    every process — warm API worker or fresh CLI — converges on the same anchor
    as soon as a rebuild lands. Empty for a class with no stored basket → caller
    falls back to relative normalization.
    """
    if not asset_class:
        return {}
    return _distributions_for(asset_class, _basket_version(asset_class))


@lru_cache(maxsize=None)
def _distributions_for(asset_class: str, version: str) -> dict[str, np.ndarray]:
    recs = reference_peers(asset_class)

    out: dict[str, np.ndarray] = {}
    for feat in FEATURE_DIRECTION:
        vals = [
            r.get(feat) for r in recs
            if r.get(feat) is not None
            and not (isinstance(r.get(feat), float) and np.isnan(r.get(feat)))
        ]
        if vals:
            out[feat] = np.asarray(vals, dtype="float64")
    return out


def clear_distribution_cache() -> None:
    """Drop the cached reference distributions (call after `build_references`)."""
    _distributions_for.cache_clear()
