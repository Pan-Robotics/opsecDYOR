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

    # Reference baskets are known gecko_ids — build Targets DIRECTLY (no per-token
    # CoinGecko /search, which is the rate-limit bottleneck). slug/category come
    # from the DefiLlama index; santiment/cryptorank keys are best-effort = gecko_id.
    def _target(gid: str) -> Target:
        info = dl_index.get(gid, {})
        return Target(gecko_id=gid, defillama_slug=info.get("slug"),
                      santiment_slug=gid, cryptorank_key=gid, category=info.get("category"))

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


def _same_class_stored(asset_class: str) -> list[dict[str, Any]]:
    """Same-class records from the latest stored run (best-effort, [] on error)."""
    try:
        from dyor.store import db

        con = db.connect()
        try:
            return [r for r in db.latest_records(con) if r.get("_class") == asset_class]
        finally:
            con.close()
    except Exception:
        return []


@lru_cache(maxsize=None)
def reference_distributions(asset_class: str | None) -> dict[str, np.ndarray]:
    """{feature: reference values} for a class — the *fixed* distribution that
    `score_universe(reference_anchored=True)` ranks each token against.

    Built from the curated reference basket ENRICHED with same-class records from
    the latest stored run, because the curated baskets often lack holder-
    concentration / social / inflation data (e.g. `build_references` collects no
    Ethplorer holder data), which would otherwise drop those features — and whole
    domains — out of anchored scoring. Stored (fresher) wins on a token collision.

    Cached per process so a token's tier stays reproducible within a session;
    `clear_distribution_cache()` recalibrates after a reference/screener rebuild.
    Empty for a class with no data → caller falls back to relative normalization.
    """
    if not asset_class:
        return {}
    merged: dict[str | None, dict] = {r.get("token"): r for r in reference_peers(asset_class)}
    for r in _same_class_stored(asset_class):
        merged[r.get("token")] = r  # stored (fresher / better-covered) overrides basket
    recs = list(merged.values())

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
    reference_distributions.cache_clear()
