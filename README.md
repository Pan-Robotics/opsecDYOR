# DYOR — Crypto Token Qualification Framework

A normalize-then-gate multi-factor scorer for crypto tokens. Resolve any token by
name, symbol or contract address (cross-chain), classify it (DeFi / L1 /
monetary / memecoin / stablecoin), score it on the dimensions that matter **for
its class** against a fixed same-class reference basket, then apply **hard
disqualifier gating** so a fatal flaw can't be averaged away. Built on free,
open data. Live at [dyor.cryptoopsec.com](https://dyor.cryptoopsec.com) as a
web app, a REST API and a hosted MCP server.

This is the implementation of the build plan in
[Crypto Token Qualification Framework](Crypto%20Token%20Qualification%20Framework:%20Validation,%20Data-Source%20Matrix,%20Scoring%20Methodology%20&%20Build%20Plan.md)
(Part 4 — Architecture & TDD). Current state, architecture and known limits:
[docs/PROJECT-STATE.md](docs/PROJECT-STATE.md).

## Pipeline

```
ingestion/   →  collect.py   →  metrics/    →  scoring/            →  surfaces
 clients        Target →         P/F, P/S,     normalize (anchored    cli · api/
 (shared rate   record           FDV/MCAP,     to class basket)       mcp_server
  limit, cache,  + _feeds        overhang,     → domain weights       web/ (Next.js)
  backoff)       diagnostics     growth        → gate → tier
                     ↕
                 store/db.py  (DuckDB: collection runs + reference baskets)
```

| Layer | Module | Responsibility |
|---|---|---|
| Ingestion | [dyor/ingestion/](dyor/ingestion/) | Per-source clients (DefiLlama, CoinGecko, GitHub, Santiment, CryptoRank, Ethplorer, Sourcify) — process-wide token-bucket limits, atomic on-disk cache with eviction, backoff, secret redaction |
| Collect | [dyor/collect.py](dyor/collect.py) | `Target` → scoring record, with a per-feed `_feeds` status map (ok / empty / error / off) |
| Classes | [dyor/classes.py](dyor/classes.py) | Asset-class profiles (feature spec, weights, required domains) + the reference baskets |
| Metrics | [dyor/metrics/](dyor/metrics/) | Derived: P/F, P/S, MC/TVL, FDV/MCAP, unlock overhang, concentration, growth |
| Scoring | [dyor/scoring/](dyor/scoring/) | normalize → weighted combine → gate → tier, with coverage + tier-stability |
| Pipeline | [dyor/pipeline.py](dyor/pipeline.py) | Reference-anchored normalization: a token's tier is identical as subject, peer or screener row |
| Store | [dyor/store/](dyor/store/) | DuckDB collection runs (with shrink guard + retention) and reference baskets |
| Surfaces | [dyor/cli.py](dyor/cli.py) · [dyor/api/](dyor/api/) · [dyor/mcp_server.py](dyor/mcp_server.py) · [web/](web/) | CLI, FastAPI, hosted MCP, Next.js UI |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" --no-build-isolation
cp .env.example .env            # all keys optional; see comments

pytest                          # offline unit suite
pytest -m integration           # cassette replay (record once with --record-mode=once)
ruff check dyor tests

# Analyze ONE token — name, symbol, or contract address (resolves cross-chain):
dyor analyze AAVE
dyor analyze 0x514910771AF9Ca656af840dff83E8264EcF986CA

# Build the same-class reference baskets that scoring is anchored to:
dyor reference                  # run alone — it is the one CoinGecko-heavy job

# The scheduled unit of work (weekly cron in production):
dyor refresh --top-n 60         # top-N by TVL ∪ every class basket → persist → alert
                                # prints per-source feed status; refuses to shrink the universe

# Memo · screen · barbell · backtest · benchmark:
dyor memo solana
dyor screen --min-tier B --no-flags --min-real-yield 0.045
dyor barbell -n 5
dyor backtest
dyor benchmark
```

Persisting a run replaces the screener's universe. `dyor refresh` and
`dyor collect --persist` therefore **refuse a run smaller than half the previous
one** unless `--force` is given, and `refresh` unions the reference baskets in by
default so the majors and every asset class stay on the board.

## API, web app and MCP

```bash
uvicorn dyor.api.app:app --port 8077        # REST (8000 is often taken locally)
cd web && npm install && npm run dev        # http://localhost:3000
dyor-mcp                                    # MCP over stdio (Claude Desktop / Code)
dyor-mcp --transport streamable-http --port 8765   # hosted MCP, served at /mcp
```

Agents connect to the hosted server with no install:
`claude mcp add --transport http dyor https://dyor.cryptoopsec.com/mcp`.
Tools: `analyze_token`, `resolve_token`, `compare_tokens`, `analyst_memo`,
`screen_tokens`, `score_portfolio`, `build_barbell`, `backtest`, `narratives`,
`asset_classes`, `methodology`. Details in [docs/mcp.md](docs/mcp.md); deployment
(nginx, pm2, cron, rate limits, admin token) in [DEPLOY.md](DEPLOY.md).

`POST /api/screener/build` is admin-only (`X-Admin-Token` = `DYOR_ADMIN_TOKEN`);
`/api/analyze` refreshes a token in place if it is already on the board and never
adds tokens to the public screener. The live-collection endpoints are rate-limited
per IP at nginx.

## Data sourcing principle

Prefer an **open** path over a gated one, and surface gaps honestly as `n/a` —
never as fabricated values. Every record carries a per-source `_feeds` map;
`dyor refresh` prints per-source counts and raises a **critical `feed_outage`
alert** when a source errors on most tokens.

Current sources, and what each contributes:

| Source | Features | Reach |
|---|---|---|
| DefiLlama protocols | P/F, P/S, MC/TVL, real yield, value accrual; `github` org; `audits` → the `no_audit` gate | protocols with a `gecko_id` |
| DefiLlama chains | the same fundamentals **chain-wide** for L1 tokens with no protocol slug | every chain in `/v2/chains` |
| CoinGecko | market/supply, categories (classification), sentiment, **watchlist count** (attention), **TVL fallback**, repo URLs | every token |
| Santiment (free) | address growth, dev-activity trend — slug resolved by id / contract / name / ticker | ~80% of tokens |
| Ethplorer `freekey` | top-10 holder concentration | Ethereum ERC-20s |
| Sourcify | contract verification (True-or-unknown) on Ethereum, Arbitrum, Base, OP, Polygon, BSC, Avalanche | any EVM deployment |
| GitHub | most recent push across every account found for the token — DefiLlama's list, all CoinGecko repo URLs, verified overrides; user accounts too (dead-token gate, corroborated against Santiment dev activity) — **needs `DYOR_GITHUB_TOKEN`**, anonymous is 60/hour | tokens with a known account |
| CryptoRank | unlock overhang, next-unlock $ — **Pro plan only** (v0 died Sep 2026; v3 free plan has no vesting endpoints) | off until upgraded |

Every record carries a per-source `_feeds` status. A spec only lists features
some source can produce (there is no free source for inflation rate or exchange
reserves, so they are not scored). One enrichment routine
(`universe.make_target`) attaches the same feeds whether a token arrives via
the TVL universe, a reference basket, or on-demand analyze — so the anchor and
the live record are measured on the same features.

`no_audit` now fires on DefiLlama's audit record (an explicit "0"; any audit link
counts as audited). `unverified_contract` and `anonymous_team` still cannot fire
on open data and are marked inactive in the methodology.

## Stage plan

- **Stage 1 — Free core** (done): identity resolution, class-aware scoring
  anchored to reference baskets, gating, the API/web/MCP surfaces, weekly refresh.
- **Stage 2 — Keyed add-ons** (add only when a metric materially changes a score
  and free sources can't derive it): CryptoRank Pro (vesting, next-unlock ÷
  volume), Token Terminal, CoinGlass (ETF flows), Glassnode (on-chain cohorts).
- **Stage 3 — Hardening**: async collection, Prefect/Dagster if the pipeline grows.

See [docs/STAGES.md](docs/STAGES.md).

## Legacy Streamlit dashboard

`dyor/app/dashboard.py` predates the Next.js app and is kept as an optional extra
(`pip install -e ".[legacy-ui]"`, then `streamlit run dyor/app/dashboard.py`). It
is not installed on the server and not covered by the test suite.

## Testing approach

Pure metric/scoring functions are unit-tested on fixtures (default `pytest` run,
offline). An autouse fixture points the DuckDB store and the on-disk cache at a
temp dir, so no test touches real data. API clients are integration-tested with
**vcrpy** cassettes (`-m integration`) — record once, replay offline; keys are
redacted from cassettes via `vcr_config`.
