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

from dyor.config import get_settings, load_config, redact_secrets
from dyor.ingestion.coingecko import CoinGeckoClient
from dyor.ingestion.cryptorank import CryptoRankClient
from dyor.ingestion.defillama import DefiLlamaClient
from dyor.ingestion.ethplorer import EthplorerClient
from dyor.ingestion.github import GitHubClient
from dyor.ingestion.santiment import SLUG_OVERRIDES, SantimentClient, resolve_slug_map
from dyor.ingestion.sourcify import SourcifyClient
from dyor.classes import classify_asset
from dyor.metrics import onchain, tokenomics, valuation

# Santiment free/anonymous history is limited to ~30 days; stay inside it.
# Default span of the Santiment series (config `ingestion.sources.santiment.
# window_days` overrides). The growth reduction compares first and last thirds,
# so 90 days → 30-day means; the 28-day window (9-day means) it replaced turned
# month-scale noise into score moves (2026-09-27).
_SANTIMENT_WINDOW_DAYS = 90


def santiment_window_days(config: dict | None = None) -> int:
    cfg = config if config is not None else load_config()
    try:
        return int(cfg["ingestion"]["sources"]["santiment"].get("window_days", _SANTIMENT_WINDOW_DAYS))
    except (KeyError, TypeError, ValueError):
        return _SANTIMENT_WINDOW_DAYS


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
    # --- added 2026-09 so every token gets as many feeds as free data allows ---
    chain_name: str | None = None        # DefiLlama chain → chain-level fees/revenue/TVL (L1s)
    verify_chain_id: int | None = None   # Sourcify: first deployment on a supported chain
    verify_address: str | None = None
    audits: str | None = None            # DefiLlama audit count ("0" = explicitly none on record)
    has_audit_links: bool = False
    # top version of a folded parent protocol — tried when the parent slug
    # serves neither fees nor TVL (a few umbrellas, e.g. bonkfun, answer 400).
    # Last on purpose: callers build Targets positionally.
    defillama_fallback_slug: str | None = None


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
_WINDOW_DAYS = {"total1y": 365, "total30d": 30, "total7d": 7, "total24h": 1}


def annualized_detail(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """`annualized` with its working, for the report's math ledger:
    {window, days, total, annualized}. None when nothing usable is present."""
    if not isinstance(summary, dict):  # DefiLlama returns [] for absent dataTypes
        return None
    for key in _WINDOWS:
        value = summary.get(key)
        if value:
            return {"window": key, "days": _WINDOW_DAYS[key], "total": value,
                    "annualized": value * _ANNUALIZE[key]}
    return None


def annualized(summary: dict[str, Any] | None) -> float | None:
    """Annualize a DefiLlama fees/revenue summary, preferring longer windows.

    total1y is used as-is; otherwise the shortest available window is scaled up.
    Returns None if the summary is missing or carries no usable total.
    """
    d = annualized_detail(summary)
    return None if d is None else d["annualized"]


def same_window_pair(
    num_summary: dict[str, Any] | None, den_summary: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    """Pick (numerator, denominator) from the SAME time window present in both.

    Ratios between two DefiLlama summaries (e.g. holders-revenue ÷ revenue) must
    use one window — annualizing each independently can pair a `total1y` with a
    `total30d` and distort the result. Returns (None, None) if no shared window
    has a usable denominator.
    """
    num, den, _ = same_window_pair_detail(num_summary, den_summary)
    return num, den


def same_window_pair_detail(
    num_summary: dict[str, Any] | None, den_summary: dict[str, Any] | None
) -> tuple[float | None, float | None, str | None]:
    """`same_window_pair` plus WHICH window was shared, for the math ledger."""
    if not isinstance(num_summary, dict) or not isinstance(den_summary, dict):
        return None, None, None
    for w in _WINDOWS:
        den = den_summary.get(w)
        if den:
            num = num_summary.get(w)
            if num is not None:
                return num, den, w
    return None, None, None


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
    shares = top_holder_shares(holders, n)
    if not shares:
        return None
    return sum(shares) / 100.0


def top_holder_shares(holders: list[dict[str, Any]] | None, n: int = 10) -> list[float] | None:
    """The top-N holders' individual `share` percentages, largest first — the
    figures `holder_concentration` sums, kept for the report's math ledger."""
    if not holders:
        return None
    return sorted((h.get("share") or 0.0) for h in holders)[::-1][:n]


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
    dev_activity: float | None = None,
    dev_activity_events: float | None = None,
    social_trend: float | None = None,
    unlock_overhang: float | None = None,
    top10_concentration: float | None = None,
    contract_verified: bool | None = None,
    social_sentiment: float | None = None,
    vc: dict[str, Any] | None = None,
    watchlist_users: int | None = None,
    audited: bool | None = None,
    santiment_detail: dict[str, Any] | None = None,
    top10_shares: list[float] | None = None,
    sentiment_votes_up_pct: float | None = None,
    unlock_inputs: dict[str, Any] | None = None,
    github_account: str | None = None,
) -> dict[str, Any]:
    """Pure transform: raw API payloads → one scoring record.

    `market` is a CoinGecko /coins/markets entry. `last_push_iso` is the org's
    most-recent push (GitHub); `unlock` is a parsed unlock summary (Pro/Stage-2).
    `address_growth`/`dev_commit_trend`/`social_trend` are precomputed Santiment
    growth signals. Missing inputs yield None features (skipped downstream),
    never exceptions.

    The record also carries `_inputs`: every raw figure a feature was computed
    from (which fees window, both sides of each ratio, the Santiment window
    means, the holder shares …) so the report can show the working next to the
    result (see dyor/explain.py). `_inputs` is informational — never scored.
    """
    mc = market.get("market_cap")
    circ = market.get("circulating_supply")
    total = market.get("total_supply") or market.get("max_supply")
    volume = market.get("total_volume")

    fees_d = annualized_detail(fees)
    rev_d = annualized_detail(revenue)
    holders_d = annualized_detail(holders_revenue)
    ann_fees = None if fees_d is None else fees_d["annualized"]
    ann_rev = None if rev_d is None else rev_d["annualized"]
    ann_holders = None if holders_d is None else holders_d["annualized"]
    va_num, va_den, va_window = same_window_pair_detail(holders_revenue, revenue)

    # FDV/MCAP from supply ratio (robust); fall back to CoinGecko's FDV/MC.
    fdv_mcap = valuation.fdv_mcap_ratio(total, circ)
    fdv_mcap_method = "supply"
    if fdv_mcap is None:
        fdv_mcap = valuation._safe_div(market.get("fully_diluted_valuation"), mc)
        fdv_mcap_method = "fdv_over_mcap" if fdv_mcap is not None else None

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
        "value_accrual": tokenomics.value_accrual(va_num, va_den),
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
        "watchlist_users": watchlist_users,    # CoinGecko watchlist count (keyless, broad)
        # --- dev ---
        "dev_activity": dev_activity,                  # Santiment mean dev events/day (scored level)
        "dev_commit_trend": dev_commit_trend,          # Santiment dev-activity trend (informational)
        "days_since_last_commit": days_since(last_push_iso),  # GitHub last push (gate)
        "dev_activity_events": dev_activity_events,    # Santiment events in-window (gate corroboration)
        # --- gate inputs derivable from free market data ---
        "daily_volume_usd": volume,
        "drawdown_from_ath_pct": _drawdown_from_ath(market.get("ath_change_percentage")),
        # --- gate input: contract verification (Sourcify; True or None, never False) ---
        "contract_verified": contract_verified,
        # --- gate input: audit on record (DefiLlama; True / explicit False / None) ---
        "audited": audited,
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
        # --- informational (not scored): the raw figures behind each feature ---
        "_inputs": {
            "price": market.get("current_price"),
            "market_cap": mc,
            "fdv": market.get("fully_diluted_valuation"),
            "circulating_supply": circ,
            "total_supply": total,
            "max_supply": market.get("max_supply"),
            "volume_24h": volume,
            "fdv_mcap_method": fdv_mcap_method,
            "fees": fees_d,                      # {window, days, total, annualized}
            "revenue": rev_d,
            "holders_revenue": holders_d,
            "value_accrual_window": {"window": va_window, "holders_revenue": va_num, "revenue": va_den},
            "tvl": tvl,
            "last_push": last_push_iso,
            "github_account": github_account,
            "unlock": {**(unlock_inputs or {}), "next_unlock_usd": unlock.get("next_unlock_usd")},
            "santiment": santiment_detail,       # {window_days, slug, <metric>: {n, k, early_mean, late_mean, growth}}
            "top10_shares_pct": top10_shares,
            "sentiment_votes_up_pct": sentiment_votes_up_pct,
            "watchlist_users": watchlist_users,
            "audited": audited,
        },
    }


def source_links(
    gecko_id: str,
    *,
    defillama_slug: str | None = None,
    chain_name: str | None = None,
    santiment_slug: str | None = None,
    github_account: str | None = None,
    eth_contract: str | None = None,
    verify_address: str | None = None,
    cryptorank_key: str | None = None,
) -> dict[str, str | None]:
    """Where a reader can see each feed's own page for this token — one entry
    per feed in `_feeds`, None when the feed had no identifier to look up."""
    from urllib.parse import quote

    return {
        "coingecko": f"https://www.coingecko.com/en/coins/{quote(gecko_id)}",
        "defillama": (f"https://defillama.com/protocol/{quote(defillama_slug)}" if defillama_slug
                      else f"https://defillama.com/chain/{quote(chain_name)}" if chain_name else None),
        "santiment": f"https://app.santiment.net/charts?slug={quote(santiment_slug)}" if santiment_slug else None,
        "github": f"https://github.com/{quote(github_account)}" if github_account else None,
        "ethplorer": f"https://ethplorer.io/address/{quote(eth_contract)}" if eth_contract else None,
        "sourcify": f"https://sourcify.dev/#/lookup/{quote(verify_address)}" if verify_address else None,
        "cryptorank": f"https://cryptorank.io/price/{quote(cryptorank_key)}" if cryptorank_key else None,
    }


def audited_from_defillama(audits: str | None, has_audit_links: bool) -> bool | None:
    """DefiLlama's audit record → the `no_audit` gate input.

    `audits` is a count as a string. A positive count, or any audit link, is a
    positive signal; an explicit "0" is DefiLlama stating none is on record
    (26 of the top-80 protocols in Sep 2026 — none of them majors). Absence of
    the field stays None: we never infer a negative from missing data.
    """
    if has_audit_links:
        return True
    if audits is None or str(audits).strip() == "":
        return None
    try:
        return int(str(audits)) > 0
    except ValueError:
        return None


def audited_for_class(asset_class: str | None, audits: str | None, has_audit_links: bool) -> bool | None:
    """The `no_audit` gate input, scoped to classes where an audit is an
    expectation. An L1, a monetary asset, a memecoin or a stablecoin is not an
    application protocol; for those the input stays unknown (None) whatever
    DefiLlama's row says."""
    if asset_class not in ("defi", "general"):
        return None
    return audited_from_defillama(audits, has_audit_links)


def github_org_from_repos(repos: list[str] | None) -> str | None:
    """'https://github.com/aave/aave-protocol' → 'aave' (the org)."""
    for url in repos or []:
        parts = url.rstrip("/").split("github.com/")
        if len(parts) == 2 and parts[1]:
            org = parts[1].split("/")[0].strip()
            if org:
                return org
    return None


# gecko_id → canonical GitHub account(s), checked FIRST. CoinGecko's repo URLs
# are whatever was submitted at listing time and DefiLlama's `github` list is
# sparse, so for several majors they point at an org development has since
# left — solana-labs (→ anza-xyz, 2025), centrehq (→ circlefin), binance-exchange
# (→ bnb-chain), balancer-labs (→ balancer), makerdao (→ sky-ecosystem, now an
# empty org), iearn-finance (→ yearn, empty), xvi10 (a founder's user account →
# gmx-io), bloxapp (→ ssvlabs, empty). The first production run with the GitHub
# feed on would have zeroed Solana, USDC and BNB as `dead_token` on that basis.
# Every entry verified live 2026-09-26 (pushed within the prior week;
# bitcoin-cash-node is the GitHub mirror of a GitLab primary, ~2 months).
GITHUB_ACCOUNT_OVERRIDES: dict[str, list[str]] = {
    "solana": ["anza-xyz", "solana-foundation"],
    "usd-coin": ["circlefin"],
    "binancecoin": ["bnb-chain"],
    "balancer": ["balancer"],
    "maker": ["sky-ecosystem"],
    "yearn-finance": ["yearn"],
    "bitcoin-cash": ["bitcoin-cash-node"],
    "gmx": ["gmx-io"],
    "ssv-network": ["ssvlabs"],
}
MAX_GITHUB_ACCOUNTS = 4  # per token per run — bounds the call budget


def github_accounts(gecko_id: str, configured_org: str | None,
                    repos: list[str] | None) -> list[str]:
    """Ordered, de-duplicated GitHub accounts whose most recent push stands for
    the token's dev activity: verified overrides, the configured/DefiLlama org,
    then the account of EVERY CoinGecko repo URL — NEAR lists the dead
    `nearprotocol` first and the live `near` second, so the first URL alone is
    not enough. Case-insensitive de-dupe, capped at `MAX_GITHUB_ACCOUNTS`."""
    cands: list[str | None] = list(GITHUB_ACCOUNT_OVERRIDES.get(gecko_id, [])) + [configured_org]
    for url in repos or []:
        cands.append(github_org_from_repos([url]))
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out[:MAX_GITHUB_ACCOUNTS]


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


def feed_summary(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{feed: {status: count}} across a collection — the per-source view that
    `refresh` prints and `alerts.feed_outage_alerts` reasons over. A source that
    is `error` for most tokens is an outage, and it should look like one."""
    out: dict[str, dict[str, int]] = {}
    for rec in records:
        for feed, status in (rec.get("_feeds") or {}).items():
            bucket = out.setdefault(feed, {})
            bucket[status] = bucket.get(status, 0) + 1
    return out


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
        settings = get_settings()
        self._has_santiment_key = bool(settings.santiment_api_key)
        # Unauthenticated GitHub is 60 requests/HOUR: with no token the feed is
        # off rather than adding a minute of sleep per token to every refresh.
        self._github_enabled = bool(settings.github_token)
        self.errors: list[dict[str, str]] = []
        self.notes: list[str] = []
        if self.cr.disabled_reason:
            self.notes.append(self.cr.disabled_reason)
        if not self._github_enabled:
            self.notes.append("GitHub feed is off — set DYOR_GITHUB_TOKEN (free) to enable "
                              "days_since_last_commit / the dead_token gate for ~all tokens")
        self._chains: dict[str, dict[str, Any]] | None = None

    def _try(self, source: str, token: str, fn: Callable[[], Any]) -> Any | None:
        """Run a fetch. A genuine failure (rate-limit, 5xx, timeout) is logged to
        `self.errors` (→ red); an expected 'not tracked here' (404/400, unknown
        slug) is treated as no-data (→ empty), not an error."""
        try:
            return fn()
        except Exception as exc:
            if not _is_not_found(exc):
                self.errors.append({"token": token, "source": source,
                                    "error": redact_secrets(f"{type(exc).__name__}: {exc}")})
            return None

    def _errored(self, token: str, source: str) -> bool:
        return any(e["token"] == token and e["source"] == source for e in self.errors)

    def _latest_push(self, token: str, accounts: list[str]) -> tuple[str | None, str | None]:
        """(most recent push ISO, account it came from) across the candidate
        accounts. A stale org that still exists (solana-labs, balancer-labs)
        would otherwise report a live project as dead."""
        best: tuple[str, str] | None = None
        for name in accounts:
            iso = self._try("github", token, lambda n=name: self.gh.account_latest_push(n))
            if iso and (best is None or iso > best[0]):  # GitHub ISO-8601 Z: lexicographic == chronological
                best = (iso, name)
        return best if best else (None, None)

    def _santiment_slugs(self, targets: list[Target]) -> dict[str, str]:
        """gecko_id → best Santiment slug for this run (one cached allProjects
        call + the cached coins_list). Best-effort: any failure → identity map."""
        try:
            projects = self.san.all_projects()
            if not projects:
                return {}
            coins = {c["id"]: c for c in self.cg.coins_list() if c.get("id")}
            return resolve_slug_map(projects, coins, [t.gecko_id for t in targets])
        except Exception as exc:
            self.errors.append({"token": "*", "source": "santiment",
                                "error": redact_secrets(f"slug map: {type(exc).__name__}: {exc}")})
            return {}

    def _chain_tvl(self, chain_name: str) -> float | None:
        """Chain TVL from the cached `/v2/chains` list."""
        if self._chains is None:
            from dyor.universe import chain_index
            try:
                self._chains = {v["name"]: v for v in chain_index(self.dl.chains()).values()}
            except Exception:
                self._chains = {}
        row = self._chains.get(chain_name)
        return row.get("tvl") if row else None

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
        window = santiment_window_days(self.config)
        frm = to - timedelta(days=window)
        fi, ti = frm.isoformat(), to.isoformat()

        def detail(series):
            if not series:
                return None
            return onchain.series_growth_detail([p.get("value") for p in series])

        def total(series):
            if not series:
                return None
            return float(sum((p.get("value") or 0) for p in series))

        daa = self._try("santiment", token, lambda: self.san.daily_active_addresses(slug, fi, ti))
        dev = self._try("santiment", token, lambda: self.san.dev_activity(slug, fi, ti))
        social = (
            self._try("santiment", token, lambda: self.san.social_volume(slug, fi, ti))
            if self._has_santiment_key else None
        )
        daa_d, dev_d, social_d = detail(daa), detail(dev), detail(social)
        dev_events = total(dev)
        if dev_d is not None:
            dev_d = {**dev_d, "events": dev_events}
        return {
            "address_growth": (daa_d or {}).get("growth"),
            # Scored dev signal: the LEVEL of activity (events per day over the
            # window), ranked against class peers. The month-over-month trend is
            # kept for the record but no longer scored — a busy or quiet month is
            # not a signal about a project (2026-09-27).
            "dev_activity": (dev_events / dev_d["n"]) if dev_d and dev_d.get("n") else None,
            "dev_commit_trend": (dev_d or {}).get("growth"),
            # Raw event count over the window: Santiment tracks a curated repo set
            # per project, so events here prove the project is alive even when the
            # GitHub org we discovered has gone quiet (dead_token corroboration).
            "dev_activity_events": dev_events,
            "social_trend": (social_d or {}).get("growth"),
            # The working (window means) for the report's math ledger.
            "_detail": {"window_days": window, "slug": slug,
                        "daily_active_addresses": daa_d, "dev_activity": dev_d,
                        "social_volume": social_d},
        }

    def collect(self, targets: list[Target] | None = None) -> list[dict[str, Any]]:
        targets = targets if targets is not None else DEFI_TARGETS
        self.errors = []

        market_rows = self._try("coingecko", "*", lambda: self.cg.markets([t.gecko_id for t in targets]))
        if not market_rows:  # markets is the backbone — without it there's nothing to score
            return []
        markets = {m["id"]: m for m in market_rows}
        san_slugs = self._santiment_slugs(targets) if any(t.santiment_slug for t in targets) else {}

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
                    unlock = self._try("defillama", tok,
                                       lambda s=slug, m=market: parse_unlock(self.dl.emissions(s), m))
            if tvl is not None and tvl <= 0:
                tvl = None  # a zero-TVL stub row (foundation, bridge) must not block the fallbacks
            # A parent slug that serves nothing at all → its top version instead
            # (never mixed: parent fees with a version's TVL would be two products).
            if (target.defillama_fallback_slug and fees is None and revenue is None
                    and holders_rev is None and tvl is None):
                fb = target.defillama_fallback_slug
                fees = self._try("defillama", tok, lambda s=fb: self.dl.fees_summary(s))
                revenue = self._try("defillama", tok, lambda s=fb: self.dl.fees_summary(s, "dailyRevenue"))
                holders_rev = self._try("defillama", tok, lambda s=fb: self.dl.fees_summary(s, "dailyHoldersRevenue"))
                tvl = self._try("defillama", tok, lambda s=fb: self.dl.tvl(s))

            # Chain-level fallback, PER FIELD: an L1's product IS the chain. A chain
            # may also appear as a "protocol" row that returns fees but no TVL, so
            # each of fees / revenue / TVL falls back to the chain-wide figure on
            # its own (all-or-nothing left L1 mc_tvl at 5/16).
            if target.chain_name:
                cn = target.chain_name
                if fees is None:
                    fees = self._try("defillama", tok, lambda c=cn: self.dl.chain_fees_summary(c))
                if revenue is None:
                    revenue = self._try("defillama", tok, lambda c=cn: self.dl.chain_fees_summary(c, "dailyRevenue"))
                if tvl is None:
                    tvl = self._try("defillama", tok, lambda c=cn: self._chain_tvl(c))

            # CoinGecko coin meta: sentiment, categories, TVL fallback, watchlist,
            # GitHub repos — one call. Fetched before GitHub so the repo list can
            # supply an org for tokens that have none configured.
            meta = self._try("coingecko", tok, lambda t=tok: self.cg.coin_meta(t)) or {}
            if tvl is None and meta.get("tvl_usd"):
                tvl = meta["tvl_usd"]

            gh_accounts = github_accounts(tok, target.github_org, meta.get("github_repos"))
            gh_on = bool(gh_accounts) and self._github_enabled
            gh_account = None
            if gh_on:
                last_push, gh_account = self._latest_push(tok, gh_accounts)

            san_slug = san_slugs.get(tok) or (SLUG_OVERRIDES.get(target.santiment_slug, target.santiment_slug)
                                              if target.santiment_slug else None)
            santiment = self._santiment_growth(tok, san_slug) if san_slug else {}

            # Unlock overhang + VC backing via CryptoRank (v0 open path is dead
            # since 2026-09 and disabled in config; a key re-enables via v3).
            overhang = None
            unlock_inputs = None
            vc = {}
            cr_on = bool(target.cryptorank_key) and self.cr.enabled
            if cr_on:
                coin = self._try("cryptorank", tok, lambda k=target.cryptorank_key: self.cr.coin(k))
                if coin:
                    unlock_inputs = {"available_supply": coin.get("availableSupply"),
                                     "max_supply": coin.get("maxSupply"),
                                     "has_vesting": coin.get("hasVesting")}
                    overhang = tokenomics.unlock_overhang(
                        coin.get("availableSupply"), coin.get("maxSupply"), coin.get("hasVesting"))
                    vc = vc_backing(coin)
                    # CryptoRank Pro exposes the next unlock's USD value — the
                    # precise `unlock_pct_of_volume` input otherwise gated behind
                    # DefiLlama Pro. DefiLlama wins if both are configured.
                    if unlock is None and coin.get("nextUnlockUsd"):
                        unlock = {"next_unlock_usd": float(coin["nextUnlockUsd"])}

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
            eth_holders = top10 = top10_shares = contract_verified = None
            if target.eth_contract:
                eth_holders = self._try("ethplorer", tok, lambda a=target.eth_contract: self.eth.top_token_holders(a, 100))
                top10 = holder_concentration(eth_holders)
                top10_shares = top_holder_shares(eth_holders)
            # Sourcify covers many EVM chains; verify the first supported deployment
            # (Ethereum if there is one, else Arbitrum/Base/OP/Polygon/BSC/Avalanche).
            v_chain, v_addr = target.verify_chain_id, target.verify_address
            if not v_addr and target.eth_contract:
                v_chain, v_addr = 1, target.eth_contract
            if v_addr:
                contract_verified = self._try("sourcify", tok,
                                              lambda a=v_addr, c=v_chain: self.sf.is_verified(a, c))

            record = build_record(
                tok, market,
                fees=fees, revenue=revenue, holders_revenue=holders_rev, tvl=tvl,
                last_push_iso=last_push, unlock=unlock,
                address_growth=santiment.get("address_growth"),
                dev_commit_trend=santiment.get("dev_commit_trend"),
                dev_activity=santiment.get("dev_activity"),
                dev_activity_events=santiment.get("dev_activity_events"),
                social_trend=santiment.get("social_trend"),
                unlock_overhang=overhang,
                top10_concentration=top10,
                contract_verified=contract_verified,
                social_sentiment=social_sentiment,
                vc=vc,
                watchlist_users=meta.get("watchlist_users"),
                audited=audited_for_class(asset_class, target.audits, target.has_audit_links),
                santiment_detail=santiment.get("_detail"),
                top10_shares=top10_shares,
                sentiment_votes_up_pct=sentiment_pct,
                unlock_inputs=unlock_inputs,
                github_account=gh_account,
            )
            record["_group"] = target.category  # peer group for category-relative scoring
            record["_class"] = asset_class       # asset-class-aware scoring profile
            record["_categories"] = categories[:6]
            record["_github_account"] = gh_account  # which account the last push came from
            record["_sources"] = source_links(
                tok, defillama_slug=target.defillama_slug, chain_name=target.chain_name,
                santiment_slug=san_slug, github_account=gh_account or (gh_accounts[0] if gh_accounts else None),
                eth_contract=target.eth_contract, verify_address=v_addr,
                cryptorank_key=target.cryptorank_key if cr_on else None,
            )
            record["_feeds"] = {
                "coingecko": "ok",
                "defillama": _feed_status(bool(target.defillama_slug or target.chain_name), fees or tvl, self._errored(tok, "defillama")),
                "cryptorank": _feed_status(cr_on, overhang, self._errored(tok, "cryptorank")),
                "ethplorer": _feed_status(bool(target.eth_contract), eth_holders, self._errored(tok, "ethplorer")),
                "sourcify": _feed_status(bool(v_addr), contract_verified, self._errored(tok, "sourcify")),
                "santiment": _feed_status(bool(san_slug), santiment.get("address_growth"), self._errored(tok, "santiment")),
                "github": _feed_status(gh_on, last_push, self._errored(tok, "github")),
            }
            records.append(record)
        return records

    def close(self) -> None:
        for client in (self.cg, self.dl, self.gh, self.san, self.cr, self.eth, self.sf):
            client.close()

    def __enter__(self) -> Collector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
