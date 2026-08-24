# Build Stages

Lifted from the framework doc's Recommendations section. Use these as the
"definition of done" gates for each stage.

## Stage 1 — Free core MVP (validate the thesis cheaply)

Sources (all free): **DefiLlama** (fees/revenue/TVL/unlocks/RWA) + **CoinGecko
free** (prices/supply/categories/ID map) + **GitHub** (authed) + **Electric
Capital** DuckDB taxonomy + **Santiment** free GraphQL.

Deliverables:
- [x] Identity resolution on `chain:address` (CoinGecko `/coins/list` ↔ DefiLlama `gecko_id`)
- [x] Core metrics: P/F, P/S, MC/TVL, FDV/MCAP, unlock-%-of-volume, holder concentration, dev-activity trend
- [x] Composite score (percentile-normalized, weighted, with hard disqualifier gating)
- [x] Ingest-to-score path: `dyor.collect.Collector` (live CoinGecko + DefiLlama + GitHub → metric records) + `dyor collect` CLI
- [x] Streamlit dashboard wired to live data (sidebar Sample / Live / Stored toggle)
- [x] Token-sink / value-accrual feature (holders-rev ÷ revenue, same-window) — free, in scoring
- [x] Dev-activity feature: GitHub org last-push → `days_since_last_commit` (feeds dead-token gate)
- [x] Persist collected records to `store.db` (`token_records`, `dyor collect --persist`, read-back in dashboard)
- [x] On-chain **address-growth** + **dev-activity trend** via Santiment (free/anonymous, `daily_active_addresses` + `dev_activity`, 30-day window) — in scoring
- [x] **Unlock overhang** via **CryptoRank v0** (open, no key) — locked-supply % when `hasVesting`. Captures HYPE's ~78% overhang. (Open alternative to the DefiLlama-Pro-gated `/emissions`.)
- [x] **Holder concentration** (top-10) via **Ethplorer `freekey`** (free) — Ethereum ERC-20s; L2/own-chain surface as n/a
- [x] **Narrative rotation** via CoinGecko categories (`dyor/narratives.py`) — momentum-ranked sectors, in the dashboard
- [x] **Interface**: multi-tab Streamlit (Token Scoring with per-token domain/feature drill-down + Narrative Rotation)
- [~] **Social trend** via Santiment `social_volume_total` — wired but **key-gated** (restricted anonymously); populates with `DYOR_SANTIMENT_API_KEY`
- [~] **Precise** unlock %-of-volume (next-event $ ÷ volume): metric + parser + wiring DONE, needs a keyed source
      (DefiLlama Pro `/emissions` = 402, or CryptoRank v1 `currencies/token-unlock`). The open v0 overhang covers the gating signal meanwhile.
- [ ] **Reserve-trend** (exchange reserves) — needs a keyed source (Glassnode / CryptoQuant)
- [ ] Gini/Nakamoto concentration beyond top-10, multi-chain holders (L2/own-chain) — needs Nansen/Covalent
- [ ] Electric Capital `open-dev-data` DuckDB load (ecosystem→repo taxonomy) for fuller dev coverage

**Benchmark to advance:** the free data reproduces known good/bad calls — e.g.
correctly flags high-FDV/low-float unlock overhangs and dead tokens.

### Free features (done)
- [x] **Social sentiment** — CoinGecko `sentiment_votes_up_percentage` (keyless) → `social_sentiment` feature fills the social domain on the free path. Coarse (vote-based, often 100%/null) but real & testable. LunarCrush (Galaxy Score/AltRank) is the keyed quality upgrade — **not built** (v4 needs a Bearer token; not more open than Santiment).
- [x] **VC backing** — `num_vc_backers` + `had_public_sale` from the CryptoRank v0 coin we already fetch (free; informational, not scored — more funds ≠ better). Surfaced in token detail.
- [x] **Score history** (`dyor/history.py`) — re-scores each persisted run (`store.db.runs` / `records_for_run`) to chart a token's final-score trajectory; shown in the dashboard token detail. Always reflects current scoring logic.

### MCP server — agent-callable (done)
- [x] **`dyor/mcp_server.py`** (FastMCP) — DYOR's scorer as MCP tools so an AI agent (Claude Desktop/Code, Cursor, Manus…) can vet tokens. Tools: `analyze_token` (resolve name/symbol/contract cross-chain → score/tier/flags/peers), `resolve_token`, `compare_tokens`, `narratives`, `asset_classes`, `methodology`. Reuses the API serializers.
- [x] Console entry **`dyor-mcp`** (stdio default; `--transport sse|streamable-http --port` for remote). Register: `claude mcp add dyor -- dyor-mcp`. Docs: [docs/mcp.md](mcp.md).
- [x] Verified over the real MCP protocol (stdio handshake → list_tools → call_tool, incl. live `analyze_token(bitcoin)` → Monetary, B). 5 unit tests.
- This is the **agent-native distribution wedge** from the growth Phase 0 (open dev-tool the crypto-builder crowd shares).

### Penalty mode + productized web app (done)
- [x] **Core-domain penalty** — each class marks `required_domains` (DeFi = `fundamental`); a token missing a required domain is floored (config `missing_core_penalty`, default 0.0) instead of renormalized away, with an advisory. So a DeFi app with no measurable fees/revenue/TVL is now actively penalized; data gaps in non-core domains stay forgiving. Toggle: `scoring.penalize_missing_core`.
- [x] **FastAPI backend** (`dyor/api/`) — REST over the scorer (`/api/analyze`, `/api/screener`, `/api/narratives`, `/api/methodology`, `/api/classes`, `/api/benchmark`), CORS-open, serializers, 7 TestClient tests.
- [x] **Next.js frontend** (`web/`) — Next 14 + React 18 + TypeScript + Tailwind. Home / Analyze (search → full token report) / Screener / Narratives / Methodology. Builds clean; live-verified end-to-end against the API (CORS OK, ETH→L1, BTC→Monetary, AAVE→DeFi).
- Fixed: classify ordering — L1 id-set now beats `has_fees` (ETH has DefiLlama fees but is a platform, not a DeFi app).

### Asset-class-aware scoring (done)
- [x] **Asset classes** (`dyor/classes.py`) — every token is classified (DeFi / L1 / Monetary / Memecoin / Stablecoin / General) and scored with a **class-appropriate profile** (its own `feature_spec` + domain weights). So "no protocol revenue" is fatal for a DeFi app but a non-issue for Bitcoin (monetary tokens have no `fundamental` domain at all).
- [x] **Classifier** — CoinGecko categories + DefiLlama category + has-fees + price-peg + known-id safety nets. Excludes "Stablecoin Issuer" (Aave issues GHO but is DeFi); requires a price peg for stablecoins; DeFi checked before L1.
- [x] **Pipeline** — union normalization across all tokens that have a feature; per-token class profile drives domain scoring, weights, and **class-relative coverage** (a monetary asset isn't dinged for missing P/F).
- [x] Surfaced in CLI (`class:` line), UI (class badge + description on detail/analyze, Class column on the screener), and a Methodology explainer table.
- Live: **Bitcoin 0.389 D → 0.562 C** (no longer penalized for lacking revenue); ETH→L1, DOGE→Memecoin, AAVE→DeFi.
- KNOWN LIMIT: a DeFi token with genuinely ~zero fees gets `fundamental`=N/A (renormalized away), so it's not *actively* penalized — the coverage indicator + gate surface it instead. A "missing-expected-domain = penalty" mode is a possible future refinement.

### On-demand single-token analysis (done)
- [x] **Resolution** (`dyor/resolve.py`) — query → token by **name**, **symbol**, or **contract address** (EVM `0x…` tried across ethereum/BSC/polygon/arbitrum/base/optimism/avax; Solana base58). An address resolves the **unified token across all its chains** (CoinGecko coin id aggregates every deployment).
- [x] **Analyze** (`dyor/analyze.py`) — resolve → auto-resolve data-source ids → collect live → score against a **peer baseline** (last persisted run, else sample) so a lone token still gets meaningful percentiles.
- [x] **CLI** `dyor analyze <query>` + **UI** "🔍 Analyze" page (search box → resolution + chains → full token visualization, reusing the detail renderer).
- [x] **Analyze toolset**: peer-set selector (last run / sample / live category); market snapshot (price/mcap/FDV/vol/supply/ATH); cross-chain explorer links + resources (CoinGecko/site/GitHub/Twitter); peer-comparison table + rank; **interactive weight what-if sliders**; domain-contribution breakdown; JSON export; **multi-token compare** (comma-separated).
- [x] **Hardening** (gamut-tested across BTC/ETH/SOL/stablecoins/memes/addresses): expected misses (404/400/unknown-slug) reclassified as no-data, not red errors; 429 resilience (keyless CoinGecko paced to 12/min + auto-raise with a Pro key, shared client across resolve+collect, `Retry-After` honored, non-fatal `markets`); **fixed a real bug** — "bitcoin" mis-resolved to a memecoin whose symbol is "BITCOIN"; now ranks exact symbol/name/id matches by market cap, with a gecko-id fallback.

### Breadth — real screener (done)
- [x] **Universe builder** (`dyor/universe.py`) — top-N protocols by TVL (optionally per category) from DefiLlama, excluding CEX/Chain/Bridge, de-duped by gecko_id.
- [x] **Auto identity-resolution** — `defillama_slug` from the protocol, `eth_contract` from CoinGecko `/coins/list` platforms (one call), `santiment_slug`/`cryptorank_key` best-effort = gecko_id (misses → honest diagnostics), `category` attached as the peer group.
- [x] **Category-relative normalization** — `score_universe(..., peer_groups=True)` ranks each metric within its `_group` (the doc's "compare within category"); CLI `--peer-groups`, dashboard "Score within category" toggle.
- [x] **CLI**: `dyor collect --top-n N [--category Lending] [--peer-groups]`. Live-verified end-to-end; the `dead_token` gate fires on real small-cap lending tokens.
- NOTE: for auto-built universes (no `github_org`), `dead_token` can only fall back
  on the low-volume criterion (drawdown was deliberately removed as a dead-token
  criterion — price action alone must not zero a token; see `config.yaml`).
- KNOWN LIMIT (2026-08-24 integration test): three of the five gate rules are
  inert on live data — `anonymous_team`/`no_audit` read fields only the sample
  data carries, and `unverified_contract` needs an explicit `False` that open
  sources never emit. Live gating is effectively `extreme_fdv_mcap` + low-volume
  `dead_token`. Populating team/audit facts needs a keyed or curated source.

### Reliability hardening (done)
- [x] **Data-coverage / confidence** score per token (features-present ÷ total) — in `ScoreResult`, CLI, and UI; sparse scores no longer read as confident.
- [x] **Per-feed diagnostics** — `Collector.errors` + each record's `_feeds` map (off/empty/error/ok); a failed feed is visible, not a silent `n/a`. (Surfaced a real `santiment`/`cryptorank` error that was previously invisible.)
- [x] **Contract verification** via **Sourcify** (open, keyless) → `contract_verified=True` on a confirmed match, else `None` (never a false `False` that could wrongly zero a score). Definitive "unverified→gate" still needs a keyed authoritative source (Etherscan).
- [x] **Treasury-hurdle advisory** — flags tokens paying a real yield below the 10Y (wires the previously-unused config constant; the thesis' hurdle-rate point).
- [x] **Schema/contract tests** (`jsonschema`) on DefiLlama / CoinGecko / CryptoRank / Ethplorer responses — catch API shape drift on re-record.
- [x] **Bug fixed**: Ethplorer `holders` variable collided with DefiLlama holders-revenue, nulling `value_accrual` live — now distinct vars.

## Stage 2 — Targeted paid add-ons (buy only what free can't derive)

- **Token Terminal** — vendor-computed P/F & P/S (vs. rolling our own from DefiLlama fees)
- **CoinGlass Standard ($299/mo)** — ETF flows + derivatives (the genuine data edge; commercial license)
- **CryptoRank** — richer unlock/vesting/funding-round coverage
- **Glassnode Professional** — only if deep BTC/ETH on-chain cohorts become central
- **Nansen pay-per-call** — smart-money confirmation signals

**Threshold to add a paid source:** only when a metric materially changes a
score AND cannot be derived from free sources.

## Stage 3 — Hardening & scale

### Ops & automation (done)
- [x] **Benchmark harness** (`dyor/benchmark.py`, `dyor benchmark`) — labeled cases with expected tier/flags/zeroed/score-band; the "benchmark to advance" gate + a regression guard after weight/gating changes. (4/4 default cases pass.)
- [x] **Alerting** (`dyor/alerts.py`) — pure detectors: score-change, tier-change, new gate flag (critical), unlock-cliff, narrative-heating; console sink always + webhook sink if `DYOR_ALERT_WEBHOOK` is set (Slack/Discord `text` payload).
- [x] **Scheduling** — `dyor refresh` is the unit of scheduled work (snapshot previous run → collect+persist → alert vs previous). Dependency-free; run via cron:

  ```cron
  # refresh the curated set every 30 min; alert on changes
  */30 * * * *  cd /path/to/DYOR && .venv/bin/dyor refresh >> /var/log/dyor.log 2>&1
  # nightly top-100 universe sweep
  0 3 * * *     cd /path/to/DYOR && .venv/bin/dyor refresh --top-n 100 >> /var/log/dyor.log 2>&1
  ```

- [x] Contract/schema tests on external responses (jsonschema) — see Reliability hardening.

### Still optional
- Prefect/Dagster instead of cron (retries + observability) if the pipeline grows.
- Allium/Flipside/Dune if custom on-chain SQL or streaming is needed.

## Cross-cutting reminders

- Treat secondary aggregators (e.g. Spoted Crypto) as **leads, not primary
  sources** — wire to CryptoQuant/CoinGlass/Glassnode/RWA.xyz directly.
- Refresh stale constants (treasury hurdle, RWA totals, supply) on a schedule.
- Keep predictions/price-targets OUT of the scorer — they are not data.
