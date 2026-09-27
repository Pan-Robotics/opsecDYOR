"""Reference baskets — cached same-class peer sets for fair comparison.

A score is only meaningful relative to its peers; ranking an L1 against DeFi apps
distorts its fundamentals. `build_references` collects a curated basket per asset
class and caches it, so `analyze(peer_mode="class")` can score a token against its
own kind (L1↔L1, DeFi↔DeFi) without a slow live collect every time.
"""

from __future__ import annotations

from functools import cache
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
    from dyor.collect import Collector, Target
    from dyor.store import db

    wanted = classes or list(REFERENCE_BASKETS)

    # The anchor must carry the same feeds live tokens get (holder concentration,
    # chain-level fundamentals, verification …) or anchored classes silently
    # fall back to relative normalization for those features. `make_target` is
    # the single source of that enrichment; Targets are built DIRECTLY from the
    # known gecko_ids (no per-token CoinGecko /search — the rate-limit bottleneck).
    from dyor.universe import basket_targets, fetch_identity_maps

    protocols, platforms, chains = fetch_identity_maps(cfg, use_cache=use_cache)
    by_gid = {t.gecko_id: t for t in basket_targets(protocols, platforms=platforms, chains=chains)}

    def _target(gid: str) -> Target:
        return by_gid.get(gid) or Target(gecko_id=gid, santiment_slug=gid, cryptorank_key=gid)

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


class ReferenceUnavailable(RuntimeError):
    """The reference baskets exist but could not be read (DB contention). Raised
    instead of silently scoring without the anchor — an unanchored score is a
    different number for the same token, not a degraded one."""


def reference_peers(asset_class: str | None) -> list[dict[str, Any]]:
    """Cached reference records for a class (empty if not built yet).

    Opened READ-ONLY: DuckDB refuses a read-write open while another thread of
    the same process holds a read-only one ("different configuration than
    existing connections"), and the API always has such readers in flight.
    Opening read-write here made the anchor vanish intermittently under load —
    the same token scored 54.8 on one request and 58.5 on the next (2026-09-27).
    """
    if not asset_class:
        return []
    from dyor.store import db

    con = db.connect(read_only=True)
    try:
        return db.reference_records(con, asset_class)
    finally:
        con.close()


def _basket_version(asset_class: str) -> str:
    """Latest updated_at of a class's stored basket — the anchor's version key.

    Read fresh on every lookup (a cheap local DuckDB query) so a long-lived API
    worker picks up a `dyor reference` rebuild done by another process instead
    of serving a process-lifetime-pinned anchor forever. Read-only, and a read
    failure PROPAGATES (it used to become "", which quietly re-keyed the cache).
    """
    from dyor.store import db

    con = db.connect(read_only=True)
    try:
        row = con.execute(
            "SELECT max(updated_at) FROM reference_records WHERE asset_class = ?",
            [asset_class],
        ).fetchone()
        return str(row[0]) if row and row[0] else ""
    finally:
        con.close()


# The last anchor each class loaded successfully in this process. A transient
# read failure (lock contention with a writer) keeps serving it: the anchor only
# ever changes on an explicit `dyor reference` rebuild, so "stale" here means
# at most one rebuild behind, never a different scale.
_LAST_GOOD: dict[str, dict[str, np.ndarray]] = {}


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
    try:
        dist = _distributions_for(asset_class, _basket_version(asset_class))
    except Exception as exc:
        if asset_class in _LAST_GOOD:
            return _LAST_GOOD[asset_class]
        raise ReferenceUnavailable(f"reference basket for '{asset_class}' unreadable: "
                                   f"{type(exc).__name__}: {exc}") from exc
    _LAST_GOOD[asset_class] = dist
    return dist


@cache
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
    _LAST_GOOD.clear()
