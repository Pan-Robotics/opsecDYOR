"""Santiment client — social + dev + on-chain via GraphQL (free entry point).

Free tier: 1000 calls/mo, 30-day history, 3000+ assets. GraphQL-only, so this
client POSTs queries rather than using the GET helpers in BaseClient. Auth is an
optional `Authorization: Apikey <key>` header (DYOR_SANTIMENT_API_KEY).

This is a thin stub: one generic `query()` plus a `social_volume` convenience
wrapper showing the metric-query shape. Extend with more `getMetric` calls as
the social/dev layer fills out.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from dyor.config import PROJECT_ROOT, get_settings, load_config
from dyor.ingestion.base import FileCache, _evict_once, shared_limiter


class SantimentBudgetExhausted(RuntimeError):
    """The anonymous monthly call budget for this IP is spent; every call until
    the reset would 429. Surfaces as a feed ERROR (never as 'not tracked')."""


def _rate_limit_wait_seconds(body: str) -> int | None:
    """Santiment's 429 body says how long: 'Try again in 287179 seconds (3 days …)'."""
    import re

    m = re.search(r"[Tt]ry again in (\d+) seconds", body or "")
    return int(m.group(1)) if m else None

# gecko_id → Santiment slug where they differ. The collector's best-effort
# `santiment_slug = gecko_id` misses these (verified against Santiment's own
# allProjects list, 2026-08-24); two are L1 reference-basket members, so the
# mapping directly widens the anchored address-growth/dev distributions.
SLUG_OVERRIDES: dict[str, str] = {
    "polkadot": "polkadot-new",
    "starknet": "starknet-token",
    "tornado-cash": "torn",
    "quickswap": "p-quickswap-new",
    "benqi": "a-benqi",
    "bsquared-network": "bnb-bsquared-network",
    "veno-finance": "veno-finance-vno",
    "rain": "arb-rain",
}


def resolve_slug_map(
    projects: list[dict[str, Any]],
    coins_by_id: dict[str, dict[str, Any]],
    gecko_ids: list[str],
) -> dict[str, str]:
    """gecko_id → Santiment slug, resolved as far as free data allows (pure).

    Precedence: slug == gecko_id · SLUG_OVERRIDES · main contract address
    (any chain in CoinGecko's platforms) · exact name · unique ticker. Measured
    on the live 116-token universe this lifts hits from 68 to 94; the rest are
    genuinely untracked by Santiment.
    """
    slugs = {p["slug"] for p in projects if p.get("slug")}
    by_addr = {p["mainContractAddress"].lower(): p["slug"]
               for p in projects if p.get("mainContractAddress") and p.get("slug")}
    by_name: dict[str, str] = {}
    by_ticker: dict[str, list[str]] = {}
    for p in projects:
        if not p.get("slug"):
            continue
        by_name.setdefault((p.get("name") or "").strip().lower(), p["slug"])
        by_ticker.setdefault((p.get("ticker") or "").strip().lower(), []).append(p["slug"])

    out: dict[str, str] = {}
    for gid in gecko_ids:
        if gid in slugs:
            out[gid] = gid
            continue
        if gid in SLUG_OVERRIDES:
            out[gid] = SLUG_OVERRIDES[gid]
            continue
        coin = coins_by_id.get(gid) or {}
        addrs = [(a or "").lower() for a in (coin.get("platforms") or {}).values() if a]
        hit = next((by_addr[a] for a in addrs if a in by_addr), None)
        if hit:
            out[gid] = hit
            continue
        name = (coin.get("name") or "").strip().lower()
        if name and name in by_name:
            out[gid] = by_name[name]
            continue
        tick = (coin.get("symbol") or "").strip().lower()
        cands = by_ticker.get(tick, [])
        if tick and len(cands) == 1:
            out[gid] = cands[0]
    return out


class SantimentClient:
    name = "santiment"

    def __init__(self, config: dict | None = None, *, use_cache: bool = True) -> None:
        cfg = config if config is not None else load_config()
        ingestion = cfg["ingestion"]
        src = ingestion["sources"]["santiment"]
        self.url = src["base_url"]
        self.limiter = shared_limiter(self.name, src["rate_limit_per_min"])  # one bucket per process
        # The free tier is 1000 calls/MONTH — without a cache, every analyze
        # burns 2 of them live (~500 analyses/month for the whole service).
        # POSTs are cached on (url, query+variables), same TTL as the GETs.
        self.use_cache = use_cache
        self.cache = FileCache(
            PROJECT_ROOT / ingestion["cache_dir"] / self.name,
            ingestion["cache_ttl_seconds"],
        )
        # Only ~35% of our gecko_ids are Santiment slugs, so most calls fail with
        # "is not an existing slug" — and each failure still costs a call against
        # the ~1000/month free tier. Remember the misses for much longer than a
        # normal response: a slug that doesn't exist rarely starts existing, and
        # a stale miss self-corrects on the next expiry.
        self.miss_cache = FileCache(
            PROJECT_ROOT / ingestion["cache_dir"] / f"{self.name}-misses",
            src.get("miss_cache_ttl_seconds", 30 * 86400),
        )
        if use_cache:
            # This client doesn't go through BaseClient, so it must evict for
            # itself — and it is the biggest cache: the day-rounded window makes
            # every week's positive entries a fresh key that otherwise lives forever.
            _evict_once(self.cache)
            _evict_once(self.miss_cache)
        headers = {"Content-Type": "application/json", "User-Agent": "dyor/0.1"}
        key = get_settings().santiment_api_key
        if key:
            headers["Authorization"] = f"Apikey {key}"
        self._client = httpx.Client(timeout=30.0, headers=headers)

    # Set when Santiment answers 429 with a wait of an hour or more: the
    # anonymous MONTHLY budget (~1000 calls per IP) is spent, not the per-minute
    # one. Every further call this process would make is a guaranteed 429 that
    # still burns the shared per-minute allowance and 6 s of pacing each, so the
    # feed is short-circuited to an immediate, explicit error instead. Cached
    # responses keep being served. (Seen 2026-09-27: "Try again in 287179 s".)
    _exhausted_until: float = 0.0

    def query(self, graphql: str, variables: dict | None = None) -> dict[str, Any]:
        cache_key = {"q": graphql, "v": variables or {}}
        if self.use_cache:
            cached = self.cache.get(self.url, cache_key)
            if cached is not None:
                return cached
        if time.time() < SantimentClient._exhausted_until:
            left = int(SantimentClient._exhausted_until - time.time())
            raise SantimentBudgetExhausted(
                f"santiment: monthly API budget exhausted for this IP — resets in ~{left // 3600}h")
        self.limiter.acquire()
        resp = self._client.post(
            self.url, json={"query": graphql, "variables": variables or {}}
        )
        if resp.status_code == 429:
            wait = _rate_limit_wait_seconds(resp.text)
            if wait is not None and wait >= 3600:
                SantimentClient._exhausted_until = time.time() + wait
                raise SantimentBudgetExhausted(
                    f"santiment: monthly API budget exhausted for this IP — resets in ~{wait // 3600}h")
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(f"santiment GraphQL error: {payload['errors']}")
        if self.use_cache:
            self.cache.set(self.url, cache_key, payload["data"])
        return payload["data"]

    # `interval` is a Santiment custom scalar; inline it as a literal (it's
    # internal, never user input) rather than risk a variable-type mismatch.
    _TIMESERIES = """
    query ($metric: String!, $slug: String!, $from: DateTime!, $to: DateTime!) {{
      getMetric(metric: $metric) {{
        timeseriesData(slug: $slug, from: $from, to: $to, interval: "{interval}") {{
          datetime
          value
        }}
      }}
    }}
    """

    def metric_timeseries(
        self,
        metric: str,
        slug: str,
        from_iso: str,
        to_iso: str,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """Generic Santiment metric time series → [{datetime, value}, ...].

        Free/anonymous access works for many on-chain + dev metrics (e.g.
        `daily_active_addresses`, `dev_activity`) but only within the last ~30
        days. Social metrics (`social_volume_total`) require a key.
        """
        miss_key = {"unsupported": [metric, slug]}
        if self.use_cache and self.miss_cache.get(self.url, miss_key) is not None:
            return []  # known-untracked slug — don't spend a call to be told again

        gql = self._TIMESERIES.format(interval=interval)
        try:
            data = self.query(gql, {
                "metric": metric, "slug": slug, "from": from_iso, "to": to_iso,
            })
        except RuntimeError as exc:
            # Remember only "this slug does not exist" — never a rate limit, a
            # quota exhaustion or a subscription restriction, which are
            # transient or key-dependent and must stay loud.
            if self.use_cache and "is not an existing slug" in str(exc):
                self.miss_cache.set(self.url, miss_key, True)
                return []
            raise
        return data["getMetric"]["timeseriesData"]

    def all_projects(self) -> list[dict[str, Any]]:
        """The identity list behind `resolve_slug_map` (one call, cached)."""
        data = self.query("{ allProjects { slug ticker name mainContractAddress infrastructure } }")
        return data.get("allProjects") or []

    def daily_active_addresses(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """On-chain usage trend (free/anonymous)."""
        return self.metric_timeseries("daily_active_addresses", slug, from_iso, to_iso)

    def dev_activity(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """Santiment's dev-activity metric — a richer dev signal than a single
        repo's last push (free/anonymous)."""
        return self.metric_timeseries("dev_activity", slug, from_iso, to_iso)

    def social_volume(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """Daily social volume (requires an API key — restricted anonymously)."""
        return self.metric_timeseries("social_volume_total", slug, from_iso, to_iso)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SantimentClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# Kept off the hot path: a tiny backoff helper for the manual POST flow above.
def _sleep_backoff(attempt: int, base: float = 1.0) -> None:
    time.sleep(base * (2**attempt))
