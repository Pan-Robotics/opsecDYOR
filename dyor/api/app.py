"""DYOR REST API (FastAPI).

    uvicorn dyor.api.app:app --reload --port 8000

Exposes the scoring engine so any frontend (the Next.js app, scripts, external
tools) can consume it. CORS is open for local dev.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from dyor.api import jobs

from dyor.api.serialize import (
    analyze_to_dict, chart_summary, class_to_dict, record_to_dict, score_to_dict,
)
from dyor.app.copy import BREAK_THESIS, DOMAIN_META, FEATURE_META, tier_color
from dyor.classes import LABELS
from dyor.config import load_config
from dyor.pipeline import score_universe
from dyor.sample_data import SAMPLE_UNIVERSE

app = FastAPI(title="DYOR API", version="0.1.0",
              description="Crypto token qualification — asset-class-aware scoring.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # dev: any origin; tighten for production
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _records(source: str) -> list[dict[str, Any]]:
    """Records for the sample set or the last persisted run."""
    if source == "stored":
        from dyor.store import db
        con = db.connect()
        try:
            return db.latest_records(con)
        finally:
            con.close()
    return SAMPLE_UNIVERSE


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dyor"}


@app.get("/api/analyze")
def analyze(
    q: str = Query(..., description="token name, symbol, or contract address"),
    peer_mode: str = Query("class", pattern="^(class|stored|sample|category)$"),
    penalize_missing_core: bool | None = Query(
        None, description="floor a missing core domain (None = config default)"),
) -> dict[str, Any]:
    """Resolve + score one token against a peer baseline."""
    from dyor.analyze import analyze_token

    res = analyze_token(q, peer_mode=peer_mode,
                        penalize_missing_core=penalize_missing_core, persist=True)
    if res.resolved is None:
        raise HTTPException(status_code=404, detail=f"could not resolve '{q}'")
    return analyze_to_dict(res)


@app.get("/api/screener")
def screener(
    source: str = Query("sample", pattern="^(sample|stored)$"),
    peer_groups: bool = False,
    penalize_missing_core: bool | None = None,
) -> dict[str, Any]:
    """Ranked universe from the sample set or the last persisted run."""
    if source == "stored":
        from dyor.store import db
        con = db.connect()
        try:
            records = db.latest_records(con)
        finally:
            con.close()
    else:
        records = SAMPLE_UNIVERSE

    results = score_universe(records, peer_groups=peer_groups,
                             penalize_missing_core=penalize_missing_core)
    by_token = {r.get("token"): r for r in records}
    rows = []
    for r in results:
        d = score_to_dict(r)
        d["class"] = class_to_dict(by_token.get(r.token, {}).get("_class"))
        d["market"] = (by_token.get(r.token, {}) or {}).get("_market")
        rows.append(d)
    return {"source": source, "count": len(rows), "results": rows}


@app.post("/api/screener/build")
def screener_build(top_n: int = 30, category: str | None = None) -> dict[str, Any]:
    """Start a background universe collection (top-N by TVL → persist). Poll the
    returned job_id; when done, re-fetch /api/screener?source=stored."""
    return {"job_id": jobs.start_build(top_n, category)}


@app.get("/api/screener/build/{job_id}")
def screener_build_status(job_id: str) -> dict[str, Any]:
    return jobs.job_status(job_id)


@app.get("/api/token-record")
def token_record(source: str = "stored", token: str = Query(...)) -> dict[str, Any]:
    """The full record for one token in the screener set (for drill-down)."""
    from dyor.store import db
    if source == "stored":
        con = db.connect()
        try:
            records = db.latest_records(con)
        finally:
            con.close()
    else:
        records = SAMPLE_UNIVERSE
    rec = next((r for r in records if r.get("token") == token), None)
    if rec is None:
        raise HTTPException(404, f"token '{token}' not in {source}")
    return record_to_dict(rec)


@app.get("/api/memo")
def memo(q: str = Query(...), peer_mode: str = Query("class", pattern="^(class|stored|sample|category)$")) -> dict[str, Any]:
    """Reasoned analyst memo for a token (markdown)."""
    from dyor.memo import analyst_memo
    return {"query": q, "memo": analyst_memo(q, peer_mode=peer_mode)}


@app.get("/api/screen")
def screen_endpoint(
    source: str = Query("stored", pattern="^(stored|sample)$"),
    asset_class: str | None = None,
    min_tier: str | None = None,
    min_score: float | None = None,
    no_flags: bool = False,
    min_real_yield: float | None = None,
    max_fdv_mcap: float | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Filter the saved/sample universe by criteria."""
    from dyor.screen import screen
    records = _records(source)
    fmin = {"real_yield": min_real_yield} if min_real_yield is not None else None
    fmax = {"fdv_mcap_ratio": max_fdv_mcap} if max_fdv_mcap is not None else None
    rows = screen(records, asset_class=asset_class or None, min_tier=min_tier or None,
                  min_score=min_score, no_flags=no_flags, feature_min=fmin,
                  feature_max=fmax, limit=limit)
    return {"matched": len(rows), "universe": len(records), "results": rows}


@app.get("/api/portfolio")
def portfolio_endpoint(tokens: str = Query(..., description="comma-separated holdings"),
                       peer_mode: str = "class") -> dict[str, Any]:
    """Score a portfolio of holdings (comma-separated names/symbols/addresses)."""
    from dyor.portfolio import score_portfolio
    qs = [t.strip() for t in tokens.split(",") if t.strip()]
    if not qs:
        raise HTTPException(400, "no tokens provided")
    return score_portfolio(qs, peer_mode=peer_mode)


@app.get("/api/barbell")
def barbell_endpoint(n: int = 5) -> dict[str, Any]:
    """BTC anchor + top-N ungated A/B satellites from the saved universe."""
    from dyor.portfolio import barbell
    return barbell(n_satellites=n)


@app.get("/api/backtest")
def backtest_endpoint() -> dict[str, Any]:
    """Per-tier forward return from persisted runs."""
    from dyor.backtest import backtest
    return backtest()


@app.get("/api/chart")
def chart(id: str = Query(..., description="CoinGecko coin id"), days: int = 30) -> dict[str, Any]:
    """Historical price chart for a token (downsampled, with period change)."""
    from dyor.ingestion.coingecko import CoinGeckoClient
    days = max(1, min(days, 365))
    with CoinGeckoClient(load_config()) as cg:
        data = cg.market_chart(id, days=days)
    summary = chart_summary(data.get("prices") or [])
    return {"id": id, "days": days, **summary}


@app.get("/api/narratives")
def narratives(by: str = "market_cap_change_24h", top: int = 30) -> dict[str, Any]:
    """Narrative rotation — CoinGecko categories ranked by momentum."""
    from dyor.narratives import fetch_narratives
    return {"by": by, "rows": fetch_narratives(by=by, top=top)}


@app.get("/api/classes")
def classes() -> dict[str, Any]:
    return {"classes": [class_to_dict(name) for name in LABELS if name != "general"]}


@app.get("/api/methodology")
def methodology() -> dict[str, Any]:
    cfg = load_config()
    return {
        "weights": cfg["scoring"]["weights"],
        "tiers": [{"label": t["label"], "min": t["min"], "color": tier_color(t["label"])}
                  for t in cfg["scoring"]["tiers"]],
        "gating": cfg["gating"]["rules"],
        "reference": cfg["reference"],
        "domains": {k: {"label": v[0], "description": v[1]} for k, v in DOMAIN_META.items()},
        "glossary": [{"key": k, "label": v[0], "meaning": v[1], "direction": v[2]}
                     for k, v in FEATURE_META.items()],
        "break_thesis": BREAK_THESIS,
        "classes": [class_to_dict(name) for name in LABELS if name != "general"],
        "class_labels": {name: {"label": lab, "description": desc}
                         for name, (lab, desc) in LABELS.items()},
    }


@app.get("/api/benchmark")
def benchmark() -> dict[str, Any]:
    from dyor.benchmark import DEFAULT_CASES, run_benchmark
    report = run_benchmark(DEFAULT_CASES)
    return {
        "passed": report.passed, "total": report.total, "accuracy": report.accuracy,
        "results": [{"name": r.name, "passed": r.passed, "tier": r.tier,
                     "final_score": None if r.final_score != r.final_score else round(r.final_score, 4),
                     "reasons": r.reasons} for r in report.results],
    }
