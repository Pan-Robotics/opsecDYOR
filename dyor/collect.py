"""Ingest-to-score path: live data → metric records → ready for `score_universe`.

Two halves, deliberately split for testability:
  * `build_record(...)` — a PURE transform from raw API payloads to a scoring
    record. Unit-tested offline against fixtures.
  * `Collector` — the orchestration that calls CoinGecko + DefiLlama and feeds
    `build_record`. Integration-tested against vcrpy cassettes.

Stage-1 scope: fundamentals (P/F, P/S, MC/TVL, real yield) from DefiLlama fees +
CoinGecko market data, plus tokenomics float/dilution and the volume/drawdown
gate inputs. On-chain concentration, social, and unlock-schedule features are
left None here — they come from paid/auxiliary sources in Stage 2 and are simply
skipped by the pipeline (weights renormalize over present features).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from dyor.config import get_settings, load_config
from dyor.ingestion.coingecko import CoinGeckoClient
from dyor.ingestion.cryptorank import CryptoRankClient
from dyor.ingestion.defillama import DefiLlamaClient
from dyor.ingestion.ethplorer import EthplorerClient
from dyor.ingestion.github import GitHubClient
from dyor.ingestion.santiment import SLUG_OVERRIDES, SantimentClient
from dyor.ingestion.sourcify import SourcifyClient
from dyor.classes import classify_asset
from dyor.metrics import onchain, tokenomics, valuation

# Santiment free/anonymous history is limited to ~30 days; stay inside it.
_SANTIMENT_WINDOW_DAYS = 28


@dataclass(frozen=True)
class Target:
    """One token to score. Each optional id unlocks a feed:

    * `defillama_slug`  — fees/revenue/TVL/value-accrual
    * `github_org`      — days-since-last-push (dev gate)
    * `santiment_slug`  — active-address growth + dev-activity trend
    * `cryptorank_key`  — unlock/vesting overhang (open v0 API)
    * `eth_contract`    — holder concentration via Ethplorer (Ethereum only)
    """

    gecko_id: str
    defillama_slug: str | None = None
    github_org: str | None = None
    santiment_slug: str | None = None
    cryptorank_key: str | None = None
    eth_contract: str | None = None
    category: str | None = None  # peer group for category-relative scoring


# A small default DeFi universe: fee-generating protocols with known CoinGecko
# ids + DefiLlama slugs + GitHub orgs. Enough peers for percentile normalization
# to mean something. Extend freely.
DEFI_TARGETS: list[Target] = [
    Target("aave", "aave", "aave-dao", "aave", "aave",
           "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", category="Lending"),
    Target("uniswap", "uniswap", "Uniswap", "uniswap", "uniswap",
           "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", category="Dexs"),
    Target("lido-dao", "lido", "lidofinance", "lido", "lido-dao",
           "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32", category="Liquid Staking"),
    Target("gmx", "gmx", "gmx-io", "gmx", "gmx", None, category="Derivatives"),
    Target("curve-dao-token", "curve-dex", "curvefi", "curve", "curve-dao-token",
           "0xD533a949740bb3306d119CC777fa900bA034cd52", category="Dexs"),
    Target("hyperliquid", "hyperliquid", "hyperliquid-dex", "hyperliquid", "hyperliquid",
           None, category="Derivatives"),
]


def days_since(iso_timestamp: str | None) -> float | None:
    """Whole days between an ISO-8601 timestamp and now (UTC). None-safe."""
    if not iso_timestamp:
        return None
    ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


_WINDOWS = ("total1y", "total30d", "total7d", "total24h")
_ANNUALIZE = {"total1y": 1.0, "total30d": 365 / 30, "total7d": 365 / 7, "total24h": 365.0}


def annualized(summary: dict[str, Any] | None) -> float | None:
    """Annualize a DefiLlama fees/revenue summary, preferring longer windows.

    total1y is used as-is; otherwise the shortest available window is scaled up.
    Returns None if the summary is missing or carries no usable total.
    """
    if not isinstance(summary, dict):  # DefiLlama returns [] for absent dataTypes
        return None
    for key in _WINDOWS:
        value = summary.get(key)
        if value:
            return value * _ANNUALIZE[key]
    return None


def same_window_pair(
    num_summary: dict[str, Any] | None, den_summary: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    """Pick (numerator, denominator) from the SAME time window present in both.

    Ratios between two DefiLlama summaries (e.g. holders-revenue ÷ revenue) must
    use one window — annualizing each independently can pair a `total1y` with a
    `total30d` and distort the result. Returns (None, None) if no shared window
    has a usable denominator.
    """
    if not isinstance(num_summary, dict) or not isinstance(den_summary, dict):
        return None, None
    for w in _WINDOWS:
        den = den_summary.get(w)
        if den:
            num = num_summary.get(w)
            if num is not None:
                return num, den
    return None, None


def parse_unlock(emissions: dict[str, Any] | None, market: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the next unlock from a DefiLlama emissions
    payload → {next_unlock_usd, pct_of_supply}.

    The Pro emissions schema can't be pinned down here without a key (free tier
    returns 402), so this is intentionally tolerant: it scans for a list of
    future {timestamp, amount} events, takes the soonest, and values it at the
    current price. Returns {} on anything it doesn't recognise, so downstream
    unlock features simply stay None. Tighten against the real shape once a
    DYOR_DEFILLAMA_API_KEY is available.
    """
    if not emissions:
        return {}
    now = datetime.now(timezone.utc).timestamp()
    price = market.get("current_price")

    events = None
    for key in ("events", "unlockEvents", "upcomingEvents"):
        if isinstance(emissions.get(key), list):
            events = emissions[key]
            break
    if not events or price is None:
        return {}

    future = []
    for ev in events:
        ts = ev.get("timestamp") or ev.get("date")
        amt = ev.get("amount") or ev.get("unlock") or ev.get("noOfTokens")
        if ts and amt and float(ts) > now:
            future.append((float(ts), float(amt)))
    if not future:
        return {}

    _, amount = min(future, key=lambda e: e[0])
    out = {"next_unlock_usd": amount * price}
    circ = market.get("circulating_supply")
    if circ:
        out["pct_of_supply"] = amount / circ
    return out


def vc_backing(coin: dict[str, Any] | None) -> dict[str, Any]:
    """Extract VC-backing facts from a CryptoRank v0 coin (informational).

    'Analyze the backers' (DYOR step) — surfaced, not scored: more funds isn't
    strictly better (can mean more unlock overhang). Uses the coin we already
    fetch for unlock overhang, so it's free.
    """
    if not coin:
        return {}
    return {
        "num_backers": len(coin.get("fundIds") or []),
        "had_public_sale": bool(coin.get("crowdsales")),
    }


def holder_concentration(holders: list[dict[str, Any]] | None, n: int = 10) -> float | None:
    """Top-N holders' combined share of supply, in [0, 1], from Ethplorer rows.

    Uses each holder's `share` (% of total supply) directly — Ethplorer returns
    only the top holders, so summing balances would mis-compute the total.
    Lower is better (less concentration). None if no holder data.
    """
    if not holders:
        return None
    shares = sorted((h.get("share") or 0.0) for h in holders)[::-1][:n]
    return sum(shares) / 100.0


def _drawdown_from_ath(ath_change_pct: float | None) -> float | None:
    """CoinGecko `ath_change_percentage` is negative below ATH; report the
    drawdown as a positive percentage (0 when at/above ATH)."""
    if ath_change_pct is None:
        return None
    return max(0.0, -ath_change_pct)


def build_record(
    gecko_id: str,
    market: dict[str, Any],
    *,
    fees: dict[str, Any] | None = None,
    revenue: dict[str, Any] | None = None,
    holders_revenue: dict[str, Any] | None = None,
    tvl: float | None = None,
    last_push_iso: str | None = None,
    unlock: dict[str, Any] | None = None,
    address_growth: float | None = None,
    dev_commit_trend: float | None = None,
    social_trend: float | None = None,
    unlock_overhang: float | None = None,
    top10_concentration: float | None = None,
    contract_verified: bool | None = None,
    social_sentiment: float | None = None,
    vc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure transform: raw API payloads → one scoring record.

    `market` is a CoinGecko /coins/markets entry. `last_push_iso` is the org's
    most-recent push (GitHub); `unlock` is a parsed unlock summary (Pro/Stage-2).
    `address_growth`/`dev_commit_trend`/`social_trend` are precomputed Santiment
    growth signals. Missing inputs yield None features (skipped downstream),
    never exceptions.
    """
    mc = market.get("market_cap")
    circ = market.get("circulating_supply")
    total = market.get("total_supply") or market.get("max_supply")
    volume = market.get("total_volume")

    ann_fees = annualized(fees)
    ann_rev = annualized(revenue)
    ann_holders = annualized(holders_revenue)

    # FDV/MCAP from supply ratio (robust); fall back to CoinGecko's FDV/MC.
    fdv_mcap = valuation.fdv_mcap_ratio(total, circ)
    if fdv_mcap is None:
        fdv_mcap = valuation._safe_div(market.get("fully_diluted_valuation"), mc)

    unlock = unlock or {}

    return {
        "token": gecko_id,
        # --- fundamental ---
        "price_to_fees": valuation.price_to_fees(mc, ann_fees),
        "price_to_sales": valuation.price_to_sales(mc, ann_rev),
        "mc_tvl": valuation.mc_tvl(mc, tvl),
        "real_yield": valuation.real_yield(ann_holders, mc),
        # --- tokenomics ---
        "fdv_mcap_ratio": fdv_mcap,
        "float_ratio": tokenomics.float_ratio(circ, total),
        # token-sink: compare holders-rev and revenue over the SAME window
        "value_accrual": tokenomics.value_accrual(*same_window_pair(holders_revenue, revenue)),
        # unlock overhang: locked-supply % when vesting (CryptoRank v0, open)
        "unlock_overhang": unlock_overhang,
        # precise next-unlock ÷ volume — populated only with a keyed unlock source
        "unlock_pct_of_volume": tokenomics.unlock_pct_of_volume(
            unlock.get("next_unlock_usd"), volume
        ),
        # --- on-chain ---
        "top10_concentration": top10_concentration,  # Ethplorer (ETH ERC-20s)
        "address_growth": address_growth,             # Santiment
        # --- social ---
        "social_trend": social_trend,          # Santiment (key-gated)
        "social_sentiment": social_sentiment,  # CoinGecko up-votes (keyless, coarse)
        # --- dev ---
        "dev_commit_trend": dev_commit_trend,          # Santiment dev-activity trend
        "days_since_last_commit": days_since(last_push_iso),  # GitHub last push (gate)
        # --- gate inputs derivable from free market data ---
        "daily_volume_usd": volume,
        "drawdown_from_ath_pct": _drawdown_from_ath(market.get("ath_change_percentage")),
        # --- gate input: contract verification (Sourcify; True or None, never False) ---
        "contract_verified": contract_verified,
        # --- informational (not scored): VC backing from CryptoRank v0 ---
        "num_vc_backers": (vc or {}).get("num_backers"),
        "had_public_sale": (vc or {}).get("had_public_sale"),
        # --- informational (not scored): raw market snapshot for display ---
        "_market": {
            "price": market.get("current_price"),
            "market_cap": mc,
            "fdv": market.get("fully_diluted_valuation"),
            "volume_24h": volume,
            "circulating_supply": circ,
            "total_supply": total,
            "ath_change_pct": market.get("ath_change_percentage"),
            "price_change_24h_pct": market.get("price_change_percentage_24h"),
        },
    }


def _safe(call: Callable[[], Any]) -> Any | None:
    """Run a network call, swallowing 4xx/transport errors into None. Kept for
    the module-level helpers; the Collector uses `_try` so failures are logged
    rather than silently dropped."""
    try:
        return call()
    except Exception:
        return None


def _is_not_found(exc: Exception) -> bool:
    """An expected 'this token isn't tracked here' miss, not a real failure.

    Covers HTTP 404/400 (e.g. CryptoRank 404, DefiLlama 400 for an unavailable
    dataType) and Santiment's 'not an existing slug' GraphQL error. Genuine
    failures (429/5xx exhausted → RuntimeError, timeouts) are NOT not-found.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (400, 404)
    msg = str(exc).lower()
    return "not an existing slug" in msg or "not found" in msg


def _feed_status(configured: bool, value: Any, errored: bool) -> str:
    """One feed's outcome for the per-token diagnostics: off / error / empty / ok."""
    if not configured:
        return "off"
    if errored:
        return "error"
    return "ok" if value not in (None, [], {}) else "empty"


class Collector:
    """Fetches live data for a set of targets and emits scoring records.

    Records carry a `_feeds` map (source → off|error|empty|ok) and the run's
    `errors` list is populated so failures are visible, not silently dropped.
    """

    def __init__(self, config: dict | None = None, *, use_cache: bool = True) -> None:
        self.config = config if config is not None else load_config()
        self.cg = CoinGeckoClient(self.config, use_cache=use_cache)
        self.dl = DefiLlamaClient(self.config, use_cache=use_cache)
        self.gh = GitHubClient(self.config, use_cache=use_cache)
        self.san = SantimentClient(self.config, use_cache=use_cache)
        self.cr = CryptoRankClient(self.config, use_cache=use_cache)
        self.eth = EthplorerClient(self.config, use_cache=use_cache)
        self.sf = SourcifyClient(self.config, use_cache=use_cache)
        self._has_santiment_key = bool(get_settings().santiment_api_key)
        self.errors: list[dict[str, str]] = []

    def _try(self, source: str, token: str, fn: Callable[[], Any]) -> Any | None:
        """Run a fetch. A genuine failure (rate-limit, 5xx, timeout) is logged to
        `self.errors` (→ red); an expected 'not tracked here' (404/400, unknown
        slug) is treated as no-data (→ empty), not an error."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not _is_not_found(exc):
                self.errors.append({"token": token, "source": source,
                                    "error": f"{type(exc).__name__}: {exc}"})
            return None

    def _errored(self, token: str, source: str) -> bool:
        return any(e["token"] == token and e["source"] == source for e in self.errors)

    def _santiment_growth(self, token: str, slug: str) -> dict[str, float | None]:
        """Fetch Santiment series for one slug and reduce to growth signals.

        active-address growth + dev-activity trend are free/anonymous; social
        volume needs a key, so it's only attempted when one is configured.

        The window is rounded to UTC midnight: a `now()`-based window changes
        every call, which both defeats the on-disk cache (the free tier is
        1000 calls/month) and makes `dev_commit_trend` drift between runs with
        no underlying data change.
        """
        slug = SLUG_OVERRIDES.get(slug, slug)
        to = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        frm = to - timedelta(days=_SANTIMENT_WINDOW_DAYS)
        fi, ti = frm.isoformat(), to.isoformat()

        def growth(series):
            if not series:
                return None
            return onchain.series_growth([p.get("value") for p in series])

        daa = self._try("santiment", token, lambda: self.san.daily_active_addresses(slug, fi, ti))
        dev = self._try("santiment", token, lambda: self.san.dev_activity(slug, fi, ti))
        social = (
            self._try("santiment", token, lambda: self.san.social_volume(slug, fi, ti))
            if self._has_santiment_key else None
        )
        return {
            "address_growth": growth(daa),
            "dev_commit_trend": growth(dev),
            "social_trend": growth(social),
        }

    def collect(self, targets: list[Target] | None = None) -> list[dict[str, Any]]:
        targets = targets if targets is not None else DEFI_TARGETS
        self.errors = []

        market_rows = self._try("coingecko", "*", lambda: self.cg.markets([t.gecko_id for t in targets]))
        if not market_rows:  # markets is the backbone — without it there's nothing to score
            return []
        markets = {m["id"]: m for m in market_rows}

        records: list[dict[str, Any]] = []
        for target in targets:
            tok = target.gecko_id
            market = markets.get(tok)
            if market is None:
                self.errors.append({"token": tok, "source": "coingecko",
                                    "error": "no market data"})
                continue

            fees = revenue = holders_rev = tvl = unlock = last_push = None
            if target.defillama_slug:
                slug = target.defillama_slug
                fees = self._try("defillama", tok, lambda s=slug: self.dl.fees_summary(s))
                revenue = self._try("defillama", tok, lambda s=slug: self.dl.fees_summary(s, "dailyRevenue"))
                holders_rev = self._try("defillama", tok, lambda s=slug: self.dl.fees_summary(s, "dailyHoldersRevenue"))
                tvl = self._try("defillama", tok, lambda s=slug: self.dl.tvl(s))
                if self.dl.has_pro:  # Pro-only emissions endpoint
                    unlock = self._try("defillama", tok, lambda s=slug: parse_unlock(self.dl.emissions(s), market))

            if target.github_org:
                last_push = self._try("github", tok, lambda o=target.github_org: self.gh.org_latest_push(o))

            santiment = self._santiment_growth(tok, target.santiment_slug) if target.santiment_slug else {}

            # Unlock overhang + VC backing via CryptoRank v0 (open, no key)
            overhang = None
            vc = {}
            if target.cryptorank_key:
                coin = self._try("cryptorank", tok, lambda k=target.cryptorank_key: self.cr.coin(k))
                if coin:
                    overhang = tokenomics.unlock_overhang(
                        coin.get("availableSupply"), coin.get("maxSupply"), coin.get("hasVesting"))
                    vc = vc_backing(coin)

            # CoinGecko coin meta: coarse social sentiment + categories (for class).
            meta = self._try("coingecko", tok, lambda t=tok: self.cg.coin_meta(t)) or {}
            sentiment_pct = meta.get("sentiment")
            social_sentiment = sentiment_pct / 100.0 if sentiment_pct is not None else None
            categories = meta.get("categories") or []
            asset_class = classify_asset(
                gecko_id=tok, coingecko_categories=categories,
                defillama_category=target.category,
                has_fees=bool(fees or revenue or tvl),
                price=market.get("current_price"),
            )

            # Holder concentration (Ethplorer) + contract verification (Sourcify),
            # both Ethereum-only. NOTE: distinct var from DefiLlama holders_rev.
            eth_holders = top10 = contract_verified = None
            if target.eth_contract:
                eth_holders = self._try("ethplorer", tok, lambda a=target.eth_contract: self.eth.top_token_holders(a, 100))
                top10 = holder_concentration(eth_holders)
                contract_verified = self._try("sourcify", tok, lambda a=target.eth_contract: self.sf.is_verified(a))

            record = build_record(
                tok, market,
                fees=fees, revenue=revenue, holders_revenue=holders_rev, tvl=tvl,
                last_push_iso=last_push, unlock=unlock,
                address_growth=santiment.get("address_growth"),
                dev_commit_trend=santiment.get("dev_commit_trend"),
                social_trend=santiment.get("social_trend"),
                unlock_overhang=overhang,
                top10_concentration=top10,
                contract_verified=contract_verified,
                social_sentiment=social_sentiment,
                vc=vc,
            )
            record["_group"] = target.category  # peer group for category-relative scoring
            record["_class"] = asset_class       # asset-class-aware scoring profile
            record["_categories"] = categories[:6]
            record["_feeds"] = {
                "coingecko": "ok",
                "defillama": _feed_status(bool(target.defillama_slug), fees or tvl, self._errored(tok, "defillama")),
                "cryptorank": _feed_status(bool(target.cryptorank_key), overhang, self._errored(tok, "cryptorank")),
                "ethplorer": _feed_status(bool(target.eth_contract), eth_holders, self._errored(tok, "ethplorer")),
                "sourcify": _feed_status(bool(target.eth_contract), contract_verified, self._errored(tok, "sourcify")),
                "santiment": _feed_status(bool(target.santiment_slug), santiment.get("address_growth"), self._errored(tok, "santiment")),
                "github": _feed_status(bool(target.github_org), last_push, self._errored(tok, "github")),
            }
            records.append(record)
        return records

    def close(self) -> None:
        for client in (self.cg, self.dl, self.gh, self.san, self.cr, self.eth, self.sf):
            client.close()

    def __enter__(self) -> "Collector":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
