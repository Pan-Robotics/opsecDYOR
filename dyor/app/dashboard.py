"""DYOR — Crypto Token Qualification, as a guided web app.

    streamlit run dyor/app/dashboard.py

A multi-page Streamlit app with a clear flow:
    Home → Screener → Token detail → Narratives → Methodology

Every view carries copy explaining what it shows and why it matters. Live data
fetches are gated behind explicit widgets, so a headless smoke render
(`main()` in bare mode) never touches the network.
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from dyor.app.copy import (
    BREAK_THESIS,
    DOMAIN_META,
    FEATURE_META,
    tier_badge,
    tier_color,
)
from dyor.config import load_config
from dyor.pipeline import FEATURE_SPEC, score_universe
from dyor.sample_data import SAMPLE_UNIVERSE

ALL_FEATURES = [f for feats in FEATURE_SPEC.values() for f, _ in feats]
SOURCES = ["Sample", "Live (DeFi universe)", "Stored (DuckDB)"]
PAGES = ["🏠 Home", "🔍 Analyze", "📊 Screener", "🔎 Token detail", "🔥 Narratives", "📖 Methodology"]


# ==========================================================================
# Data loading (cached; live fetches only run when a user opts in)
# ==========================================================================
@st.cache_data(ttl=900, show_spinner="Fetching DefiLlama + CoinGecko + CryptoRank + Ethplorer + Santiment…")
def _collect_live() -> list[dict]:
    from dyor.collect import Collector

    with Collector() as collector:
        return collector.collect()


def _load_stored() -> list[dict]:
    from dyor.store import db

    con = db.connect()
    try:
        return db.latest_records(con)
    finally:
        con.close()


def load_records(source: str) -> list[dict]:
    if source == "Live (DeFi universe)":
        return _collect_live()
    if source == "Stored (DuckDB)":
        return _load_stored()
    return SAMPLE_UNIVERSE


@st.cache_data(ttl=900, show_spinner="Fetching CoinGecko categories…")
def _fetch_narratives(by: str) -> list[dict]:
    from dyor.narratives import fetch_narratives

    return fetch_narratives(by=by, top=30)


@st.cache_data(ttl=300)
def _score_history(token: str, peer_groups: bool) -> list[tuple[str, float]]:
    """Token's final-score trajectory across persisted runs (re-scored)."""
    from dyor.history import score_history
    from dyor.store import db

    con = db.connect()
    try:
        return [(str(at), s) for at, s in score_history(con, token, peer_groups=peer_groups)]
    finally:
        con.close()


def _clean(x) -> float | None:
    return None if (x is None or (isinstance(x, float) and math.isnan(x))) else round(x, 3)


def _usd(v) -> str:
    if v is None:
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"${v / div:,.2f}{unit}"
    return f"${v:,.2f}"


def _num(v) -> str:
    if v is None:
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"{v / div:,.2f}{unit}"
    return f"{v:,.0f}"


def _source() -> str:
    return st.session_state.get("source", "Sample")


def _peer_groups() -> bool:
    return st.session_state.get("peer_groups", False)


def _penalize() -> bool:
    return st.session_state.get("penalize_core", True)


# ==========================================================================
# Pages
# ==========================================================================
def page_home(cfg: dict) -> None:
    st.title("DYOR — Crypto Token Qualification")
    st.subheader("A flight-to-fundamentals scorer for crypto tokens")
    st.markdown(
        "The 2021 playbook — where a rising tide lifted every memecoin — is over. "
        "Capital now rewards tokens with **real revenue, durable tokenomics, and "
        "actual usage**. DYOR turns that thesis into a repeatable, data-driven "
        "score so a fatal flaw can't hide behind one good number."
    )

    st.divider()
    st.markdown("#### How it works")
    steps = [
        ("1 · Ingest", "Pull live data from free / open sources — DefiLlama, CoinGecko, CryptoRank, Ethplorer, Santiment, GitHub."),
        ("2 · Resolve", "Tie every token to one identity on `chain:address` so signals join cleanly across sources."),
        ("3 · Measure", "Compute derived metrics: P/F, P/S, FDV/MCAP, token-sink, unlock overhang, holder concentration, growth."),
        ("4 · Score", "Normalize each signal across peers, weight by domain, then **gate** — hard red flags cap or zero the score."),
        ("5 · Rank", "Map the final 0–1 score to a tier: A (high conviction) → D (avoid)."),
    ]
    cols = st.columns(len(steps))
    for col, (head, body) in zip(cols, steps):
        with col:
            st.markdown(f"**{head}**")
            st.caption(body)

    st.divider()
    st.markdown("#### The five domains")
    for key, (label, desc) in DOMAIN_META.items():
        weight = cfg["scoring"]["weights"].get(key, 0)
        st.markdown(f"- **{label}** ({weight:.0%}) — {desc}")

    st.divider()
    st.markdown("#### The gate — why a flaw can't be averaged away")
    st.markdown(
        "A great revenue multiple shouldn't rescue an unverified contract or a dead "
        "repo. Hard disqualifiers **cap or zero** the score instead of being averaged in:"
    )
    st.caption("unverified contract · anonymous team · no audit · extreme FDV/MCAP · "
               "dead token (no commits 6mo+ or near-zero volume)")

    st.info("**Start here →** open **📊 Screener** in the sidebar. "
            "Tip: the **Stored (DuckDB)** source shows your last live run instantly, offline.")


def _tier_legend() -> None:
    chips = " ".join(
        f":{tier_color(t['label'])}[{t['label']}]" for t in load_config()["scoring"]["tiers"]
    )
    st.markdown("**Tiers:** " + chips)


def page_screener(cfg: dict) -> None:
    st.header("📊 Screener")
    st.caption(
        "Each token is scored **0–1** across five domains, combined by weight, then gated. "
        "Higher = more qualified. **Raw** is before gating; **Final** is after."
    )
    _tier_legend()

    records = load_records(_source())
    results = score_universe(records, cfg, peer_groups=_peer_groups(), penalize_missing_core=_penalize())
    if not results:
        st.info("Nothing to show for this source yet. Run `dyor collect --persist`, "
                "or switch the source to **Sample** in the sidebar.")
        return

    from dyor.classes import class_profile
    rec_by_token = {r.get("token"): r for r in records}
    table = pd.DataFrame([
        {
            "Token": r.token,
            "Class": class_profile(rec_by_token.get(r.token, {}).get("_class")).label,
            "Final": _clean(r.final_score),
            "Raw": _clean(r.raw_score),
            "Coverage": _clean(r.coverage),
            "Tier": r.tier,
            "Flags": ", ".join(r.flags) if r.flags else "—",
            **{f"{DOMAIN_META[k][0]}": _clean(v) for k, v in r.domain_scores.items() if k in DOMAIN_META},
        }
        for r in results
    ])
    st.dataframe(
        table, width="stretch", hide_index=True,
        column_config={
            "Final": st.column_config.ProgressColumn(
                "Final", min_value=0.0, max_value=1.0, format="%.3f"),
            "Coverage": st.column_config.ProgressColumn(
                "Coverage", help="Fraction of scored features with data",
                min_value=0.0, max_value=1.0, format="%.0f%%"),
        },
    )
    st.bar_chart(table.set_index("Token")["Final"].dropna(), height=240)
    st.caption("Domain columns are each token's normalized 0–1 score within that domain. "
               "Open **🔎 Token detail** to see the raw numbers behind a score.")


def page_detail(cfg: dict) -> None:
    st.header("🔎 Token detail")
    records = load_records(_source())
    results = score_universe(records, cfg, peer_groups=_peer_groups(), penalize_missing_core=_penalize())
    if not results:
        st.info("No tokens for this source. Switch to **Sample** in the sidebar.")
        return

    by_token = {r["token"]: r for r in records}
    tokens = [r.token for r in results]
    default = st.session_state.get("detail_token", tokens[0])
    pick = st.selectbox("Token", tokens, index=tokens.index(default) if default in tokens else 0)
    st.session_state["detail_token"] = pick
    result = next(r for r in results if r.token == pick)
    _render_detail(result, by_token.get(pick, {}), cfg)


def _render_detail(result, rec: dict, cfg: dict, *, peer_note: str | None = None) -> None:
    """Shared token visualization — used by Token detail and Analyze."""
    from dyor.classes import class_profile

    verified = rec.get("contract_verified")
    badge = " · :green[✓ source-verified]" if verified else ""
    prof = class_profile(rec.get("_class"))
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.markdown(f"### {result.token}\n{tier_badge(result.tier)}{badge}  ·  :violet[{prof.label}]")
    c1.caption(f"🏷️ {prof.description}")
    c2.metric("Final score", _clean(result.final_score))
    c3.metric("Raw (pre-gate)", _clean(result.raw_score))
    c4.metric("Data coverage", None if math.isnan(result.coverage) else f"{result.coverage:.0%}",
              help=f"{result.features_present} of {result.features_total} scored features present")
    if peer_note:
        st.caption(peer_note)

    if result.flags:
        st.warning("**Gate flags:** " + ", ".join(result.flags)
                   + " — these capped or zeroed the score.")
    else:
        st.success("No gate flags — passed all hard disqualifiers.")
    for note in result.advisories:
        st.info("⚠ " + note)

    nb = rec.get("num_vc_backers")
    if nb is not None:
        sale = " · had public sale" if rec.get("had_public_sale") else ""
        st.caption(f"🏦 VC backers: **{nb}**{sale} _(CryptoRank — informational, not scored)_")

    hist = _score_history(result.token, _peer_groups())
    if len(hist) >= 2:
        st.markdown("#### Score history")
        st.caption("Final score across persisted `dyor collect --persist` runs.")
        st.line_chart(pd.DataFrame(hist, columns=["run", "score"]).set_index("run"), height=200)

    feeds = rec.get("_feeds")
    if feeds:
        icon = {"ok": "🟢", "empty": "⚪", "error": "🔴", "off": "⚫"}
        chips = "  ".join(f"{icon.get(v, '?')} {k}" for k, v in feeds.items())
        st.caption("Feeds — 🟢 data · ⚪ no data · 🔴 error · ⚫ not configured")
        st.markdown(chips)

    st.divider()
    st.markdown("#### Domain scores")
    st.caption("Normalized 0–1 within each domain vs. the peer set. Missing domains are skipped.")
    dom = pd.Series({DOMAIN_META[k][0]: _clean(v)
                     for k, v in result.domain_scores.items() if k in DOMAIN_META}).dropna()
    st.bar_chart(dom, height=220)

    st.divider()
    st.markdown("#### The numbers behind it")
    rows = []
    for feat in ALL_FEATURES:
        if feat not in rec or rec[feat] is None:
            continue
        label, desc, direction = FEATURE_META.get(feat, (feat, "", "higher"))
        arrow = "↓ better" if direction == "lower" else "↑ better"
        rows.append({"Metric": label, "Value": round(rec[feat], 4), "Good when": arrow, "What it means": desc})
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("No raw feature values on this record.")

    st.divider()
    st.markdown("#### 🧠 Break your thesis")
    st.caption("Before conviction, try to kill the idea. The framework's stress-test:")
    for q in BREAK_THESIS:
        st.markdown(f"- {q}")


_PEER_MODES = {
    "Last saved run": "stored",
    "Sample set": "sample",
    "Its own category (live, slower)": "category",
}


@st.cache_data(ttl=600, show_spinner="Resolving + analyzing token…")
def _analyze(query: str, peer_mode: str) -> dict:
    """Resolve + collect + score one token. Cached; returns a plain dict."""
    from dyor.analyze import analyze_token

    res = analyze_token(query, peer_mode=peer_mode)
    r = res.resolved
    return {
        "resolved": None if r is None else {
            "name": r.name, "symbol": r.symbol, "gecko_id": r.gecko_id,
            "matched_by": r.matched_by, "rank": r.market_cap_rank,
            "chains": r.chains, "platforms": r.platforms,
            "explorers": r.explorer_links(), "coingecko_url": r.coingecko_url,
            "links": r.links,
        },
        "record": res.record, "result": res.result, "peer_count": res.peer_count,
        "errors": res.errors, "all_results": res.all_results, "rank": res.rank,
    }


def _market_snapshot(record: dict) -> None:
    m = record.get("_market") or {}
    if not any(v is not None for v in m.values()):
        return
    st.markdown("#### Market snapshot")
    a = st.columns(4)
    price = m.get("price")
    a[0].metric("Price", f"${price:,.6g}" if price else "—")
    a[1].metric("Market cap", _usd(m.get("market_cap")))
    a[2].metric("FDV", _usd(m.get("fdv")))
    a[3].metric("24h volume", _usd(m.get("volume_24h")))
    b = st.columns(4)
    ch = m.get("price_change_24h_pct")
    b[0].metric("24h change", f"{ch:+.1f}%" if ch is not None else "—")
    ath = m.get("ath_change_pct")
    b[1].metric("From ATH", f"{ath:.0f}%" if ath is not None else "—")
    b[2].metric("Circulating", _num(m.get("circulating_supply")))
    b[3].metric("Total supply", _num(m.get("total_supply")))


def _crosschain_and_resources(rd: dict) -> None:
    chains, explorers, links = rd["chains"], rd["explorers"], (rd.get("links") or {})
    with st.expander(f"🔗 Cross-chain ({len(chains)} chain(s)) + resources"):
        if explorers:
            st.markdown("**Explorers:** " + " · ".join(f"[{c}]({u})" for c, u in explorers.items()))
        other = [c for c in chains if c not in explorers]
        if other:
            st.caption("Also deployed on: " + ", ".join(other[:18]) + (" …" if len(other) > 18 else ""))
        res = [f"[CoinGecko]({rd['coingecko_url']})"]
        if links.get("homepage"):
            res.append(f"[Website]({links['homepage']})")
        if links.get("github"):
            res.append(f"[GitHub]({links['github']})")
        if links.get("twitter"):
            res.append(f"[Twitter/X]({links['twitter']})")
        st.markdown("**Links:** " + " · ".join(res))


def _peer_table(all_results, target_token: str) -> None:
    st.markdown("#### Peer comparison")
    st.caption("The token (⭐) ranked against its peer set.")
    rows = [{"Token": f"{r.token} ⭐" if r.token == target_token else r.token,
             "Final": _clean(r.final_score), "Tier": r.tier,
             "Coverage": _clean(r.coverage), "Flags": ", ".join(r.flags) or "—"}
            for r in all_results]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 column_config={"Final": st.column_config.ProgressColumn(
                     "Final", min_value=0.0, max_value=1.0, format="%.3f")})


def _weight_whatif(result, record: dict, cfg: dict) -> None:
    from dyor.scoring.composite import combine, to_tier
    from dyor.scoring.gate import evaluate
    from dyor.scoring.weights import Weights, load_weights

    st.markdown("#### ⚖️ Weight what-if")
    st.caption("Re-weight the five domains to your thesis and watch the score move. "
               "(Domain scores stay fixed; only the blend changes.)")
    base = load_weights(cfg).by_domain
    cols = st.columns(len(base))
    vals = {d: col.slider(DOMAIN_META.get(d, (d,))[0], 0.0, 1.0, float(w), 0.05, key=f"w_{d}")
            for col, (d, w) in zip(cols, base.items())}
    total = sum(vals.values())
    weights = Weights({d: v / total for d, v in vals.items()}) if total > 0 else load_weights(cfg)

    new_raw = combine(result.domain_scores, weights)
    gate = evaluate(record, cfg)
    new_final = gate.apply(new_raw) if not _ismissing(new_raw) else new_raw
    base_final = result.final_score
    delta = (new_final - base_final) if not (_ismissing(new_final) or _ismissing(base_final)) else None
    c1, c2 = st.columns(2)
    c1.metric("Re-weighted final", _clean(new_final),
              delta=None if delta is None else round(delta, 3))
    c2.metric("New tier", to_tier(new_final, cfg))


def _contribution_table(result, cfg: dict) -> None:
    from dyor.scoring.weights import load_weights

    w = load_weights(cfg).by_domain
    present = {d: s for d, s in result.domain_scores.items() if not _ismissing(s)}
    tw = sum(w.get(d, 0) for d in present) or 1.0
    rows = [{"Domain": DOMAIN_META.get(d, (d,))[0], "Weight": f"{w.get(d, 0):.0%}",
             "Score": round(s, 3), "Contribution": round(w.get(d, 0) / tw * s, 3)}
            for d, s in present.items()]
    rows.sort(key=lambda r: r["Contribution"], reverse=True)
    st.markdown("#### What drove the score")
    st.caption("Each domain's share of the final (weight × score, renormalized over present domains).")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _ismissing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _export_button(data: dict) -> None:
    import json

    sr = data["result"]
    payload = {
        "resolved": data["resolved"],
        "score": {"final": _clean(sr.final_score), "raw": _clean(sr.raw_score),
                  "tier": sr.tier, "coverage": _clean(sr.coverage),
                  "flags": sr.flags, "advisories": sr.advisories,
                  "domain_scores": {k: _clean(v) for k, v in sr.domain_scores.items()},
                  "rank": data["rank"], "peer_count": data["peer_count"]},
        "record": {k: v for k, v in (data["record"] or {}).items() if not k.startswith("_")},
        "market": (data["record"] or {}).get("_market"),
    }
    st.download_button("⬇ Download analysis (JSON)",
                       json.dumps(payload, indent=2, default=str),
                       file_name=f"{data['resolved']['gecko_id']}_dyor.json",
                       mime="application/json")


def _render_compare(queries: list[str], peer_mode: str, cfg: dict) -> None:
    st.markdown(f"#### Comparing {len(queries)} tokens")
    rows, details = [], []
    for q in queries[:6]:
        data = _analyze(q, peer_mode)
        r, res = data["resolved"], data["result"]
        if r is None:
            st.warning(f"Could not resolve **{q}**.")
            continue
        if res is None:
            st.warning(f"**{r['name']}**: no market data to score.")
            continue
        row = {"Token": r["name"], "Symbol": r["symbol"], "Final": _clean(res.final_score),
               "Tier": res.tier, "Coverage": _clean(res.coverage)}
        row.update({DOMAIN_META[k][0]: _clean(v) for k, v in res.domain_scores.items() if k in DOMAIN_META})
        rows.append(row)
        details.append((r, res, data["record"]))
    if not rows:
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"Final": st.column_config.ProgressColumn(
                     "Final", min_value=0.0, max_value=1.0, format="%.3f")})
    st.bar_chart(df.set_index("Token")["Final"].dropna(), height=260)
    for r, res, rec in details:
        with st.expander(f"{r['name']} ({r['symbol']}) — {res.tier}"):
            _render_detail(res, rec or {}, cfg)


def page_analyze(cfg: dict) -> None:
    st.header("🔍 Analyze a token")
    st.markdown(
        "Run the full analysis on **any** token — by **name** (Aave), **symbol** "
        "(UNI), or **contract address** (resolves the unified token across **all "
        "its chains**). Enter **several, comma-separated**, to compare them."
    )
    query = st.text_input(
        "Token name(s), symbol(s), or contract address",
        placeholder="e.g.  AAVE   ·   Lido DAO   ·   0x514910…   ·   aave, uniswap, curve")
    peer_label = st.radio("Compare against", list(_PEER_MODES), horizontal=True,
                          help="The peer baseline the token is percentile-scored against.")
    peer_mode = _PEER_MODES[peer_label]

    if not query or not st.button("Analyze", type="primary"):
        st.info("Enter a token and press **Analyze**. It's scored live against your "
                "chosen peer baseline. Tip: run `dyor collect --top-n 50 --persist` "
                "for a richer 'Last saved run' baseline.")
        return

    queries = [q.strip() for q in query.split(",") if q.strip()]
    if len(queries) > 1:
        _render_compare(queries, peer_mode, cfg)
        return

    data = _analyze(queries[0], peer_mode)
    r = data["resolved"]
    if r is None:
        st.error(f"Could not resolve **{query}**. Try a name, symbol, or contract address.")
        if data["errors"]:
            st.caption("· ".join(e["error"] for e in data["errors"][:2]))
        return

    rank = f" · CG rank #{r['rank']}" if r["rank"] else ""
    st.success(f"Resolved **{r['name']} ({r['symbol']})** — matched by "
               f"**{r['matched_by']}**{rank}  ·  `id={r['gecko_id']}`")
    _crosschain_and_resources(r)

    if data["result"] is None:
        st.warning("Resolved, but no market data was available to score this token.")
        return

    _market_snapshot(data["record"] or {})
    if data["rank"]:
        st.caption(f"📊 Ranked **#{data['rank']}** of {data['peer_count'] + 1} "
                   f"(token + {data['peer_count']} peers).")
    st.divider()
    _render_detail(data["result"], data["record"] or {}, cfg,
                   peer_note=f"Scored against **{data['peer_count']}** peers ({peer_label}).")

    st.divider()
    _weight_whatif(data["result"], data["record"] or {}, cfg)
    st.divider()
    _contribution_table(data["result"], cfg)
    st.divider()
    _peer_table(data["all_results"], data["resolved"]["gecko_id"])
    st.divider()
    _export_button(data)


def page_narratives(cfg: dict) -> None:
    st.header("🔥 Narrative rotation")
    st.markdown(
        "Crypto capital rotates between **narratives** (AI, DePIN, RWA, privacy, gaming…). "
        "Spotting a sector heating **before** price follows is an edge. This ranks "
        "CoinGecko's 700+ categories by momentum — rising market-cap with rising attention "
        "is an early signal; a sector already parabolic on the news may be late."
    )
    by_label = st.radio("Rank by", ["24h momentum", "Market cap", "Volume (24h)"], horizontal=True)
    by = {"24h momentum": "market_cap_change_24h", "Market cap": "market_cap",
          "Volume (24h)": "volume_24h"}[by_label]

    if not st.button("Load / refresh narratives", type="primary"):
        st.info("Click **Load / refresh narratives** to pull live category data from CoinGecko.")
        return

    rows = _fetch_narratives(by)
    if not rows:
        st.warning("No category data returned.")
        return

    df = pd.DataFrame([
        {
            "Narrative": r["name"],
            "24h %": _clean(r["change_24h"]),
            "Market cap ($B)": round((r["market_cap"] or 0) / 1e9, 2),
            "Volume 24h ($M)": round((r["volume_24h"] or 0) / 1e6, 1),
            "Top coins": ", ".join(r.get("top_3") or []),
        }
        for r in rows
    ])
    st.dataframe(df, width="stretch", hide_index=True)
    st.bar_chart(df.set_index("Narrative")["24h %"], height=300)


def page_methodology(cfg: dict) -> None:
    st.header("📖 Methodology")
    st.markdown(
        "**Normalize → weight → gate → tier.** Heterogeneous signals are made "
        "comparable, combined by domain weight, then hard flaws override the average."
    )

    st.markdown("##### 1 · Normalize")
    st.markdown(
        "Each metric is ranked **across the peer set** (percentile by default) into 0–1, so "
        "no single large-magnitude factor dominates. 'Lower is better' metrics (P/F, dilution, "
        "concentration, unlock overhang) are inverted.")
    st.markdown("##### 2 · Weight by domain")
    st.markdown("Domain scores combine with explicit weights summing to 1.0:")
    st.markdown("\n".join(
        f"- **{DOMAIN_META[k][0]}** — {cfg['scoring']['weights'][k]:.0%}"
        for k in DOMAIN_META if k in cfg["scoring"]["weights"]))
    st.markdown("##### 3 · Gate (don't average)")
    st.markdown("Hard disqualifiers cap or zero the score so a fatal flaw can't be offset:")
    st.json(cfg["gating"]["rules"], expanded=False)
    st.markdown("##### 4 · Tier")
    _tier_legend()

    st.divider()
    st.markdown("#### Asset classes — judged on what matters for each")
    st.markdown(
        "Not every token is a cash-flow protocol. Each token is classified and "
        "scored with a class-appropriate profile, so **'no protocol revenue' is "
        "fatal for a DeFi app but a non-issue for Bitcoin**.")
    from dyor.classes import LABELS, class_profile
    st.dataframe(pd.DataFrame([
        {"Class": lab, "Judged on": ", ".join(class_profile(name).feature_spec.keys()),
         "Why": desc}
        for name, (lab, desc) in LABELS.items() if name != "general"
    ]), width="stretch", hide_index=True)

    st.divider()
    st.markdown("#### Metric glossary")
    glos = pd.DataFrame(
        [{"Metric": label, "Good when": "↓" if d == "lower" else "↑", "Meaning": desc}
         for (label, desc, d) in FEATURE_META.values()])
    st.dataframe(glos, width="stretch", hide_index=True)

    st.divider()
    st.markdown("#### Data sources & the open-first principle")
    st.markdown(
        "Where a signal is paywalled on one provider, we use a **free / open** alternative "
        "for the same feature rather than block on a key — and coverage gaps surface as "
        "honest `n/a`, never fabricated zeros.")
    st.dataframe(pd.DataFrame([
        {"Source": "DefiLlama", "Provides": "fees, revenue, holders-rev, TVL", "Access": "free"},
        {"Source": "CoinGecko", "Provides": "price, supply, FDV, ATH, categories", "Access": "free"},
        {"Source": "CryptoRank v0", "Provides": "unlock / vesting overhang", "Access": "free (open v0; v1/v2 keyed)"},
        {"Source": "Ethplorer", "Provides": "holder concentration (ETH)", "Access": "free (freekey)"},
        {"Source": "Santiment", "Provides": "active addrs, dev activity", "Access": "free (social = keyed)"},
        {"Source": "GitHub", "Provides": "org last-push (dev gate)", "Access": "free"},
    ]), width="stretch", hide_index=True)


# ==========================================================================
def main() -> None:
    st.set_page_config(page_title="DYOR — Token Qualification", page_icon="🧭", layout="wide")

    with st.sidebar:
        st.markdown("## 🧭 DYOR")
        st.caption("Flight-to-fundamentals token scorer")
        page = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.divider()
        st.selectbox(
            "Scoring data source", SOURCES, key="source",
            help="Sample = offline demo · Live = fetch all sources · "
                 "Stored = your last `dyor collect --persist` run.",
        )
        st.caption(f"Source: **{_source()}**")
        st.checkbox(
            "Score within category", key="peer_groups",
            help="Normalize each metric against same-category peers (Lending vs "
                 "Dexs vs L1…) instead of the whole universe. Fairer, but noisier "
                 "in small groups. Needs category-tagged data (Live / Stored).",
        )
        st.checkbox(
            "Penalize missing core domain", key="penalize_core", value=True,
            help="Floor a missing core domain (e.g. a DeFi app with no fees/revenue) "
                 "instead of renormalizing it away.",
        )
        st.divider()
        cfg = load_config()
        st.caption(f"10Y treasury hurdle **{cfg['reference']['treasury_10y_yield_pct']}%** "
                   f"· normalization **{cfg['scoring']['normalization']}**")

    router = {
        PAGES[0]: page_home, PAGES[1]: page_analyze, PAGES[2]: page_screener,
        PAGES[3]: page_detail, PAGES[4]: page_narratives, PAGES[5]: page_methodology,
    }
    router[page](cfg)


if __name__ == "__main__":
    main()
