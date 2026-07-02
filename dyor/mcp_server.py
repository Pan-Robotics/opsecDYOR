"""DYOR MCP server — token qualification as agent-callable tools.

Exposes DYOR's scorer over the Model Context Protocol so an AI agent (Claude
Desktop/Code, Cursor, Manus, …) doing token research can get an opinionated,
asset-class-aware, *gated* assessment instead of scraping raw data.

Run:
    dyor-mcp                      # stdio (Claude Desktop / Claude Code)
    dyor-mcp --transport sse --port 8848        # remote agents over HTTP/SSE
    dyor-mcp --transport streamable-http --port 8848

Register (Claude Code):
    claude mcp add dyor -- dyor-mcp
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from dyor.api.serialize import (
    analyze_to_dict,
    class_to_dict,
    resolved_to_dict,
    score_to_dict,
)

# DNS-rebinding protection stays ON, but allow the hosted deployment's public
# host/origin in addition to loopback — so the server can sit behind nginx at
# https://dyor.cryptoopsec.com/mcp without the reverse proxy having to spoof a
# loopback Host header. Override DYOR_MCP_HOST to point at a different domain.
import os

_PUBLIC_HOST = os.environ.get("DYOR_MCP_HOST", "dyor.cryptoopsec.com")
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[_PUBLIC_HOST, "127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=[
        f"https://{_PUBLIC_HOST}",
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ],
)

INSTRUCTIONS = (
    "DYOR scores crypto tokens on the dimensions that matter for their asset class "
    "(DeFi protocols on fees/revenue/TVL, monetary assets on scarcity/adoption, "
    "memecoins on distribution/social, etc.), normalizes across peers, then applies "
    "hard disqualifier gates. Use `analyze_token` to vet a specific token by name, "
    "symbol, or contract address (it resolves cross-chain). Scores are a research "
    "aid, NOT financial advice — always present the tier/flags as analysis, not a "
    "buy/sell call."
)

mcp = FastMCP("dyor", instructions=INSTRUCTIONS, transport_security=_TRANSPORT_SECURITY)


def _trim_analysis(d: dict[str, Any], peer_limit: int = 8) -> dict[str, Any]:
    """Keep the agent's context lean: cap the peer list."""
    if d.get("peers"):
        d["peers"] = d["peers"][:peer_limit]
    return d


@mcp.tool()
def analyze_token(query: str, peer_mode: str = "stored",
                  penalize_missing_core: bool | None = None) -> dict[str, Any]:
    """Vet ONE crypto token. Resolve it by name ("Aave"), symbol ("UNI"), or
    contract address (any chain — resolves the unified token cross-chain), then
    score it.

    Returns: the resolved identity (+ all chains), asset class, a 0–1 score and
    tier (A high-conviction → D avoid), gate flags (e.g. dead_token, extreme
    FDV/MCAP), non-fatal advisories, per-domain scores, a market snapshot, data
    coverage, feed status, and the ranked peer set the score is relative to.

    peer_mode: "stored" (last saved universe), "sample" (built-in set), or
    "category" (live top-6 of the token's own category — slower, fairest).
    penalize_missing_core: floor a DeFi token's score if it has no
    fees/revenue/TVL data (default = config). This is a research aid, not advice.
    """
    from dyor.analyze import analyze_token as _analyze

    res = _analyze(query, peer_mode=peer_mode, penalize_missing_core=penalize_missing_core)
    if res.resolved is None:
        return {"error": f"could not resolve '{query}' to a token",
                "hint": "try a different name, ticker symbol, or contract address",
                "details": res.errors}
    return _trim_analysis(analyze_to_dict(res))


@mcp.tool()
def resolve_token(query: str) -> dict[str, Any]:
    """Resolve a name/symbol/contract-address to a token's canonical identity
    WITHOUT scoring it (fast). Returns gecko_id, symbol, every chain it's deployed
    on with addresses, block-explorer links, and project links. Useful to confirm
    you've got the right token (e.g. avoiding a memecoin with a hijacked ticker)
    before a deeper look."""
    from dyor.resolve import resolve_query

    r = resolve_query(query)
    if r is None:
        return {"error": f"could not resolve '{query}'"}
    return resolved_to_dict(r)


@mcp.tool()
def compare_tokens(queries: list[str], peer_mode: str = "stored") -> dict[str, Any]:
    """Analyze and compare several tokens at once. Pass a list of names/symbols/
    addresses. Returns a compact ranked summary (token, class, score, tier,
    coverage, flags) — for a quick like-for-like read. Use `analyze_token` for the
    full report on any one of them."""
    from dyor.analyze import analyze_token as _analyze

    rows = []
    for q in queries[:10]:
        res = _analyze(q, peer_mode=peer_mode)
        if res.resolved is None:
            rows.append({"query": q, "error": "unresolved"})
            continue
        s = res.result
        rows.append({
            "query": q, "name": res.resolved.name, "symbol": res.resolved.symbol,
            "class": res.record.get("_class") if res.record else None,
            "score": None if s is None else score_to_dict(s)["final_score"],
            "tier": None if s is None else s.tier,
            "coverage": None if s is None else score_to_dict(s)["coverage"],
            "flags": [] if s is None else list(s.flags),
        })
    rows.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    return {"compared": len(rows), "ranked": rows}


@mcp.tool()
def analyst_memo(query: str, peer_mode: str = "class") -> dict[str, Any]:
    """Generate a reasoned analyst memo for a token — verdict, what drove the
    score, risks, the framework's "break your thesis" questions answered WITH the
    data, and a confidence caveat. Use this when you want a defensible write-up,
    not just a tier. Returns markdown text. (Research aid, not financial advice.)"""
    from dyor.memo import analyst_memo as _memo

    return {"query": query, "memo": _memo(query, peer_mode=peer_mode)}


@mcp.tool()
def screen_tokens(
    asset_class: str | None = None, min_tier: str | None = None,
    min_score: float | None = None, no_flags: bool = False,
    min_real_yield: float | None = None, max_fdv_mcap: float | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Screen the saved universe by criteria — e.g. asset_class="defi", min_tier="B",
    min_real_yield=0.045 (4.5%), no_flags=true. Returns matching tokens ranked
    high→low. Build/refresh the universe with `dyor collect --top-n N --persist`."""
    from dyor.screen import screen
    from dyor.store import db

    con = db.connect()
    try:
        records = db.latest_records(con)
    finally:
        con.close()
    fmin = {"real_yield": min_real_yield} if min_real_yield is not None else None
    fmax = {"fdv_mcap_ratio": max_fdv_mcap} if max_fdv_mcap is not None else None
    rows = screen(records, asset_class=asset_class, min_tier=min_tier, min_score=min_score,
                  no_flags=no_flags, feature_min=fmin, feature_max=fmax, limit=limit)
    return {"matched": len(rows), "results": rows, "universe_size": len(records)}


@mcp.tool()
def score_portfolio(tokens: list[str], peer_mode: str = "class") -> dict[str, Any]:
    """Score a portfolio of holdings (names/symbols/addresses). Returns tier
    distribution, asset-class exposure, average score, gate-flagged holdings, and
    barbell-heuristic notes (is there a monetary anchor? over-diversified?)."""
    from dyor.portfolio import score_portfolio as _sp

    return _sp(tokens, peer_mode=peer_mode)


@mcp.tool()
def build_barbell(n_satellites: int = 5) -> dict[str, Any]:
    """Build the thesis' Barbell: a BTC monetary anchor + the top-N ungated,
    A/B-tier satellites from the saved universe. Concentrate, don't over-diversify."""
    from dyor.portfolio import barbell

    return barbell(n_satellites=n_satellites)


@mcp.tool()
def backtest() -> dict[str, Any]:
    """Does the tier predict forward returns? Computes per-tier average forward
    return + win-rate from persisted runs (entry price at collection → now). Small
    sample early; compounds as `dyor refresh` runs accumulate."""
    from dyor.backtest import backtest as _bt

    return _bt()


@mcp.tool()
def narratives(by: str = "market_cap_change_24h", top: int = 20) -> dict[str, Any]:
    """Which crypto sectors/narratives are heating up. Ranks CoinGecko's 700+
    categories by `by` = "market_cap_change_24h" (momentum), "market_cap", or
    "volume_24h". Returns each sector's name, 24h change, market cap, volume, and
    top coins — for spotting capital rotation early."""
    from dyor.narratives import fetch_narratives

    return {"by": by, "rows": fetch_narratives(by=by, top=top)}


@mcp.tool()
def asset_classes() -> dict[str, Any]:
    """List DYOR's asset classes and what each is judged on — so you can explain
    WHY a token scored the way it did (e.g. Bitcoin has no 'fundamental' domain:
    it's not penalized for lacking protocol revenue)."""
    from dyor.classes import LABELS

    return {"classes": [class_to_dict(name) for name in LABELS if name != "general"]}


@mcp.tool()
def methodology() -> dict[str, Any]:
    """How DYOR scores: domain weights, tier thresholds, the hard disqualifier
    gates, the treasury hurdle, and the metric glossary. Use this to cite or
    explain the scoring transparently."""
    from dyor.app.copy import DOMAIN_META, FEATURE_META
    from dyor.config import load_config

    cfg = load_config()
    return {
        "weights": cfg["scoring"]["weights"],
        "tiers": cfg["scoring"]["tiers"],
        "gates": cfg["gating"]["rules"],
        "reference": cfg["reference"],
        "domains": {k: {"label": v[0], "description": v[1]} for k, v in DOMAIN_META.items()},
        "glossary": [{"key": k, "label": v[0], "meaning": v[1], "direction": v[2]}
                     for k, v in FEATURE_META.items()],
        "disclaimer": "Research aid, not financial advice.",
    }


def main() -> None:
    """Console entry point. Default stdio; --transport sse|streamable-http for HTTP."""
    argv = sys.argv[1:]
    transport = "stdio"
    if "--transport" in argv:
        transport = argv[argv.index("--transport") + 1]
    if "--port" in argv:
        mcp.settings.port = int(argv[argv.index("--port") + 1])
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
