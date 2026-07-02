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
