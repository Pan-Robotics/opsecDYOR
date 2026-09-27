# Deploying DYOR as a CryptoOpsec app tool

DYOR runs as its **own service** at `https://dyor.cryptoopsec.com`, launched from the
**Tools** section of the main site. Three processes behind one subdomain (same origin,
so no CORS):

| Process   | What                       | Bind                | pm2 name   |
|-----------|----------------------------|---------------------|------------|
| FastAPI   | scoring engine             | `127.0.0.1:8077`    | `dyor-api` |
| Next.js   | the UI                     | `127.0.0.1:3010`    | `dyor-web` |
| FastMCP   | hosted MCP server (agents) | `127.0.0.1:8765`    | `dyor-mcp` |

nginx routes `/api/*` + `/openapi.json` → FastAPI, `/mcp` → the MCP server (streaming),
everything else → Next.js. Agents connect at `https://dyor.cryptoopsec.com/mcp` — no install.

Prereqs (already on the cryptoopsec.com box): **node, python ≥3.10, pm2, nginx, certbot**.

---

## 1. DNS

Add an **A record**: `dyor.cryptoopsec.com` → the VPS IP (same box as the main site).

## 2. Copy DYOR to the VPS

DYOR is not in the OpsecSite git repo — sync it to `/root/DYOR`. From your machine:

```bash
rsync -av --delete \
  --exclude node_modules --exclude .venv --exclude .next \
  --exclude __pycache__ --exclude '*.pyc' --exclude .pytest_cache \
  "/home/alexdada555/Documents/Crypto Opsec/DYOR/" root@<VPS_IP>:/root/DYOR/
```

> Keep `data/dyor.duckdb` in the sync (it's NOT excluded). It holds the reference
> baskets + the screener universe that reference-anchored scoring needs. Without it
> the screener is empty and scoring falls back to relative.

## 3. Python engine

```bash
cd /root/DYOR
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .            # installs deps from pyproject (fastapi, uvicorn, duckdb, numpy…)
.venv/bin/uvicorn dyor.api.app:app --host 127.0.0.1 --port 8077  # smoke test, then Ctrl-C
```

(Works on open data keyless. If you later add Santiment/other keys, put them in `config.yaml`.)

## 4. Web UI

```bash
cd /root/DYOR/web
test -f .env.local && echo "DELETE .env.local — it overrides .env.production!" # must NOT exist on the server
npm ci
npm run build                      # bakes in NEXT_PUBLIC_API_URL from .env.production
```

`web/.env.production` already points the browser at `https://dyor.cryptoopsec.com`
(same origin). If you use a different host, edit it before building.

## 5. Run the services under pm2

```bash
cd /root/DYOR
pm2 start deploy/ecosystem.config.cjs
pm2 save                           # persist across reboots (pm2 startup once, if not set up)
pm2 status                         # dyor-api + dyor-web + dyor-mcp online
```

## 6. nginx + TLS

```bash
cp /root/DYOR/deploy/nginx-dyor.conf /etc/nginx/sites-available/dyor.cryptoopsec.com
ln -s /etc/nginx/sites-available/dyor.cryptoopsec.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d dyor.cryptoopsec.com     # adds 443 + http→https redirect
```

## 7. Verify

```bash
curl -s https://dyor.cryptoopsec.com/api/health        # {"status":"ok",...}
curl -sI https://dyor.cryptoopsec.com/                 # 200, Next.js UI
# Hosted MCP — an initialize handshake should return 200 + an event-stream:
curl -s -i -X POST https://dyor.cryptoopsec.com/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | head -12                                            # serverInfo "dyor", mcp-session-id header
```

Open `https://dyor.cryptoopsec.com`, run an analysis, check the price chart and screener.
Agents connect with: `claude mcp add --transport http dyor https://dyor.cryptoopsec.com/mcp`.

## 8. The main site

`client/src/components/tools-section.tsx` already links **Launch DYOR →**
`https://dyor.cryptoopsec.com` (override with `VITE_DYOR_URL` at build time). Deploy the
site the usual way:

```bash
cd /root/OpsecSite && ./deploy.sh
```

---

## Updating DYOR later

```bash
# re-sync code (step 2), then on the VPS:
cd /root/DYOR && .venv/bin/pip install .          # if Python deps changed
cd /root/DYOR/web && npm ci && npm run build       # if web changed
pm2 restart dyor-api dyor-web
```

Refresh the scoring universe periodically (rebuilds reference baskets + a screen):

```bash
cd /root/DYOR && .venv/bin/dyor reference          # rebuild per-class baskets
# (or trigger a screener build from the UI / POST /api/screener/build)
```

## Notes & gotchas

- **`.env.local` precedence** — Next loads `.env.local` over `.env.production` in prod
  builds. Never ship `web/.env.local` (localhost) to the server, or the UI will call
  `localhost:8077` and fail.
- **DuckDB is single-writer** — keep one `dyor-api` process (no pm2 cluster mode). The
  live "self-heal" upsert and screener builds both write to `data/dyor.duckdb`.
- **CORS** — same-origin, so none needed. The API currently allows all origins
  (`allow_origins=["*"]`); optional hardening: restrict to the subdomain in
  `dyor/api/app.py`.
- **First call latency** — analyzing a new token collects live data; nginx
  `proxy_read_timeout` is set to 120s for that.
- **Hosted MCP** — `dyor-mcp` runs as a pm2 service (streamable-http, `127.0.0.1:8765`),
  exposed at `/mcp` (the nginx `location /mcp` uses `proxy_buffering off` + a long
  `proxy_read_timeout` for the event stream). It's a read-only research surface with no
  auth; if you want to limit abuse, add an nginx `limit_req` zone for `/mcp` (and `/api/`),
  or put a bearer token in front. The same binary still works locally over stdio (`dyor-mcp`).

## Scheduled refresh (cron)

`dyor refresh` is the unit of scheduled work: snapshot the previous run →
collect live → persist → alert on changes. Installed on the VPS as:

```bash
scp deploy/dyor-refresh.sh <VPS>:/usr/local/bin/dyor-refresh
ssh <VPS> 'chmod +x /usr/local/bin/dyor-refresh && touch /var/log/dyor-refresh.log'
scp deploy/dyor-refresh.cron <VPS>:/tmp/ && ssh <VPS> 'crontab /tmp/dyor-refresh.cron'
```

**Weekly, Sunday 03:07 UTC — deliberately not daily.** Santiment's free
anonymous tier is ~1000 calls/month and each token costs 2, so a 60-token
refresh is 120 calls: weekly is ~520/month and leaves headroom for the site's
on-demand analyses. Daily would be ~3600/month, and an exhausted quota silently
drops `address_growth`/`dev_commit_trend` — coverage falls and scores move. A
Santiment key in `/root/DYOR/.env` makes daily affordable.

`refresh` also **unions in every class reference basket** (~56 tokens on top of
the TVL slice), so the screener keeps bitcoin, ethereum, the memecoins and the
stablecoins regardless of weekly TVL churn — ranking on TVL alone dropped
ethereum, chainlink and celestia in one run and left a DeFi-only board. Pass
`--no-baskets` to opt out; `dyor collect` takes `--include-baskets` to opt in.
Effective universe at `TOP_N=60` is ~116 tokens.

Santiment cost stays low because only ~35% of our gecko_ids are Santiment slugs
and the client **remembers the misses for 30 days**: ~232 calls on the first run,
~81/week after — roughly 350/month against the ~1000 free tier.

**`TOP_N` must not shrink the universe below the current run.** `refresh`
persists a *new* run and the screener reads only the latest, so a smaller top-N
shrinks the screener.

The wrapper takes `flock -n -E 75` so two collectors never overlap, and logs to
`/var/log/dyor-refresh.log` (monthly logrotate, 12 kept). Exit codes: `0` ok,
`75` skipped because a run was already going, `1` collect returned nothing
(nothing persisted), `143` terminated.

### Installing the Python package on the server

**Install editable — `pip install -e . --no-build-isolation --no-deps`.** A
plain `pip install .` leaves a *copy* in `site-packages`, and then the console
scripts (`dyor`, `dyor-mcp`) import that copy while uvicorn imports
`/root/DYOR/dyor` (it inserts cwd on `sys.path`). An rsync deploy then updates
the API but silently leaves the CLI and MCP server running old code. Editable
means one copy, and rsync alone is a complete code deploy.

## Deployment sweep

`deploy/deployment-sweep.sh` verifies a deploy end to end and prints a PASS/FAIL
table: source-of-truth (clean tree, HEAD == origin, tests), code parity
(server `dyor/` tree checksum == local, editable import, each shipped fix
present in the *imported* module), services (pm2 + listening ports), the HTTP
surface (every web page, API route, MCP handshake, TLS expiry, the main site's
Tools link in the served bundle), data (runs, basket rows/classes, latest run
size), scheduling (crontab, cron enabled, wrapper, logrotate, flock guard) and
a behavioural regression (screener stays up during a live collect; a same-class
persist does not move another token's score).

```bash
deploy/deployment-sweep.sh            # uses ssh host alias "cryptoopsec"
DYOR_SSH_HOST=myhost deploy/deployment-sweep.sh
```

**Run it when no refresh is in flight.** The collector and the API share one
outbound IP, and CoinGecko's keyless limit is per IP with separate token buckets
per process — so during a refresh, on-demand `analyze` backs off against 429s and
can exceed a 90s client timeout. This is also why the cron slot is 03:07 UTC.

## Rate limiting, admin token, lock, logs (added 2026-09-26)

**Per-IP rate limits at nginx.** The live-collection endpoints (`/api/analyze`,
`/api/memo`, `/api/portfolio`, `/api/screener/build`, `/mcp`) each trigger ~10
upstream calls against shared per-IP limits and a 1,000/month Santiment quota.
Zones live at http scope in `deploy/nginx-dyor-ratelimit.conf`; the live vhost
is certbot-managed so it is patched in place, idempotently:

```bash
scp deploy/nginx-dyor-ratelimit.conf deploy/apply-nginx-ratelimit.sh <VPS>:/tmp/
ssh <VPS> 'cp /tmp/nginx-dyor-ratelimit.conf /etc/nginx/conf.d/dyor-ratelimit.conf && bash /tmp/apply-nginx-ratelimit.sh'
```

`dyor_live` = 6 req/min (burst 3) on the collection endpoints, `dyor_api` = 60
req/min (burst 20) on everything else under `/api/`. Excess requests get 429.

**Screener rebuilds are admin-only.** `POST /api/screener/build` requires
`X-Admin-Token` equal to `DYOR_ADMIN_TOKEN` in `/root/DYOR/.env`; with no token
set the endpoint is disabled (403). The weekly cron is the normal path. A rebuild
unions the reference baskets in and goes through the shrink guard.

**One collect lock.** The cron wrapper and the API build job flock the same file,
`/root/DYOR/data/.collect.lock` (`DYOR_COLLECT_LOCK` overrides), so two
collectors can never run at once.

**Shrink guard.** `db.persist_run` refuses a run smaller than
`store.min_run_fraction` (50%) of the previous one unless forced — the reason a
`--top-n 30` rebuild or a bare `dyor refresh` can no longer blank the board.
`refresh` then prunes runs older than the newest `store.keep_runs` (156).

**Secrets on the server.** `/root/DYOR/.env` (mode 600) holds
`DYOR_CRYPTORANK_API_KEY` (the feed activates on a plan with vesting endpoints)
and, when set, `DYOR_ADMIN_TOKEN` / `DYOR_ALERT_WEBHOOK`. It is read from the
project dir regardless of CWD.

**Logs.** `pm2 install pm2-logrotate` (set to 20 MB / 14 files / compress) — uvicorn
writes INFO to the pm2 error stream, and unrotated they grow without bound. The
refresh log rotates via `deploy/logrotate-dyor-refresh.conf` →
`/etc/logrotate.d/dyor-refresh`; it needs `su root root` because `/var/log` is
group-writable on Ubuntu and logrotate silently skips such parents otherwise.

**Web changes need a rebuild.** An rsync alone leaves the old `.next` serving 200s;
`deploy/deployment-sweep.sh` now fails if the server's build is older than its
sources.

## Santiment budget, anchor reliability, one-off basket refill (added 2026-09-27)

**Santiment's anonymous budget is per IP per month (~1000 calls).** On
2026-09-27 the server hit it ("API Rate Limit Reached. Try again in 287179
seconds") after the Sunday refresh plus a `dyor reference` rebuild, two preview
collects and the live analyses. Consequences and guards:

- `SantimentClient` now recognises a 429 whose wait is an hour or more as the
  monthly budget and short-circuits every further call in the process to an
  immediate `SantimentBudgetExhausted` (feed shows `error`, `feed_outage` alert
  fires) instead of pacing 6 s per doomed request. Cached responses still serve.
- `db.refresh_in_latest_run` refuses to replace a stored row with one whose
  feeds errored where the stored row's did not, so live analyses during an
  outage cannot strip `address_growth` / `dev_activity` off the board.
- Budget arithmetic: the weekly refresh spends ~2 calls per Santiment-tracked
  token (~180/week); each live analysis 2 more unless the day's window is
  already cached. A registered free API key (`DYOR_SANTIMENT_API_KEY`) moves
  the budget off the shared IP; a longer window (90 d) costs nothing extra but
  could not be tested while exhausted — revisit after the reset.

**The scoring anchor must be read read-only.** `reference_peers` /
`_basket_version` opened read-write; DuckDB refuses that while any thread of
the same process holds a read-only connection ("different configuration than
existing connections"), the error was swallowed, and the request silently
scored *unanchored* — the same token 54.8 on one call and 58.5 on the next.
Now: read-only opens, brief retries, the last good anchor kept per process,
and `ReferenceUnavailable` → HTTP 503 (`Retry-After: 5`) rather than a number
on a different scale. Never write `except Exception: return {}` around it again.

**Rebuilding baskets while a source is unavailable poisons the anchor.** A
`dyor reference` re-collects every basket coin; a feed that errors for all of
them (Santiment over budget) yields distributions with no address-growth or
dev-activity values, and every token is then scored without those features —
Tether jumped 17 points from that alone (2026-09-27, a rebuild run right after
the Santiment window changed, which invalidated the same-day cache). Before a
rebuild: confirm the feeds are live, or that the window / cache keys match
what the cache holds (`ls -t .cache/santiment | head`), and afterwards check
`reference_distributions(cls)` has the on-chain and dev features for every
class. If not, rebuild again with the previous window forced in memory
(`cfg["ingestion"]["sources"]["santiment"]["window_days"] = 28;
build_references(cfg)`), as was done to recover.

**One-off basket refill.** The 2026-09-27 rebuild widened the monetary / meme /
stablecoin baskets while Santiment was exhausted, so the new coins' Santiment
features are empty until a rebuild after the monthly reset. A transient systemd
timer does it: `systemctl list-timers dyor-reference-refill.timer` (fires
2026-10-02 04:00 UTC, logs to `/var/log/dyor-refresh.log`, takes the collect
lock). If it has fired, it is gone; run `dyor reference` under `flock` by hand
for any later basket change.

## Coverage matrix

`deploy/coverage-matrix.py` prints, for the latest persisted run, how many
tokens of each class have each scored feature and *why* the rest don't (source
off / empty / error / no source / derived-null), plus the per-token coverage
distribution. Run it on the server after a refresh to see what a data-source
change bought: `ssh <VPS> '/root/DYOR/.venv/bin/python /root/DYOR/deploy/coverage-matrix.py'`.
