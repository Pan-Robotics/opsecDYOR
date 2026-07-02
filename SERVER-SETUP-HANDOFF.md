# DYOR → cryptoopsec.com — Server Setup Handoff

**Audience:** the local Claude Code instance that has **both** the project source at
`/home/alexdada555/Documents/Crypto Opsec/{DYOR,OpsecSite}` **and** root SSH to the
cryptoopsec.com VPS.
**Goal:** stand up **DYOR** as `https://dyor.cryptoopsec.com`, and make the main site's
**Tools** section launch it.

You have both sides, so you do the whole thing yourself: push the code up, deploy it, wire
the site. Conventions below: **LOCAL** = a command on this machine; **SERVER** = a command
over SSH on the VPS. Replace `<VPS>` with your ssh host/alias (e.g. `root@1.2.3.4`).

Heads-up on git topology (verified): **neither** local dir is a git repo. The canonical
OpsecSite repo (with `origin`) exists **only on the server** at `/root/OpsecSite` — so the
site change in Step 6 is committed/pushed **on the server**, not locally. DYOR isn't in git
anywhere, so it ships by rsync (Step 0).

---

## Topology you're building

```
                          nginx (already on this VPS)
 cryptoopsec.com ───────► 127.0.0.1:3000   OpsecSite (Express SPA, pm2 "OpsecSite")  [exists]
 dyor.cryptoopsec.com ──► 127.0.0.1:3010   DYOR web  (Next.js,    pm2 "dyor-web")    [new]
        ├ /api/*, /openapi.json ─► 127.0.0.1:8077  DYOR API (FastAPI, pm2 "dyor-api") [new]
        └ /mcp                  ─► 127.0.0.1:8765  DYOR MCP (FastMCP, pm2 "dyor-mcp") [new]
```

Same-origin by design: the DYOR UI calls `/api/*` on its own host, so there is **no CORS**.
The hosted MCP server lets AI agents connect at `https://dyor.cryptoopsec.com/mcp` with no
local install. All three processes come up from one `pm2 start` (Step 3) and one nginx
vhost (Step 4) — nothing extra to do for MCP.

---

## Pre-flight (verify, don't assume)

```bash
node -v            # ≥ 18
python3 --version  # ≥ 3.10
pm2 -v && nginx -v && certbot --version
pm2 list           # expect an "OpsecSite" process already online
dig +short dyor.cryptoopsec.com   # must resolve to THIS VPS's public IP
```

- If `dyor.cryptoopsec.com` does **not** resolve to this box → stop and tell the human to
  add an **A record** `dyor` → this VPS IP. certbot (Step 4) will fail without it.
- If `node/python3/pm2/nginx/certbot` is missing, install it before continuing.

---

## Step 0 — Push the DYOR code to the server  *(LOCAL → SERVER)*

DYOR lives at `/home/alexdada555/Documents/Crypto Opsec/DYOR`. rsync it to `/root/DYOR`
(**run on LOCAL**; the trailing slash on the source matters):

```bash
ssh <VPS> 'mkdir -p /root/DYOR'
rsync -avz --delete \
  --exclude node_modules --exclude .venv --exclude .next \
  --exclude __pycache__ --exclude '*.pyc' --exclude .pytest_cache --exclude .git \
  "/home/alexdada555/Documents/Crypto Opsec/DYOR/" <VPS>:/root/DYOR/
```
> `data/dyor.duckdb` is intentionally **kept** — it holds the reference baskets + the
> screener universe the scoring needs. Do not exclude it.

**Gate before proceeding** (SERVER) — confirm the payload landed:
```bash
ssh <VPS> 'ls /root/DYOR/{web,dyor,deploy,pyproject.toml} /root/DYOR/data/dyor.duckdb'
# expect: web/ dyor/ deploy/ pyproject.toml + the .duckdb file
```
From here, Steps 1–5 are **SERVER** commands (`ssh <VPS> '...'`, or open an interactive
session: `ssh <VPS>` then run them in `/root/DYOR`).

The repo already contains everything else you need: `web/.env.production`,
`deploy/ecosystem.config.cjs`, `deploy/nginx-dyor.conf`, and a longer `DEPLOY.md`.

---

## Step 1 — Python scoring engine (dyor-api)

```bash
cd /root/DYOR
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .          # deps from pyproject: fastapi, uvicorn, duckdb, numpy, pandas, mcp…

# smoke test (Ctrl-C after you see it serving):
.venv/bin/uvicorn dyor.api.app:app --host 127.0.0.1 --port 8077 &
sleep 4 && curl -s localhost:8077/api/health   # -> {"status":"ok","service":"dyor"}
kill %1
```
Works on open/keyless data sources. (If the human later wants Santiment etc., keys go in
`config.yaml`.)

---

## Step 2 — Web UI (dyor-web)

```bash
cd /root/DYOR/web
# CRITICAL: a stray .env.local would override .env.production and point the UI at localhost.
rm -f .env.local
cat .env.production              # sanity: NEXT_PUBLIC_API_URL=https://dyor.cryptoopsec.com
npm ci
npm run build                    # bakes NEXT_PUBLIC_API_URL into the bundle
```

---

## Step 3 — Run the services under pm2

```bash
cd /root/DYOR
pm2 start deploy/ecosystem.config.cjs   # dyor-api (8077) + dyor-web (3010) + dyor-mcp (8765)
pm2 save
pm2 status                              # all three => online
# quick local checks (before nginx):
curl -s localhost:8077/api/health
curl -sI localhost:3010 | head -1       # HTTP/1.1 200 OK
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/mcp   # 406 = MCP mounted (needs MCP headers)
```
> Keep a **single** `dyor-api` instance — DuckDB is single-writer (no pm2 cluster mode).

---

## Step 4 — nginx vhost + TLS

```bash
cp /root/DYOR/deploy/nginx-dyor.conf /etc/nginx/sites-available/dyor.cryptoopsec.com
ln -sf /etc/nginx/sites-available/dyor.cryptoopsec.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d dyor.cryptoopsec.com --redirect -n --agree-tos -m <admin-email>
nginx -t && systemctl reload nginx
```
(If you don't have the admin email, run `certbot --nginx -d dyor.cryptoopsec.com` interactively, or ask the human.)

---

## Step 5 — Verify DYOR end-to-end

```bash
curl -s https://dyor.cryptoopsec.com/api/health           # {"status":"ok",...}
curl -sI https://dyor.cryptoopsec.com/ | head -1          # HTTP/2 200
curl -s "https://dyor.cryptoopsec.com/api/analyze?q=bitcoin&peer_mode=class" \
  | head -c 200                                            # JSON with a score/tier
# Hosted MCP handshake — expect 200 + content-type text/event-stream + a "dyor" serverInfo:
curl -s -i -X POST https://dyor.cryptoopsec.com/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | head -12
```
Then load `https://dyor.cryptoopsec.com` in a browser: gold/Orbitron theme, working
Analyze + price chart + Screener, and a "← CryptoOpsec" link in the nav.

---

## Step 6 — Make the main site launch DYOR (OpsecSite)

The only site change is the **Tools** card: `client/src/components/tools-section.tsx`.
`/root/OpsecSite` is the git checkout that deploys via `./deploy.sh` (fetch `origin/main`,
**stash any uncommitted changes**, ff-only, rebuild, `pm2 restart OpsecSite`). So the change
must be **committed on the server** — an *uncommitted* edit would be stashed away and lost.

**6a. Copy the already-edited file up** (LOCAL already has the change):
```bash
scp "/home/alexdada555/Documents/Crypto Opsec/OpsecSite/client/src/components/tools-section.tsx" \
  <VPS>:/root/OpsecSite/client/src/components/tools-section.tsx
```

If the LOCAL file is somehow unavailable, write
`/root/OpsecSite/client/src/components/tools-section.tsx` with **exactly** this instead:

```tsx
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/animation/Reveal";

// DYOR app URL — override with VITE_DYOR_URL at build time if the subdomain changes.
const DYOR_URL = import.meta.env.VITE_DYOR_URL ?? "https://dyor.cryptoopsec.com";

const DYOR_FEATURES = [
  "Asset-class-aware scoring",
  "A–D conviction tiers",
  "Token screener",
  "Portfolio & barbell tools",
  "Agent-callable (MCP)",
];

export default function ToolsSection() {
  return (
    <Reveal>
      <section
        id="tools"
        className="relative py-20 flex flex-col justify-start items-center p-4 overflow-x-hidden min-h-[480px] m-0 bg-[url('https://mkt-site-asset.crypto.com/assets/home-page/bento-layout/win-btc-mobile-v2.webp')] bg-center bg-cover bg-no-repeat box-border"
      >
        <div className="absolute inset-0 bg-black/60" />
        <div className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
          <div className="text-center mb-12">
            <h2 className="font-orbitron text-3xl md:text-4xl font-bold mb-6 text-cyber-gold">
              CryptoOpsec Tools
            </h2>
            <p className="text-xl text-gray-300 max-w-3xl mx-auto">
              Self-custody-friendly security and research tools. The first is live now.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 max-w-4xl mx-auto">
            {/* DYOR — live */}
            <div className="rounded-2xl border border-cyber-gold/30 bg-cyber-slate/80 backdrop-blur-md p-6 flex flex-col">
              <div className="flex items-center gap-3 mb-3">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyber-gold text-cyber-dark text-xl">
                  🧭
                </span>
                <div>
                  <h3 className="font-orbitron text-xl font-bold text-white leading-tight">DYOR</h3>
                  <p className="text-xs text-gray-400">Do Your Own Research</p>
                </div>
                <span className="ml-auto text-xs font-semibold px-2 py-1 rounded-full bg-green-500/15 text-green-400 border border-green-500/30">
                  ● LIVE
                </span>
              </div>
              <p className="text-sm text-gray-300 mb-4">
                A crypto-token qualification engine — resolves any token cross-chain and scores it on
                fundamentals, tokenomics, on-chain, social, and dev activity, judged against its own
                asset class. Opinionated A–D tiers with hard disqualifier gates. Research aid, not advice.
              </p>
              <div className="flex flex-wrap gap-2 mb-5">
                {DYOR_FEATURES.map((f) => (
                  <span
                    key={f}
                    className="text-xs px-2 py-1 rounded-full bg-cyber-gray/60 text-cyber-steel border border-cyber-gold/10"
                  >
                    {f}
                  </span>
                ))}
              </div>
              <Button
                asChild
                className="mt-auto w-full bg-cyber-gold hover:bg-cyber-gold-dark text-cyber-dark font-semibold shadow-none"
              >
                <a href={DYOR_URL} target="_blank" rel="noopener noreferrer">
                  Launch DYOR →
                </a>
              </Button>
            </div>

            {/* Next tool — placeholder */}
            <div className="rounded-2xl border border-cyber-gold/10 bg-cyber-slate/40 backdrop-blur-md p-6 flex flex-col items-center justify-center text-center">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyber-gray/60 text-cyber-steel text-xl mb-3">
                🛡️
              </span>
              <h3 className="font-orbitron text-lg font-bold text-gray-300 mb-1">OpsecViz</h3>
              <p className="text-sm text-gray-500 mb-4">
                Multi-chain portfolio analytics &amp; reporting.
              </p>
              <span className="text-xs font-semibold px-3 py-1 rounded-full bg-cyber-gray/60 text-cyber-steel border border-cyber-gold/10">
                Coming soon
              </span>
            </div>
          </div>

          <p className="text-center text-sm text-gray-400 mt-8">
            More tools on the way — join our Telegram for early access.
          </p>
        </div>
      </section>
    </Reveal>
  );
}
```

**6b. Commit on the server, then deploy** (all SERVER):
```bash
cd /root/OpsecSite
git add client/src/components/tools-section.tsx
git commit -m "Tools: launch DYOR (dyor.cryptoopsec.com)"
./deploy.sh                   # safe: the change is COMMITTED, so it isn't stashed; builds + restarts
git push origin main          # push when you can, to keep origin in sync (deploy works either way)
```
> `./deploy.sh` does `git merge --ff-only origin/main`; a local commit that's ahead of origin
> is a no-op merge, so it deploys fine even before you push. Never `git push --force`. If the
> push is rejected because origin diverged, leave it and reconcile origin with the human — the
> site is already live from your local commit.

If the subdomain ever differs, set it without code changes:
`VITE_DYOR_URL=https://dyor.example.com npm run build` (then `pm2 restart OpsecSite`).

**Verify:** open `https://www.cryptoopsec.com`, scroll to **Tools** → a "DYOR ● LIVE" card with
a **Launch DYOR →** button that opens `https://dyor.cryptoopsec.com`.

---

## Updating DYOR later

```bash
# re-run the Step 0 rsync (LOCAL → SERVER), then on the SERVER:
cd /root/DYOR && .venv/bin/pip install .         # only if Python deps changed
cd /root/DYOR/web && rm -f .env.local && npm ci && npm run build
pm2 restart dyor-api dyor-web
# refresh the scoring universe occasionally:
cd /root/DYOR && .venv/bin/dyor reference         # rebuild per-class baskets
```

## Rollback

```bash
pm2 delete dyor-web dyor-api && pm2 save
rm -f /etc/nginx/sites-enabled/dyor.cryptoopsec.com
nginx -t && systemctl reload nginx
# OpsecSite: revert the commit and ./deploy.sh
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| UI loads but every call "Failed to fetch" | `dyor-api` down (`pm2 logs dyor-api`) or nginx `/api/` block missing. |
| UI calls `localhost:8077` in prod | a `web/.env.local` survived — delete it and `npm run build` again. |
| 502 from nginx | the upstream (3010 or 8077) isn't running — `pm2 status`, `pm2 logs`. |
| certbot fails | DNS A record for `dyor` not pointing here yet (`dig +short dyor.cryptoopsec.com`). |
| DuckDB "lock"/IO errors | more than one writer — ensure a single `dyor-api`, no cluster mode. |
| Screener empty / odd scores | `data/dyor.duckdb` wasn't synced — re-run Step 0 (keep the .duckdb) or `dyor reference`. |
| First analyze is slow | live collection on first call; nginx `proxy_read_timeout` is 120s by design. |
| DYOR Tools card missing on site | OpsecSite change not in `origin/main`, or it got stashed — see Step 6 caveat. |

Full reference: `/root/DYOR/DEPLOY.md`.
