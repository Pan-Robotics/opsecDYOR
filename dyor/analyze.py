"""On-demand single-token analysis.

Resolve a user query (name / symbol / contract address) to a token, auto-resolve
its data-source ids, collect it live, and score it **against a peer baseline**
(the last persisted run, or the sample set) — because a token scored in
isolation has no percentiles to rank against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dyor.collect import Collector, Target
from dyor.config import load_config
from dyor.resolve import ResolvedToken, resolve_query
from dyor.sample_data import SAMPLE_UNIVERSE
from dyor.scoring.composite import ScoreResult
from dyor.pipeline import score_universe


@dataclass
class AnalyzeResult:
    query: str
    resolved: ResolvedToken | None
    record: dict | None = None
    result: ScoreResult | None = None
    peer_count: int = 0
    errors: list[dict] = field(default_factory=list)
    all_results: list[ScoreResult] = field(default_factory=list)  # target + peers, ranked
    rank: int | None = None                                       # target's 1-based rank

    @property
    def ok(self) -> bool:
        return self.result is not None


def _defillama_index(cfg: dict, use_cache: bool) -> dict[str, dict[str, Any]]:
    """gecko_id -> {slug, category} from DefiLlama protocols (highest-TVL wins)."""
    from dyor.ingestion.defillama import DefiLlamaClient

    with DefiLlamaClient(cfg, use_cache=use_cache) as dl:
        protocols = dl.protocols()
    best: dict[str, dict[str, Any]] = {}
    for p in protocols:
        gid = p.get("gecko_id")
        if not gid:
            continue
        tvl = p.get("tvl") or 0
        if gid not in best or tvl > best[gid]["tvl"]:
            best[gid] = {"slug": p.get("slug"), "category": p.get("category"), "tvl": tvl}
    return best


def target_from_resolved(resolved: ResolvedToken, dl_index: dict[str, dict[str, Any]]) -> Target:
    """Build a Target from a resolved token, auto-resolving optional ids."""
    info = dl_index.get(resolved.gecko_id, {})
    return Target(
        gecko_id=resolved.gecko_id,
        defillama_slug=info.get("slug"),
        github_org=None,
        santiment_slug=resolved.gecko_id,      # best-effort
        cryptorank_key=resolved.gecko_id,      # best-effort
        eth_contract=resolved.platforms.get("ethereum"),
        category=info.get("category"),
    )


def analyze_token(
    query: str,
    config: dict | None = None,
    *,
    peers: list[dict] | None = None,
    peer_mode: str = "stored",   # "stored" | "class" | "sample" | "category"
    penalize_missing_core: bool | None = None,
    use_cache: bool = True,
    persist: bool = False,
) -> AnalyzeResult:
    """Resolve → collect → score one token against a peer baseline.

    `peer_mode` picks the comparison set:
      * "class"    — the token's own asset class (L1↔L1, DeFi↔DeFi) from the cached
                     reference baskets (`dyor reference`). Fairest; falls back to
                     same-class records in the stored run, then "stored".
      * "stored"   — the last persisted run (mixed classes).
      * "sample"   — the built-in sample universe.
      * "category" — a live top-6 of the token's DefiLlama category (slower).

    `persist=True` writes the freshly collected record back into the latest stored
    run (live self-heal), so the screener reflects the same fresh data on next view.
    """
    cfg = config if config is not None else load_config()

    with Collector(cfg, use_cache=use_cache) as collector:
        # Share the Collector's CoinGecko client so resolution + collection pace
        # against ONE rate limiter (avoids self-inflicted 429s on the free tier).
        try:
            resolved = resolve_query(query, cfg, use_cache=use_cache, client=collector.cg)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the UI
            return AnalyzeResult(query=query, resolved=None,
                                 errors=[{"token": query, "source": "resolve",
                                          "error": f"{type(exc).__name__}: {exc}"}])
        if resolved is None:
            return AnalyzeResult(query=query, resolved=None)

        target = target_from_resolved(resolved, _defillama_index(cfg, use_cache))

        peer_targets: list[Target] = []
        if peer_mode == "category" and target.category:
            from dyor.universe import fetch_universe
            peer_targets = [t for t in fetch_universe(cfg, top_n=6, category=target.category,
                                                      use_cache=use_cache)
                            if t.gecko_id != target.gecko_id]

        records = collector.collect([target, *peer_targets])
        errors = list(collector.errors)

    record = next((r for r in records if r.get("token") == target.gecko_id), None)
    if record is None:
        return AnalyzeResult(query=query, resolved=resolved, errors=errors)
    if persist:
        _persist_live(record)
    live_peers = [r for r in records if r.get("token") != target.gecko_id]

    # Choose the peer baseline.
    if peers is not None:
        baseline = peers
    elif peer_mode == "category" and live_peers:
        baseline = live_peers
    elif peer_mode == "sample":
        baseline = SAMPLE_UNIVERSE
    elif peer_mode == "class":
        baseline = _class_peers(record.get("_class")) or _stored_peers() or SAMPLE_UNIVERSE
    else:
        baseline = _stored_peers() or SAMPLE_UNIVERSE
    baseline = [p for p in baseline if p.get("token") != record.get("token")]

    ranked = score_universe([record, *baseline], cfg, penalize_missing_core=penalize_missing_core)
    by_token = {r.token: r for r in ranked}
    rank = next((i + 1 for i, r in enumerate(ranked) if r.token == record["token"]), None)
    return AnalyzeResult(
        query=query, resolved=resolved, record=record,
        result=by_token.get(record["token"]), peer_count=len(baseline),
        errors=errors, all_results=ranked, rank=rank,
    )


def _persist_live(record: dict) -> None:
    """Write a freshly collected record into the latest stored run (best-effort)
    so the screener self-heals to the same data. Never breaks the analysis."""
    try:
        from dyor.store import db

        con = db.connect()
        try:
            db.upsert_into_latest_run(con, record)
        finally:
            con.close()
    except Exception:
        pass


def _stored_peers() -> list[dict]:
    """The last persisted run as peers (empty if the store doesn't exist yet)."""
    try:
        from dyor.store import db

        con = db.connect()
        try:
            return db.latest_records(con)
        finally:
            con.close()
    except Exception:
        return []


def _class_peers(asset_class: str | None) -> list[dict]:
    """Same-class peers: the cached reference basket merged with same-class records
    from the stored run. The freshly-stored record WINS on a token collision, so a
    token that's been live-analyzed shows its current data in others' peer tables
    too (consistent with live-wins self-heal). Empty → caller falls back to stored."""
    try:
        from dyor.reference import reference_peers

        merged: dict[str | None, dict] = {p.get("token"): p for p in reference_peers(asset_class)}
        for p in _stored_peers():
            if p.get("_class") == asset_class:
                merged[p.get("token")] = p  # stored (fresher) overrides basket cache
        return list(merged.values())
    except Exception:
        return []
