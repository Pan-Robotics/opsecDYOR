# Code Review — 2026-09-26

**Scope:** every Python module in `dyor/` (5,971 lines), the Next.js app (`web/`,
1,945 lines), the test suite (18 files, 190 tests, 61% coverage), deploy config,
and a production health check one month after the last deploy. Static analysis
with ruff; SQL, secrets and tracked-file hygiene checked; production `_feeds`
telemetry, access logs and refresh history inspected on the VPS.

**Headline:** the scoring core is clean and the August fixes have held for four
consecutive weekly runs. But three production-impacting problems are live right
now, and one of them has been silently degrading every score for two weeks.

| Sev | ID | Finding | Status |
|---|---|---|---|
| **HIGH** | H1 | CryptoRank v0 dead (Cloudflare 403) since ~Sep 6–11 — `unlock_overhang` missing from every score, no alert fired | **live now** |
| **HIGH** | H2 | Public screener "Build" button shrinks the pinned universe (jobs.py ignores baskets) — already fired in prod on Sep 11 | **live now** |
| **HIGH** | H3 | `/api/analyze` hardcodes `persist=True` — any visitor writes to the public screener | **live now** |
| **HIGH** | H4 | No rate limiting on unauthenticated endpoints that trigger live upstream collection | **live now** |
| MED | M1 | User input interpolated into upstream CoinGecko URL paths (path/query injection) | |
| MED | M2 | Methodology copy overclaims: drawdown gate (removed) and three inert gate rules shown as active | |
| MED | M3 | Classifier makes any token with a DefiLlama entry `defi` — L1s outside the id-set get penalised | |
| MED | M4 | Ethplorer rate-limit errors arrive as HTTP 200 + error body → reported as "empty" | |
| MED | M5 | DefiLlama Pro key would be logged in the failure message (latent) | |
| MED | M6 | GitHub limiter assumes a token (80/min); real unauthenticated cap is 60/hour | |
| MED | M7 | CoinGecko `markets()` silently truncates at 250 ids | |
| MED | M8 | CoinGecko Demo keys are sent as Pro keys to the Pro host | |
| MED | M9 | `dyor refresh` with no `--top-n` persists the 6-token curated set (shrinks screener) | |
| MED | M10 | Next.js 14.2.15: 1 critical + 2 high advisories | |
| MED | M11 | Tests touch the real DuckDB; the modules with the bugs above are 9–45% covered | |
| LOW | L1–L13 | Dead schema/code, hard Streamlit dep, cache growth, thread-unsafe limiter, doc drift, ops hygiene | |

---

## Production state (2026-09-26)

- **Cron: 4/4 Sunday runs OK** — Aug 30 (1902s), Sep 6 (1996s), Sep 13 (1850s),
  Sep 20 (2035s). ~32 min is nominal for sequential rate-limited collection of
  ~117 tokens; the 988s Aug 24 run was cache-warm.
- **Feed errors: 2 → 116 → 116** across the last three cron runs. The per-record
  `_feeds` map (stored in every row, read by nothing) shows `cryptorank: error`
  for **100% of tokens** in every run since Sep 11. See H1.
- **Unexpected run** `20260911T013544105818Z`, 31 tokens, 01:35 UTC — not the
  cron. API log: `POST /api/screener/build` from 24.56.150.3 (external). See H2.
- **Usage:** 115 `/api/analyze` calls from 24 distinct IPs in a month. Real traffic.
- All 4 pm2 services online, 0 restarts since deploy; DB 1.6 MB / 864 rows / 19
  runs; `.cache` 63 MB and growing (L4); pm2-logrotate not installed (L12); the 7
  5xx in the API log are all the stale Aug 24 lock error, none new.

---

## HIGH

### H1 · CryptoRank v0 is dead — every score has been missing `unlock_overhang` for ~2 weeks

**Evidence.** `_feeds.cryptorank == "error"` for 31/31, 114/114 and 117/117
tokens in the Sep 11, 13 and 20 runs (Sep 6: 2 errors total). Direct probe from
both local and the VPS: `GET https://api.cryptorank.io/v0/coins/aave` → **HTTP
403, `text/html`** — a Cloudflare challenge page. Browser User-Agent, `Accept`,
`Origin` and `Referer` headers do not get through. The endpoint was
undocumented; [`cryptorank.py`](../dyor/ingestion/cryptorank.py) said so.

**Impact.** `unlock_overhang`, `num_vc_backers`, `had_public_sale` are `None`
for every live token. `unlock_overhang` is in the tokenomics spec of **all five
classes**, so every token's tokenomics domain now averages one fewer feature —
that is the score shift behind the 19 and 69 alerts on Sep 13 and 20.
`unlock_cliff` alerts can never fire. The reference baskets (collected Aug 24)
still carry the feature, so live tokens are anchored against a distribution they
can no longer be measured on; the next `dyor reference` rebuild strips it from
the anchor too.

**Why nobody knew.** `_cmd_refresh` prints `116 feed error(s)` and nothing else.
The information to diagnose it was persisted in every record and never surfaced.

**Fix.**
1. *Diagnostics (do regardless):* `refresh` prints per-source error/empty/ok
   counts; add a `feed_outage` **critical** alert when a configured feed errors
   on ≥ 50% of tokens in a run. Add it to the sweep too.
2. *Source:* CryptoRank v0 is gone for keyless clients. `DYOR_CRYPTORANK_API_KEY`
   already exists in `Settings`; the documented API has a free tier — port
   `coin()` to the keyed endpoint. Until then, mark the feed `off` rather than
   `error` so coverage reflects reality.

### H2 · The public "Build / refresh" button shrinks the pinned universe

**Evidence.** [`jobs._run_build`](../dyor/api/jobs.py) calls
`fetch_universe(top_n, category)` with no `include_baskets`, persists a new run,
and `latest_records` returns it. The screener UI defaults `topN` to 30. Run
`20260911T013544105818Z` (31 tokens) is exactly that: a visitor clicked the
button on Sep 11 and the public screener dropped from 114 tokens to 31 — no BTC,
no ETH, no memecoins, no stablecoins — until the Sep 13 cron restored it.

**Also:** the endpoint is unauthenticated and unthrottled. Each call starts a
~25-minute collect (~120 Santiment calls of a 1,000/month quota); concurrent
calls spawn concurrent collectors with independent rate-limit buckets (429
storm) and race each other and the cron on the DuckDB write lock.

**Fix.**
1. `include_baskets=True` in `jobs._run_build` (one line).
2. A **shrink guard** in the persist path: refuse a new run smaller than 50% of
   the previous unless explicitly forced. This also closes M9 and the
   `dyor collect --persist` footgun.
3. The weekly cron makes a public rebuild redundant — remove the button or put
   it behind an admin token; at minimum `limit_req` it and serialise builds
   with the same flock the cron uses.

### H3 · `/api/analyze` is a public write path

[`app.py:66`](../dyor/api/app.py) calls `analyze_token(..., persist=True)`
unconditionally. Every visitor's analysis is upserted into the latest run and
appears in the public screener's tier tabs. The frozen anchor means it no longer
moves other scores (fixed in August), but it still lets anyone inject any
CoinGecko-listed token into a public ranking. 24 distinct IPs have used analyze.

**Fix.** Make the "self-heal" a genuine refresh-in-place: persist only if the
token is *already* in the latest run. New tokens go to a separate
`analyzed_tokens` table (still available for peer tables) or nowhere.

### H4 · No rate limiting on endpoints that trigger live upstream collection

`/api/analyze`, `/api/memo`, `/api/portfolio` (up to 25 live analyses per
request), `/api/screener/build` and `/mcp` are unauthenticated with no nginx
`limit_req` and no application throttle. One analyze ≈ 10 upstream calls
including 2 Santiment calls against a 1,000/month quota; an exhausted quota
silently drops two features and moves scores (the drift class fixed in August).
Sync endpoints also block uvicorn's default 40-thread pool for 30–90 s each, so
~40 concurrent analyses stall `/health` as well.

**Fix.** `limit_req_zone` per IP on `/api/` and `/mcp` in
[`nginx-dyor.conf`](../deploy/nginx-dyor.conf); cap portfolio at ~10; a
process-wide semaphore around live collection.

---

## MEDIUM

**M1 · Path/query injection into upstream URLs.**
[`resolve.py:170`](../dyor/resolve.py) `client.coin_detail(q)` and
[`app.py:191`](../dyor/api/app.py) `cg.market_chart(id, …)` interpolate raw user
input into CoinGecko URL paths. `q = "../simple/price?ids=bitcoin&vs_currencies=usd"`
reaches an arbitrary CoinGecko GET endpoint through the server and caches the
result under our key. Blast radius is CoinGecko-only and GET-only — but a
configured Pro key would be spent on arbitrary endpoints. Validate against
`^[a-z0-9-]{1,100}$` before building a URL.

**M2 · Methodology copy overclaims.** The product's positioning is
"transparent, not a black box", so this matters. [`page.tsx:134`](../web/app/page.tsx)
says a dead token is "no commits 6mo+, **~99% off ATH**, near-zero volume" —
drawdown was deliberately removed from the gate. The methodology page lists all
five config gate names as active; `anonymous_team` and `no_audit` read fields the
collector never emits, and `unverified_contract` needs a `False` open sources
never produce. Say so on the page ("not active on open data").

**M3 · Classifier over-assigns `defi`.** [`classes.py:186`](../dyor/classes.py):
`has_fees or defillama_category or …` → `defi`. `analyze._defillama_index`
includes *every* DefiLlama protocol, including `Chain`/`CEX`/`Bridge` categories
(the universe builder excludes them; analyze does not). An L1 outside the
hardcoded `L1_IDS` gets the DeFi profile, is penalised for "no fundamentals",
and lands in D. Treat `Chain` as an L1 signal and ignore excluded categories.

**M4 · Ethplorer failures are invisible.** Ethplorer returns errors — including
`freekey` rate limits — as HTTP 200 with `{"error": {...}}`;
[`ethplorer.py:39`](../dyor/ingestion/ethplorer.py) `payload.get("holders", [])`
turns that into `[]` → `_feeds` says `empty`. A rate-limited Ethplorer reads as
"no holders". Raise on an `error` key.

**M5 · DefiLlama Pro key leaks into logs (latent).**
[`defillama.py:91`](../dyor/ingestion/defillama.py) puts the key in the URL path;
[`base.py:160`](../dyor/ingestion/base.py) interpolates the URL into
`RuntimeError`. No key is configured today. Redact before it is.

**M6 · GitHub limiter assumes a token.** `default_rate_per_min = 80`
("5000/hr authed") but no token exists on the server; the unauthenticated cap is
60/**hour**. Works today only because 13 targets set `github_org`. Mirror
CoinGecko's key-aware rate selection.

**M7 · `markets()` truncates silently at 250 ids** (`per_page: 250, page: 1`).
The universe is 117; a top-N near 190 with baskets would drop tokens with no
error. Paginate or assert.

**M8 · Demo vs Pro CoinGecko keys.** Any key is sent as `x-cg-pro-api-key` to
`pro-api`. A free Demo key — the likely first upgrade — needs `x-cg-demo-api-key`
on the public host, so it would 401 everywhere.

**M9 · `dyor refresh` with no `--top-n`** collects the 6-token `DEFI_TARGETS` and
persists it as the latest run. The wrapper always passes `--top-n 60`, but the
footgun is one forgotten flag away. Closed by the H2 shrink guard.

**M10 · Next.js 14.2.15.** `npm audit --omit=dev`: 1 critical (Next DoS via
Server Actions), 2 high (postcss XSS in CSS output; nanoid). Server Actions are
not used, so the DoS vector likely does not apply, but it is a pinned, unpatched
framework on a public site. `npm audit fix` for nanoid; bump to the latest
14.2.x; plan the 15/16 major.

**M11 · Tests.** 190 pass, 61% coverage. The modules where every HIGH finding
lives are the least covered: `analyze.py` 28%, `portfolio.py` 9%, `jobs.py` 37%,
`mcp_server.py` 45%, `cli.py` 22%, `dashboard.py` 0%. API tests exercise code
that opens the **real** `data/dyor.duckdb` (`test_backtest_endpoint`, stored
screener) — no `DYOR_HOME` isolation fixture. No test would have caught H2 or
H3. Add an autouse fixture pointing `DYOR_HOME` at `tmp_path`, and tests that
assert a build preserves the basket tokens and that analyze does not persist
unknown tokens.

---

## LOW / hygiene

- **L1 · Dead schema and code.** `raw_responses`, `crosswalk`, `land_raw`,
  `latest_raw`, `build_crosswalk`, all of `identity/resolver.py`: 0 rows, never on
  the live path; `db.py`'s docstring ("every API response, verbatim") is false.
  Also unused: `onchain.top_n_concentration/gini/nakamoto_coefficient/trend_slope`,
  `github.repo/contributors/weekly_commit_activity`,
  `defillama.prices_current/fees_overview/stablecoins/protocol`.
- **L2 · Streamlit is a hard dependency** (`pyproject` `dependencies`) for
  `dyor/app/dashboard.py` — 670 lines, 0% coverage, superseded by the Next.js app,
  but still first in the README. Move to an optional extra or delete.
- **L3 · `.env` resolved from CWD** (`env_file=".env"`), not `PROJECT_ROOT`.
  Fine under pm2; silently ignored when `dyor` runs from anywhere else.
- **L4 · Cache and limiter.** `FileCache.set` is non-atomic (`write_text`;
  half-written files read as misses — use tmp+rename); nothing evicts expired
  entries (63 MB on the VPS; the Santiment positive cache gains ~230 files/week
  forever because the day-rounded window is a new key each run); empty-body
  responses are never cached (`None` → miss) so no-TVL protocols are refetched
  every run. `RateLimiter` is per-instance and not thread-safe: concurrent API
  requests each get a fresh 12/min CoinGecko bucket, the aggregate exceeds the
  per-IP limit, and the 429 backoff `time.sleep`s inside uvicorn worker threads.
  A process-wide limiter per source fixes both.
- **L5 · Store.** `connect()` runs `CREATE TABLE IF NOT EXISTS` on every open, so
  every read is a write-lock open; readers could use `read_only=True` and only
  persist/upsert need RW. No index on `token_records(run_id)`; `latest_records`
  scans and sorts all rows; history is append-only with no retention (864 rows,
  +117/week).
- **L6 · `jobs._JOBS` never pruned;** the screener's poll chain has no `catch`,
  so a transient fetch error leaves the UI on "Building…" forever.
- **L7 · `to_tier` assumes `config.yaml` tiers are sorted descending** — sort in code.
- **L8 · Web.** `Markdown.tsx` strips every underscore (`price_to_fees` renders as
  `pricetofees`); no XSS (no `dangerouslySetInnerHTML`) and links carry
  `noreferrer` — good — but `href`s from CoinGecko data are rendered raw; filter
  to `http(s)`. The screener drops N/A-tier tokens from every tab silently.
  `BacktestTool.run` has no `catch`.
- **L9 · MCP.** `analyze_token` defaults `peer_mode="stored"` (API/CLI default
  `class`) and its docstring omits `class`; `screen_tokens` recommends
  `dyor collect --top-n N --persist`, which now shrinks the universe.
- **L10 · Doc drift.** README pipeline diagram and layer table (Streamlit,
  raw-response landing, crosswalk); README/`docs/mcp.md`/`screener/page.tsx`
  all recommend the universe-shrinking `collect --persist`;
  `ecosystem.config.cjs:20` still says "non-editable"; `api/app.py:3` says port
  8000; `ethplorer.py` mentions a config key that does not exist.
- **L11 · Static analysis.** `collect.py:419` closure captures the loop variable
  `market` (harmless — invoked in the same iteration, Pro-only path); unused
  imports in `test_api.py`/`test_classes.py`; `memo.py:78` f-string with no
  placeholders. No linter or type checker is configured — add ruff to `[dev]`.
- **L12 · Ops.** pm2-logrotate not installed (uvicorn INFO goes to `*-error.log`,
  800 KB+ and growing); the MCP error log is 15 startup cycles of lifecycle noise
  plus `CancelledError` on shutdown — benign; no `.env` on the server, so no
  alert webhook and every refresh's alerts go only to the log.
- **L13 · Refresh diagnostics.** `_cmd_collect` prints each feed error;
  `_cmd_refresh` prints only the count. The cron is the path that runs
  unattended and is the one with no detail.

---

## What is solid

- SQL is fully parameterised; git history has no secrets; `.env`, the DuckDB
  file and `.cache` are untracked; cassette recordings filter key headers.
- The scoring core — `normalize`, `composite`, `gate`, `pipeline`, `classes` —
  is pure, 93–100% covered, and the frozen-anchor invariant has held across four
  weekly runs with no unexplained drift.
- Metrics consistently return `None` on missing or non-positive input; clamps
  are in place where providers misreport.
- `BaseClient` does the right things: cache before limiter, retry with
  backoff, `Retry-After` honoured, empty-body handled, 4xx not retried.
- The MCP server keeps DNS-rebinding protection on, binds loopback, exposes
  read-only tools (`persist=False`) and trims peer lists.
- The Markdown renderer is safe; external links use `noreferrer`.
- The refresh wrapper (flock, logging, rotation, distinct exit codes) worked
  unattended four times out of four.

## Suggested order

1. H1 — per-source counts + `feed_outage` alert (30 min), then the CryptoRank port.
2. H2 — `include_baskets` in jobs + shrink guard + throttle or remove the button.
3. H3 — refresh-in-place persist semantics.
4. H4 — nginx `limit_req`, portfolio cap.
5. M1, M2, M10 — input validation, honest methodology copy, Next patch.
6. M11 — `DYOR_HOME` test isolation, then tests for H2/H3.
7. Everything else as hygiene passes.
