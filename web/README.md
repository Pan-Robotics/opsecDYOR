# DYOR Web — Next.js frontend

A productized front end for the DYOR scorer, talking to the FastAPI backend.

## Run (two terminals)

**1. API** (from the repo root, with the Python venv active):

```bash
uvicorn dyor.api.app:app --port 8077
```

**2. Frontend** (from `web/`):

```bash
npm install        # first time
npm run dev        # http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_URL` (see [.env.local](.env.local)); point it
at the API host. CORS on the API is open for local dev.

## Pages

| Route | What |
|---|---|
| `/` | Home — hero, how-it-works, asset classes |
| `/analyze` | Search any token → full report: class, score, **tier + confidence + tier-stability**, market snapshot, domain bars, metrics, cross-chain explorers, peers, and an on-demand **🧠 analyst memo**. Peer modes incl. **"Same asset class" (default, fairest)**. |
| `/screener` | Tier-tabbed universe (A/B/C/D), background **build top-N**, and a **filter bar** (class / min-tier / min real-yield / no-flags) |
| `/tools` | **Portfolio scorer**, **Barbell builder**, **tier backtest** |
| `/narratives` | Sector rotation from CoinGecko categories |
| `/methodology` | Weights, tiers, asset classes, gate, metric glossary |

API: `analyze`, `screener` (+ `screener/build`), `screen`, `memo`, `portfolio`,
`barbell`, `backtest`, `narratives`, `classes`, `methodology`.

## Stack

Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS. Client components
fetch the API at runtime via [lib/api.ts](lib/api.ts).

> Note: `npm audit` reports advisories in the Next.js 14 line; for a local tool
> that's acceptable. Bump Next before any public deployment.
