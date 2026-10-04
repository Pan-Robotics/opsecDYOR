# DYOR — Consolidated Project State

**Compiled 2026-08-24.** Reconstructed from the surviving `~/.claude/.../memory/` files,
in-repo docs, the working tree, the DuckDB store, and live checks against production.
Written because the Claude Code session transcripts for this project (June–July 2026)
were deleted by the 30-day retention sweep on 2026-08-19 and are not recoverable.

Sources of truth this consolidates: `docs/STAGES.md` (build gates), `DEPLOY.md` +
`SERVER-SETUP-HANDOFF.md` (ops), `growth/dyor-instance.md` (go-to-market),
`README.md`, `config.yaml`.

---

## 1. What DYOR is

A **normalize-then-gate, asset-class-aware crypto token qualification scorer**, built
from the research doc *"Crypto Token Qualification Framework"* (Part 4 build plan,
in-repo). Resolve any token by name, symbol, or contract address (cross-chain) → a
0–100 composite score, an A–D tier, hard-disqualifier gate flags, and a full report.

The core thesis: **judge each token by the dimensions that matter for its asset
class.** A DeFi app is judged on fees/revenue/TVL; Bitcoin is not penalised for
having no protocol revenue. Built entirely on **free/open data sources**.

Positioning (drafted Phase 0, not locked): *"The open, no-paywall token scorer —
judges Bitcoin like Bitcoin and a DeFi app like a DeFi app; transparent methodology,
not a black box."* Framed throughout as a **research aid, not financial advice.**

---

## 2. Verified current state (checked 2026-08-24)

| Check | Result |
|---|---|
| Unit tests | **179 passed**, 14 integration deselected, ~5s (`.venv/bin/python -m pytest -q`) |
| Git | 1 commit, `ed5ecd9`, dated 2026-07-02, 135 files / 65,867 insertions. Clean tree. |
| Last code change | 2026-06-28 14:35 (`dyor/mcp_server.py`) |
| Local DuckDB | `data/dyor.duckdb` — 105 `token_records`, 43 `reference_records`; latest run `20260623T221809Z` (32 tokens). `crosswalk` and `raw_responses` empty. |
| `https://dyor.cryptoopsec.com/` | **200 — LIVE** |
| `https://dyor.cryptoopsec.com/api/methodology` | **200 — LIVE** |
| `https://cryptoopsec.com/` | **200 — LIVE** |
| Hosted MCP | Registered and reachable as the `claude.ai DYOR` connector (11 tools) |

**The deployment shipped.** The memory files describe deploy as a *plan* with a
runbook; production is in fact up and serving. That happened in a session whose
transcript is gone.

---

## 3. Architecture

ELT, layered:

```
dyor/ingestion/   BaseClient (token-bucket rate limit, file cache, retry/backoff,
                  Retry-After honoured) → defillama, coingecko, github, santiment,
                  cryptorank, ethplorer, sourcify
       ↓
dyor/store/db.py  DuckDB raw landing + crosswalk + token_records + reference_records
       ↓
dyor/identity/    resolver.py — chain:address ↔ gecko_id join
       ↓
dyor/metrics/     valuation.py, tokenomics.py, onchain.py (pure functions)
       ↓
dyor/scoring/     normalize → weights → gate → composite
       ↓
dyor/pipeline.py  normalize-across-peers glue
       ↓
dyor/cli.py · dyor/api/ (FastAPI) · web/ (Next.js) · dyor/mcp_server.py (FastMCP)
```

Tuning lives in `config.yaml`; secrets in `.env` with a `DYOR_` prefix.

### Asset classes (`dyor/classes.py`)

Every token is classified **defi / l1 / monetary / meme / stablecoin / general** via
CoinGecko categories + DefiLlama category + has-fees + price-peg + known-id safety
nets (`MONETARY_IDS`, `L1_IDS`, `STABLE_IDS`, `MEME_IDS`). Each class carries its own
`ClassProfile` — feature spec, domain weights, and `REQUIRED_DOMAINS`.

Two ordering gotchas already fixed, don't regress them:
- Aave has the CoinGecko category "Stablecoin Issuer" (it issues GHO) → was
  mis-classed stablecoin. Fix: exclude "issuer", require an actual price peg, check
  DeFi before L1.
- ETH has DefiLlama fees → was mis-classed DeFi. Fix: the L1 id-set beats `has_fees`.

Live results: BTC → monetary (0.389 D → 0.562 C once class-aware), ETH → l1
(A, 0.85 in class mode), DOGE → meme, AAVE → defi, SOL → B (0.74 vs 12 L1s).

### Scoring consistency — the invariant

A token's tier must be **identical** whether it's the analyze subject, a peer in
someone else's report, or a screener row. Two independent causes of drift were fixed:

1. **Peer-set composition.** `config.yaml scoring.reference_anchored: true` → each
   feature is ranked by `normalize.percentile_of_score` against its class's *fixed*
   reference-basket distribution, not the ad-hoc universe. For an anchored class, a
   feature with no basket distribution is **excluded (NaN), never relatively
   normalized** — otherwise the peer set leaks back in. Classes with no basket
   (e.g. "general") fall back to relative, so the benchmark is unaffected.
2. **Fresh-vs-persisted data.** Analyze collects live; the screener reads the last
   persisted run (e.g. RPL `dev_commit_trend` 0.10 live vs 0.78 stored = a full tier
   swing). Chosen resolution: **live wins + self-heal** — `analyze_token(persist=True)`
   writes the fresh record back via `db.upsert_into_latest_run`, refreshing that
   token's row *in* the latest run rather than spawning a 1-token run. `_class_peers`
   merges basket + stored with stored winning on collision.

**Keep `reference_anchored` on. Do not revert to purely relative scoring.** To improve
anchored-feature coverage, enrich the baskets via `dyor reference` — don't re-enable
the relative fallback. `analyze_token` must not persist by default (tests aren't
DB-isolated); only the API opts in.

**Fixed 2026-08-24** (after the integration test found the anchor was not actually
fixed — see `docs/INTEGRATION-TEST-2026-08-24.md`): `reference_distributions` now
reads the **curated basket only** (the latest-persisted-run merge was removed — it
had made every persist move the yardstick, 29/32 scores and 6 tier flips from one
screener rebuild), and its cache is keyed per **(class, basket version)** where the
version is the basket's `max(updated_at)`, so a warm API worker converges with a
fresh CLI as soon as a `dyor reference` rebuild lands — no process restart needed.
To pay for the lost enrichment, `build_references` now resolves an `eth_contract`
per basket token (one coins_list call) so the anchor carries holder-concentration
and verification distributions, and the baskets were widened (defi 10 → 26 tokens,
l1 12 → 15). Companion fixes: Santiment gained an on-disk POST cache + a
UTC-midnight-rounded window (was burning the 1000/month free quota and drifting
`dev_commit_trend` between runs) and a `SLUG_OVERRIDES` map (polkadot →
polkadot-new, starknet → starknet-token, …); `float_ratio` is clamped to [0, 1].

### Core-domain penalty

`REQUIRED_DOMAINS` per class (defi and general require `fundamental`).
`_apply_core_penalty` **floors** a missing required domain (`missing_core_penalty`,
default 0.0) instead of renormalizing it away — so a DeFi app with no measurable
fees is actively penalized, while gaps in non-core domains stay forgiving. It's a
**runtime toggle**, threaded end to end: `score_universe(penalize_missing_core=…)`
→ `analyze_token` → `/api/analyze` + `/api/screener` query param → Next.js checkbox
(`api.ts penaltyParam`) → Streamlit sidebar. Default on.

### Confidence

`ScoreResult.tier_stability` = the fraction of ±20% per-domain weight perturbations
that keep the tier; `.confidence` (high/med/low) combines that with coverage.
Surfaced in serializers, CLI, API and web.

---

## 4. Surfaces

**CLI** (`dyor <cmd>`): `analyze` · `score` · `collect` · `screen` · `memo` ·
`barbell` · `backtest` · `benchmark` · `reference` · `refresh`

**FastAPI** (`dyor/api/app.py`, port **8077** — 8000 is taken by the HPLIP printer):
`/api/health` `/analyze` `/screener` `POST /screener/build` `/screener/build/{job_id}`
`/token-record` `/memo` `/screen` `/portfolio` `/barbell` `/backtest` `/chart`
`/narratives` `/classes` `/methodology` `/benchmark`

**Next.js** (`web/`, Next 14 + React 18 + TS + Tailwind, App Router):
Home · Analyze · Screener · Narratives · Tools · Methodology · API/MCP.
Components: `TokenReport`, `TokenLink`, `AppState`, `Markdown`, `PriceChart`, `Nav`, `ui`.

**MCP** (`dyor/mcp_server.py`, FastMCP, entry point `dyor-mcp`) — 11 tools:
`analyze_token` (flagship) · `resolve_token` · `compare_tokens` · `analyst_memo` ·
`screen_tokens` · `score_portfolio` · `build_barbell` · `backtest` · `narratives` ·
`asset_classes` · `methodology`. stdio by default;
`--transport streamable-http --port 8765` for hosted. This is the growth Phase-0
**agent-native distribution wedge**.

**Streamlit** (`dyor/app/dashboard.py`) — the original multi-page dashboard, still
present, superseded by the Next.js app.

### Notable UI behaviour
- Screener groups a real universe into **tier tabs (A/B/C/D)**, top-20 each; heavy
  collection runs as a **background job** (`dyor/api/jobs.py`, in-memory registry,
  daemon thread, poll every 3s) because a synchronous request would time out.
- Analyze uses `useSearchParams()` inside a Suspense-wrapped `AnalyzeInner`, so
  clicking a peer *while already on the page* re-runs the query.
- `web/components/AppState.tsx` — Context provider in the root layout plus a
  `useStickyState` hook, so Analyze / Screener / Tools / Narratives survive
  page-navigation unmount. Cleared on a full reload (accepted).

---

## 5. Deployment

`dyor.cryptoopsec.com` — **same-origin, no CORS**, one nginx vhost, three pm2 services:

```
dyor.cryptoopsec.com ──► 127.0.0.1:3010  Next.js   (pm2 "dyor-web")
       ├ /api/*, /openapi.json ─► :8077  FastAPI   (pm2 "dyor-api")
       └ /mcp                  ─► :8765  FastMCP   (pm2 "dyor-mcp")
```

Main site: `cryptoopsec.com` → `127.0.0.1:3000`, Express SPA, pm2 `OpsecSite`,
source at `/root/OpsecSite` on the VPS (that's the **canonical git repo** — the local
`OpsecSite` dir is not one). Its `client/src/components/tools-section.tsx` launch card
reads `VITE_DYOR_URL`.

Artifacts: `DEPLOY.md`, `SERVER-SETUP-HANDOFF.md`, `deploy/ecosystem.config.cjs`,
`deploy/nginx-dyor.conf`. DYOR ships to `/root/DYOR` by **rsync** (it wasn't a git repo
when the runbook was written — it is now, so a git-based deploy is available if wanted).
Ship `data/dyor.duckdb` along with it for the reference baskets.

Agents connect with no install:
`claude mcp add --transport http dyor https://dyor.cryptoopsec.com/mcp`

**Ops gotchas:** the `/mcp` nginx location needs `proxy_buffering off` and a long
`proxy_read_timeout` for the event stream · keep exactly **one** `dyor-api` (DuckDB is
single-writer) · **never** ship `web/.env.local` to the VPS, it overrides
`.env.production` in a prod build · killing `next-server` needs `kill <pid>`, a pkill
chain exits 144 early and leaves the old server on the port.

### Reskin
`web/tailwind.config.ts` is remapped to the CryptoOpsec cyber palette — bg `#050f19`,
panel `#0e1f2f`, panel2 `#192e43`, edge `#24384f`, brand gold `#c9a31d`, brand2
`#e3bd44`, muted steel `#7e96b8` — with Orbitron headings and Inter body. Semantic
A–D tier colours (emerald/sky/amber/rose) are deliberately kept.

---

## 6. Development environment

- **pip network is sandbox-blocked** — installs need `dangerouslyDisableSandbox: true`.
- **Big installs get OOM-killed** (exit 137). Install in small batches with
  `--only-binary=:all: --timeout 300 --retries 6`.
- **Editable install needs `--no-build-isolation`**: install `setuptools wheel` first,
  then `pip install -e . --no-build-isolation --no-deps`. This is also what's required
  to register a new console entry point (e.g. `dyor-mcp`).
- **Tests**: `. .venv/bin/activate && python -m pytest` runs unit only
  (`addopts = -m 'not integration'`). Full: `python -m pytest -o addopts="-ra"`.
  Re-record cassettes: `pytest -m integration --record-mode=once`. **Do not** set
  `record_mode` in the `vcr_config` fixture — it overrides the CLI flag.
- Time-windowed GraphQL cassettes match POSTs **by URL, in recorded order** (body is
  excluded from `match_on`); conftest no-ops `base.time.sleep` so Santiment's 10/min
  limiter doesn't slow replay.
- DefiLlama `/tvl/{slug}` returns **HTTP 200 with an empty body** for a protocol with
  no TVL (DePIN tokens like GEODNET, helium). `base._request_with_retry` treats an
  empty 200 as "no data", not a JSONDecodeError. So a red 🔴 feed means a genuine
  failure; not-found/empty is ⚪.
- Keyless CoinGecko is paced to **12/min** (auto-raises to 400 with a Pro key);
  `resolve` and `collect` **share one client** — two limiters caused 429s.
- **`dyor reference` 429s if run concurrently with any other CoinGecko caller.** Run
  it alone. It's resilient — partial baskets are fine.
- DuckDB is single-writer: never hold a connection open during a long collect.
- Streamlit `use_container_width` is removed after 2025-12-31 — use `width="stretch"`.

---

## 7. Where the build stands

**Done:** §1 Reliability · §2 Breadth · §3 Free features · §5 Ops — all complete per
`docs/STAGES.md`, plus asset-class scoring, penalty mode, the FastAPI + Next.js
product, the MCP server, the capability batch (confidence, class-aware peer sets,
screen, memo, portfolio/barbell, backtest), the CryptoOpsec reskin, and deployment.

**The only remaining feature work is §4, and all of it needs paid keys:**

| Gap | Blocked on |
|---|---|
| Precise `unlock_pct_of_volume` (next-event $ ÷ volume) | DefiLlama Pro `/emissions` (402) or CryptoRank v1. Metric + parser + wiring are already done; open v0 overhang covers the gating signal meanwhile. |
| Santiment `social_trend` | `DYOR_SANTIMENT_API_KEY` (restricted anonymously) |
| Exchange reserve-trend | Glassnode / CryptoQuant |
| Gini/Nakamoto beyond top-10; L2 & own-chain holders | Nansen / Covalent |
| Electric Capital dev taxonomy | `open-dev-data` DuckDB load |
| ETF flows | CoinGlass Standard (~$299/mo) |

**Threshold for buying a paid source** (a standing rule): only when the metric
*materially changes a score* AND cannot be derived from free sources.

**Standing principle (user directive):** when a feature is gated on one provider, find
an OPEN alternative for the same data rather than block on a key — even for a single
data point. This is why unlock overhang uses CryptoRank v0 and holder concentration
uses Ethplorer `freekey`. **Coverage gaps are honest `n/a`, never fabricated zeros.**

### Known limits
- BTC and L1s score on sparse coverage relative to the DeFi-tuned metric set;
  class profiles and peer-grouping mitigate but don't eliminate this.
- `value_accrual` is a **ratio** — it can read 1.0 with near-zero absolute yield
  (Uniswap). `real_yield` carries the magnitude; they're complementary, read both.
- Auto-built universes have no `github_org`, so the `dead_token` gate can only
  fall back to the low-volume criterion. **Verified 2026-08-24:** price drawdown
  was removed as a dead-token criterion (config + `gate.py` agree); `docs/STAGES.md`
  still claims otherwise and is stale on this point.
- **Three of the five gate rules are inert on live data.** `anonymous_team` and
  `no_audit` read `team_anonymous` / `audited`, which only exist in
  `sample_data.py` — the live collector never emits them. `unverified_contract`
  fires only on an explicit `False`, which open sources never produce. So live
  gating is effectively `extreme_fdv_mcap` + low-volume `dead_token`. The
  benchmark passes 4/4 because it runs on synthetic records that *do* carry
  those fields, so it does not cover this.
- `contract_verified` is True-or-None, never False — open sources can't prove a
  negative, and a false False could wrongly zero a score. The gate only fires on an
  explicit False, which means it effectively never fires on open data.
- Tier A needs a real universe's percentile spread; small benchmark sets top out at B.

---

## 8. Go-to-market

Phase 0 is **done** (2026-06-24), captured in `growth/dyor-instance.md`. The framing
that matters: **DYOR is already built**, so the validation surface is the real product
(the public Analyze page = the magic moment and the shareable artifact), not a fake
landing page. The questions are distribution → retention → willingness to pay.

- **Archetype:** prosumer-creator with an open-source / dev-tool distribution wedge.
- **ICP:** "the fundamentals-pilled holder" — crypto-native, concentrated portfolio,
  distrusts hype, already lives on DefiLlama + CoinGecko. *"14 tabs open to decide if
  a token is real — I want one honest read."* Secondary: indie analysts and creators
  who'll **cite** it (citation = distribution). **Anti-ICP:** memecoin degens and
  large institutions.
- **Channels, ranked:** ① Crypto Twitter/X ② Reddit organic ③ OSS + "Show HN"
  ④ Farcaster ⑤ creator collabs ⑥ TG/Discord. **Avoid:** Meta/TikTok paid,
  LinkedIn paid, Google search ads.
- **Kill-metric** (2-week organic seeding, pass = ALL): ≥1,000 unique analyses ·
  ≥25% 7-day return · ≥20 unsolicited organic shares · ≥3% Pro/alerts waitlist conversion.
- **Riskiest assumption:** will serious researchers *trust and act on* an opinionated
  tier, or dismiss it as another black-box screener and go back to raw free data?
  The mitigation bet is transparent, open methodology. Second risk: willingness to pay
  — crypto retail expects free, so the business may be API / pro-alerts / B2B.

**Not yet done:** Phase 1 competitor research (Token Terminal, Messari, Nansen,
Artemis, Kaito, DefiLlama, Glassnode) · Phase 2 positioning spec · Phase 3 visuals
(real screen recordings + score-card OG image, explicitly **not** AI hero art) ·
Phase 4 public validation surface (per-token `/t/<token>` URLs with OG score-cards,
Pro waitlist, usage analytics).

Since the site is already live, **Phase 4 is the natural next move** — per-token
shareable URLs are the thing the whole channel strategy depends on.

---

## 8b. September 2026 — review and hardening

A full code review on 2026-09-26 (`docs/CODE-REVIEW-2026-09-26.md`) found four
live production defects and 24 further issues; all were resolved and deployed
the same day. The important state changes:

- **CryptoRank's open v0 endpoint is dead** (Cloudflare, ~Sep 6–11). The client
  now uses the keyed v3 API; the deployed key is on the **Sandbox** plan, which
  has no vesting endpoints, so the feed reports `off` and `unlock_overhang` is
  `n/a` for live tokens. Upgrading to Pro re-enables it (and adds next-unlock
  USD for `unlock_pct_of_volume`) with no code change.
- **`refresh` now prints per-source feed counts**, and a `feed_outage` critical
  alert fires when any source errors on ≥50% of tokens.
- **The universe can no longer shrink by accident**: every persist goes through
  `db.persist_run` (refuses < 50% of the previous run unless `--force`), the API
  build unions the baskets, is admin-gated (`DYOR_ADMIN_TOKEN`, unset → disabled)
  and flocks the same `data/.collect.lock` as the cron. The public Build button
  is gone.
- `/api/analyze` refreshes tokens in place only; it never adds to the board.
- **nginx per-IP rate limits** on the live-collection endpoints and `/mcp`;
  app-side semaphore on live analyses; portfolio capped at 10.
- Web on **Next 16.3.6 / React 19**, 0 production advisories.
- Server: `.env` (mode 600) holds the CryptoRank key; pm2-logrotate installed;
  cron wrapper uses the shared lock path.

## 8c. September 2026 — data-source coverage pass

Audit question: is every supplier's schema parsed, is anything dropped, and does
each token get every feed free data allows? Baseline (Sep 20 run, 117 tokens):
**42.9% of class-spec feature slots had data**; 106 slots belonged to features
with no source at all; L1 `mc_tvl` was 1/17; Santiment resolved 59% of tokens.
Changes (commit `e68acd2`, `docs/DATA-COVERAGE-2026-09-26.md` has the numbers):

- Specs list only producible features (`inflation_rate`, `reserve_trend` out);
  `watchlist_users` (CoinGecko watchlist count) added to every class.
- CoinGecko `coin_meta` yields TVL (fallback for slug-less tokens), watchlist,
  supply flags and repo URLs in the same call. `developer_data` /
  `community_data` are null on the free tier — not requested.
- DefiLlama chain-level fees/revenue/TVL for L1s; protocol `github` and
  `audits` flow into Targets. **`no_audit` now fires on open data** (an explicit
  "0" on DefiLlama; any audit link counts as audited) — ~26 of the top-80
  protocols are capped at 0.5 by design. Disable by removing the rule from
  `config.yaml gating.rules` if that is not wanted.
- Santiment slug map by id / main contract / name / unique ticker (68 → 94/116).
- Sourcify on six EVM chains; GitHub org auto-discovered; the feed is gated
  on `DYOR_GITHUB_TOKEN` (anonymous is 60/hour). **Configured 2026-09-26**: a
  fine-grained token (public repositories, read-only, no extra permissions) in
  the local `.env` and `/root/DYOR/.env`; API/MCP restarted; `_feeds.github`
  is `ok` on live analyses. The `dead_token` gate's no-commits-in-180-days
  criterion is therefore active from the next refresh (Sun 2026-09-28).
  **A no-persist preview collect of the full universe showed it would have
  zeroed Solana, NEAR, BNB, USDC, TUSD, BCH and Balancer**: CoinGecko's repo
  URLs still point at `solana-labs`, `nearprotocol`, `binance-exchange`,
  `centrehq`, `balancer-labs` — orgs development left years ago — and
  `/orgs/{name}` 404s for user accounts (convex-eth, resupplyfi, GMX's xvi10),
  which read as "no repos". Fixed the same day: the collector checks EVERY
  discovered account (DefiLlama list + all CoinGecko repo URLs + verified
  `GITHUB_ACCOUNT_OVERRIDES` for the migrated majors, user accounts via
  `/users/` fallback, max 4) and keeps the most recent push (`_github_account`
  on the record says which); the gate's no-commits criterion is overruled when
  Santiment's dev-activity window shows events (`dev_activity_events`, a new
  gate input). Santiment alone was not enough — its repo lists for USDC,
  Balancer, Maker and BCH are stale too — hence the overrides.
- **2026-09-27 — the report shows its working; scores are 0–100.** The token
  page's "The numbers behind it" list is replaced by a ledger: for every
  feature of the token's class, the raw figures (which fees window, both sides
  of each ratio, the Santiment window means, the ten holder shares …) with the
  feed they came from, the formula with those figures substituted, the value,
  its percentile against the reference basket (and the basket size), its weight
  in the composite and the points it adds; then the domain roll-up
  (weight → renormalized weight → domain score → points = raw score), every
  gate rule with its evidence and result, and the tier thresholds. Missing
  features say why (feed empty/off/error, keyed source, undefined ratio).
  Server side: `build_record` keeps `_inputs`, the pipeline keeps per-feature
  percentiles on `ScoreResult`, `dyor/explain.py` builds the ledger, and
  `analyze_to_dict` serves it as `explain`. The "Data sources" card links each
  feed to its own page for the token (`_sources` on the record) and carries a
  key for the four feed states (ok / empty / error / off). **Presentation scale
  is now 0–100** everywhere a human reads a number — API/MCP JSON
  (`scale: 100`), web, CLI, memo, alerts; tier thresholds and gate caps in the
  methodology are 0–100 too. The engine still computes in [0, 1]; only
  `scoring.composite.display()` converts, so no weight, threshold or cap moved.
- **2026-09-27 — score stability (user: "extreme jumps for non-core reasons
  must not occur; a busy or quiet month of commits is not a signal").** The
  Sunday run had moved Bitcoin 76.9 → 54.8 (B → C). Attribution found three
  non-core causes, all fixed: (1) `percentile_of_score` was a step function —
  Bitcoin's float ratio flickering between 0.99998 and 1.0 (provider rounding)
  crossed three basket coins sitting at exactly 1.0 and moved two percentiles
  by 50 points each; it is now a linearly interpolated CDF (ties share their
  mean position, 0 = worst peer, 1 = best), continuous and monotone. (2) The
  monetary basket had 7 coins (one rank ≈ 17 points); monetary / meme /
  stablecoin were widened to 13 / 14 / 14 with verified coins (`dyor
  reference` rebuilt; the new coins' Santiment features fill in via the
  `dyor-reference-refill` timer on 2026-10-02 because the monthly budget is
  spent). (3) The scored dev signal is now `dev_activity` — mean events/day
  over the window, a sustained level ranked against class peers — instead of
  the month-over-month `dev_commit_trend` (kept, informational). Measured on
  the same two weekly runs, dev excluded from both for like-for-like: median
  |Δ| 1.2 → 0.5 points, p90 8.0 → 5.5, >5-point moves 26 → 12, tier flips
  18 → 10 of 113; Bitcoin 76.2 → 71.2 (B → B). Remaining large moves are gate
  events. One-time re-anchoring came with it (e.g. Aave 47 → 38: its +158 %
  dev-trend month no longer buys a perfect dev score; Uniswap 33 → 46; the
  stablecoins rose). Still open: `address_growth` is a 28-day trend on a 7-value
  stablecoin/monetary distribution — a 90-day window (30-day means) is the next
  smoothing step once Santiment's budget resets (untestable while exhausted).
- **2026-09-27 — the anchor could silently vanish under load.** The reference
  loader opened DuckDB read-write while request threads held read-only
  connections; DuckDB refused ("different configuration than existing
  connections"), `_load_reference_dist` swallowed it and the request scored
  UNANCHORED — the same token 54.8 on one call, 58.5 on the next. Fixed: the
  loader is read-only, retries briefly, keeps the last good anchor per process,
  and raises `ReferenceUnavailable` (API → 503, Retry-After 5) rather than
  answer on a different scale. `refresh_in_latest_run` now refuses a record
  whose feeds errored where the stored one's did not; `SantimentClient`
  short-circuits once the monthly budget 429 appears. See DEPLOY.md.
- **2026-09-27 — DefiLlama dropout (user: Uniswap "off" despite a full
  DefiLlama page).** Root cause: DefiLlama's `/protocols` lists protocol
  *versions* (Uniswap V2/V3/V4, Aave V2/V3 …) whose `gecko_id` is empty; the
  token's id sits on the *parent* protocol, which only `/lite/protocols2`
  exposes and we never read. Uniswap therefore had no slug at all, and Aave
  matched the one version still carrying an id — `aave-v2`, $113M of a $19B
  protocol, whose fees made its P/F 1300× instead of 3×. Audit over the 135
  universe + basket tokens: parent-aware matching 80 → 99; 19 tokens gained
  their page (Uniswap, Curve, Compound, GMX, Morpho, PancakeSwap, Pendle,
  Raydium, Jito, Ethena, Aerodrome, Velodrome, Balancer, Yearn, Stargate …),
  8 moved from one version to the aggregate (Aave, Jupiter, Sushi, 1inch,
  Frax, Benqi …); the 36 still without a page are monetary coins, memecoins
  and stablecoins that genuinely have none. Fix: `universe.fold_parent_protocols`
  adds one synthetic row per parent (slug = parent slug, whose `/summary/fees`
  and `/tvl` serve the aggregate; tvl = Σ versions so it wins the
  highest-TVL pick; audits / github merged; `children` for a fallback when a
  parent serves nothing, e.g. bonkfun); `best_by_gecko` used by the universe,
  the baskets and analyze alike; `Target.defillama_fallback_slug`; a chain
  token that matches a Bridge/CEX/Chain row keeps chain-level fundamentals
  (DefiLlama files those as "Canonical Bridge" — its "solana" row is one — and
  the Ethereum Foundation treasury as "Foundation"; `UMBRELLA_CATEGORIES`
  covers them, and a zero TVL from such a row no longer blocks the chain
  fallback). That alone corrected Solana's P/F 298× → 19×, Sui 3938× → 58×,
  Aptos 649× → 32× and gave Ethereum an MC/TVL. Two basket ids were wrong: SNX is
  `havven`, MKR migrated to `sky`. The stored run's DefiLlama-derived fields
  were recomputed in place (100 of 114 now `ok`, was 84) and the baskets
  rebuilt; the Santiment-dependent fields were left alone (budget spent).
- **2026-09-27 — Santiment window 28 → 90 days** (`ingestion.sources.
  santiment.window_days`; anonymous access serves ≥ 400 days): the growth
  reduction compares first and last thirds, so `address_growth` is now a
  30-day-mean vs 30-day-mean trend and `dev_activity` a 90-day level. First
  used by the 2026-10-02 timer (`dyor reference`, then the weekly refresh so
  the board matches the anchor); until then live analyses hit the exhausted
  budget and the persist guard keeps the board intact.
- **2026-09-30 — a tweet quoted "6260/100" for ETH's fundamentals.** Three
  defects in what we hand a reader, all fixed: (1) a feed that failed on a live
  collect (Santiment over its monthly budget) left its domains out and the
  weight was redistributed — Ethereum read 76 (B) live against 52 (C) on the
  board; `dyor/feeds.py` now maps feeds to fields and `analyze` carries the
  last stored values forward for a feed that errored (`stale`, dated), while a
  feed that still errors yields a "provisional" advisory naming the affected
  domains; (2) nothing said the numbers were already 0–100 — `analyze_to_dict`
  carries `scale: 100` and a quotable `summary` (class, score/100, tier, each
  domain with its weight, coverage, caveats, "do not rescale"), and the MCP
  instructions say the same; (3) only the DeFi default weights were exposed —
  `class_to_dict` carries the class's own weights, methodology returns
  `class_weights`, the methodology page shows them. Live ETH now 54.3 C ==
  board.
- **2026-10-04 — SEO layer.** The app had one shared title on every page, no
  OG/Twitter cards, canonical, robots, sitemap, manifest, favicon.ico or
  structured data, and nothing token-specific indexable (reports lived behind
  a client-side `?q=`). Now: `web/lib/seo.ts` (identity, `pageMeta`, JSON-LD
  builders); root metadata with template/keywords/robots/manifest/verification
  and Organization + WebSite(SearchAction) data; per-route metadata; permanent
  server-rendered **`/token/<gecko_id>`** pages (ISR hourly, full report in
  HTML, BreadcrumbList + WebPage data, per-token Open Graph score card via
  `next/og`, unknown ids → live analysis) fed by new **`/api/token`** and
  **`/api/tokens`** (stored board, cached per board version); crawlable
  **`/tokens`** index; `/methodology` server-rendered with FAQPage data;
  robots.ts, sitemap.ts (all token pages), manifest.ts, icons, not-found;
  self-hosted fonts (`web/app/fonts`, offline build); `X-Powered-By` off,
  content security headers in `next.config.mjs`, HSTS snippet in nginx.
  `web/.env.production` gained `API_URL=http://127.0.0.1:8077` (server-side
  fetches over loopback) and `NEXT_PUBLIC_DYOR_URL`. Still manual: submit the
  sitemap in Search Console / Bing (property = the `dyor.` subdomain) and set
  `NEXT_PUBLIC_GSC_VERIFICATION` / `NEXT_PUBLIC_TWITTER_HANDLE`.
- `universe.make_target` is the one enrichment path for universe, baskets and
  analyze, so the anchor and live records share feature sets. Baskets rebuilt.
- **2026-10-04 (later): share, ranked screener, compare, plain punctuation.**
  `TokenReport` carries a `ShareBar` (copy link, post on X via the intent URL,
  native share, copy the `summary` paragraph) and a "Compare with other tokens"
  link. The screener (`web/app/screener/page.tsx`) now ranks the stored board by
  composite score, any domain or any scored metric (best or worst first, presets
  such as best real yield or most concentrated holders) from the new
  `GET /api/tokens?detail=true` payload (`domain_scores`, `features`,
  `percentiles`, `market`, `advisories`), with class, tier, gate-flag and
  coverage filters and a checkbox selection of up to 6 tokens. `/compare?tokens=`
  (server-rendered, `GET /api/compare?ids=`) lays those tokens out line for line:
  score, domains with weights, every per-domain metric from the ledger, market
  figures and feed states, best value per row marked. `web/lib/metrics.ts` is the
  single list of rankable metrics. All reader-facing copy (web, API strings,
  advisories, memo, alerts, MCP instructions, tier labels in `config.yaml`) was
  rewritten without em or en dashes, middle dots, arrows, ellipses or `≥ ≤ ×`;
  tier labels are now `"C (watchlist)"` style, so anything parsing the old
  `"C — watchlist"` form must use the parenthesised word.
- **2026-10-04 (later still): tab persistence.** The sticky store
  (`web/components/AppState.tsx`) is now mirrored to `sessionStorage` and
  restored after mount, so screener ranking, filters, selection, the analyze
  query and result, tools inputs and results survive tab switches and reloads.
  The Compare tab returns to the compared set (`compare:ids`), the token page's
  compare link appends to it, and the screener keeps its loaded board in memory
  so returning is instant. `web/scripts/tab-persistence.mjs` drives a headless
  Chrome over the DevTools protocol through 18 checks.
- **2026-10-04 (evening): responsive pass.** Measured with real phone and
  desktop screenshots (`web/scripts/screenshots.mjs`). The header no longer
  wraps into three rows on a phone (brand row + scrolling tab strip); the
  screener, token index, token ledger and gate tables, and the methodology
  glossary stack into cards under `md`; the compare table pins its label
  column and scrolls sideways; the methodology and API pages no longer
  overflow (grid items are `min-width: 0`); touch targets and form controls
  were enlarged; narratives load on first visit. Every route reports zero
  sideways overflow at 390px and 1366px.
- **2026-10-04 (night): CryptoOpsec Accounts.** A separate wallet-only sign-in
  service (EVM via EIP-4361, Solana via Sign-In With Solana) at
  accounts.cryptoopsec.com, built in the sibling `Accounts/` repo: Hono +
  Postgres, ES256 access cookie for `.cryptoopsec.com` with `plan`/`feat`
  claims, rotating refresh with reuse detection, hosted login/account pages
  under a strict CSP, export and delete. DYOR became its first relying app:
  `dyor/api/auth.py` (offline JWT verification, `require_feature` ready for the
  paid tier), `GET /api/me`, and a sign-in menu in the header. Nothing is gated
  yet; the paid tier will cover MCP, API keys, Tools and pro data sources.

## 9. Gaps in this reconstruction

Honest about what couldn't be recovered:

- **Everything after 2026-06-28 14:35 is undocumented.** The git init and commit
  (2026-07-02) and the production deployment happened in sessions whose transcripts
  are gone. There is no record of *why* specific deploy decisions were made, or of
  anything attempted and rejected.
- `/api/chart`, `/api/token-record`, `web/components/PriceChart.tsx` and
  `web/app/api-mcp/page.tsx` exist in the tree but appear in no memory file — they
  were built in lost sessions. Their intent is inferable from the code only.
- Whether the server's DuckDB has been refreshed since deploy is **unknown** — the
  local copy's newest run is 2026-06-23. If `dyor refresh` isn't on cron up there,
  production may be serving two-month-old stored data (Analyze still collects live).
- Rejected alternatives, dead ends, and tuning rationale for `config.yaml` weights
  are lost beyond what the docs state.
