# DYOR — Crypto Token Qualification Framework

A normalize-then-gate multi-factor scorer for crypto tokens. Resolves token
identity on `chain:address`, normalizes heterogeneous signals (fundamentals,
tokenomics, on-chain, social, dev), combines them with explicit domain weights,
and applies **hard disqualifier gating** so a fatal flaw can't be averaged away.

This is the implementation of the build plan in
[Crypto Token Qualification Framework](Crypto%20Token%20Qualification%20Framework:%20Validation,%20Data-Source%20Matrix,%20Scoring%20Methodology%20&%20Build%20Plan.md)
(Part 4 — Architecture & TDD).

## Pipeline (ELT)

```
ingestion/  → store/  → identity/  → metrics/  → scoring/  → app/
 clients      duckdb    crosswalk    derived     normalize   streamlit
 (rate-limit, raw       chain:addr   P/F, P/S,    → weight    dashboard
  cache,      landing   ↔ gecko_id   FDV/MCAP,    → gate
  backoff)                           unlock%      → tier
```

| Layer | Module | Responsibility |
|---|---|---|
| Ingestion | [dyor/ingestion/](dyor/ingestion/) | Per-source clients (DefiLlama, CoinGecko, GitHub, Santiment, CryptoRank v0, Ethplorer) with token-bucket rate limiting, on-disk caching, exponential backoff |
| Store | [dyor/store/](dyor/store/) | DuckDB raw-response landing + crosswalk tables |
| Identity | [dyor/identity/](dyor/identity/) | `chain:address` ↔ CoinGecko `id` ↔ DefiLlama slug (`gecko_id` join) |
| Metrics | [dyor/metrics/](dyor/metrics/) | Derived: P/F, P/S, MC/TVL, FDV/MCAP, unlock-%-of-volume, concentration |
| Scoring | [dyor/scoring/](dyor/scoring/) | `percentile/zscore/minmax` normalize → weighted combine → gate → tier |
| App | [dyor/app/](dyor/app/) | Streamlit dashboard |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the offline unit suite (pure functions — no network):
pytest

# Record integration cassettes once (hits live APIs):
pytest -m integration --record-mode=once

# Replay integration tests offline (CI mode — fails on unseen requests):
pytest -m integration --record-mode=none

# Analyze ONE token on demand — by name, symbol, or contract address (cross-chain):
dyor analyze AAVE
dyor analyze "Lido DAO"
dyor analyze 0x514910771AF9Ca656af840dff83E8264EcF986CA   # resolves cross-chain

# Score the built-in sample universe:
dyor score

# LIVE: fetch DefiLlama + CoinGecko + CryptoRank + Ethplorer + Santiment, score, persist:
dyor collect --persist
dyor collect --top-n 50 --category Lending --peer-groups   # build a universe, score within category

# Build cached same-class peer baskets (fairer "L1 vs L1" scoring):
dyor reference
dyor analyze solana --peer-mode class      # scored against L1 peers, not DeFi apps

# Reasoned analyst memo · screen · barbell · backtest:
dyor memo solana
dyor screen --min-tier B --no-flags --min-real-yield 0.045
dyor barbell -n 5
dyor backtest

# Check the scorer still reproduces known good/bad calls:
dyor benchmark

# Scheduled unit of work (for cron): collect + persist + alert vs the previous run:
dyor refresh                 # set DYOR_ALERT_WEBHOOK for Slack/Discord notifications

# Launch the Streamlit interface (analyst tool):
streamlit run dyor/app/dashboard.py
```

## Use it from an AI agent (MCP)

DYOR ships an **MCP server** so an AI agent (Claude Desktop/Code, Cursor, Manus…)
can call the scorer as tools while doing token research — getting an opinionated,
asset-class-aware, *gated* assessment instead of scraping raw data.

```bash
dyor-mcp                                   # stdio (Claude Desktop / Code)
dyor-mcp --transport sse --port 8848       # remote agents over HTTP/SSE
```

Register with Claude Code:

```bash
claude mcp add dyor -- dyor-mcp
```

Tools: `analyze_token` (resolve by name/symbol/contract, cross-chain → score, tier,
flags, peers), `resolve_token`, `compare_tokens`, `narratives`, `asset_classes`,
`methodology`. Full setup (Claude Desktop JSON, remote HTTP) in [docs/mcp.md](docs/mcp.md).

## Productized web app (FastAPI + Next.js)

A two-tier front end lives alongside the Streamlit analyst tool:

```bash
# 1. API (repo root, venv active):
uvicorn dyor.api.app:app --port 8077

# 2. Frontend (web/):
cd web && npm install && npm run dev   # http://localhost:3000
```

The **FastAPI** layer ([dyor/api/](dyor/api/)) exposes the scorer as REST
(`/api/analyze`, `/api/screener`, `/api/narratives`, `/api/methodology`,
`/api/classes`, `/api/benchmark`) so any frontend can consume it. The **Next.js**
app ([web/](web/)) is the polished UI — Home, Analyze, Screener, Narratives,
Methodology. See [web/README.md](web/README.md).

## Data sourcing principle

Prefer an **open** path over a gated one. Where a signal is paywalled on one
provider, we use a free alternative for the same feature rather than block on a
key: unlock overhang via **CryptoRank v0** (open) instead of DefiLlama Pro
`/emissions` (402); holder concentration via **Ethplorer `freekey`** instead of
Etherscan Pro. Coverage gaps surface honestly as `n/a` (e.g. Ethplorer is
Ethereum-only, so L2/own-chain tokens have no holder data) — never as fabricated
zeros. Keyed sources remain wired as optional precision upgrades.

## Stage plan

- **Stage 1 — Free core MVP** (current): DefiLlama + CoinGecko free + GitHub +
  Santiment free. Identity resolution, core metrics, composite score with gating,
  Streamlit dashboard.
- **Stage 2 — Paid add-ons**: Token Terminal (P/F, P/S), CoinGlass (ETF flows),
  CryptoRank (unlocks), Glassnode (on-chain cohorts) — add only when a metric
  materially changes a score *and* free sources can't derive it.
- **Stage 3 — Hardening**: Prefect/Dagster scheduling, contract tests on every
  external schema, narrative-rotation + unlock-cliff alerting.

See [docs/STAGES.md](docs/STAGES.md) for detail.

## Testing approach

Pure metric/scoring functions are unit-tested on fixtures (default `pytest`
run, offline & green). API clients are integration-tested with **vcrpy**
cassettes (`@pytest.mark.integration` + `@pytest.mark.vcr`) — record once,
replay offline in CI. API keys are redacted from cassettes via `vcr_config`.
