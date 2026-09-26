# Data-Source Coverage Audit — 2026-09-26

**Question:** are all supplier schemas parsed correctly, is anything silently
dropped, and does every token get as many data sources as free data allows, so
scoring is fair and comparable?

**Method.** Live schema probes against every supplier (cache bypassed), compared
with the fields each parser reads; then a per-token, per-feature "why is this
None?" matrix over a full production run, attributing each gap to its cause
(source off / empty / error / no source exists / derived-null). Baseline is the
Sep 20 cron run; the "after" run is the same universe collected with the new code.

---

## 1. What the schema probes found

| Supplier | Finding | Action |
|---|---|---|
| CoinGecko `/coins/{id}` | `developer_data` and `community_data` come back **`null` on the free tier** even when requested — no free dev/community signal there. But `market_data.total_value_locked` (e.g. GMX $244M, dYdX $111M, Jito $1.27B — all tokens DefiLlama has no protocol for), `watchlist_portfolio_users` (present for every token probed, 29k–2M) and `links.repos_url.github` are free. | `coin_meta` requests `market_data`; TVL fallback, new `watchlist_users` feature, repo URLs for GitHub-org discovery. dev/community not requested. |
| CoinGecko `/coins/markets` | All fields the parser needs are present; `max_supply` is read as the FDV fallback. | none |
| DefiLlama `/summary/fees/{slug}` | Returns `github` (list of orgs) alongside totals; `holdersRevenue` often has only `total1y` (handled: longest window preferred, same-window pairing). Protocols without a series return 400 → correctly `None`. | `github` → `github_org` when unset |
| DefiLlama `/protocols` | Carries `audits` (count as string) and `audit_links`. Top-80: `"2"`×49, `"0"`×26, `"3"`×3, `"1"`×1, `null`×1. Of the 26 zeros none is a major; one contradicts its own `audit_links`. | `audited` = True on count>0 or any link, **False only on an explicit "0"**, None when absent. The `no_audit` gate (cap 0.5) is now live on open data. |
| DefiLlama `/v2/chains` + `/overview/fees/{chain}` | 315 chains carry a `gecko_id` and TVL; the fees endpoint accepts the chain **name verbatim** (`Ethereum`, `Binance`, `TON`, `ICP` …) and returns the same `total24h/7d/30d/1y` shape as protocols. | L1 tokens without a protocol slug get chain-wide fees, revenue and TVL. |
| Santiment `allProjects` | 2,588 projects; **1,595 with `mainContractAddress`**, plus `name`, `ticker`, `infrastructure`. Measured on the live 116-token universe: slug==gecko_id 62 + overrides 6 → **+19 by contract, +5 by exact name, +2 by unique ticker = 94 (81%)**; the 22 left are genuinely untracked. | `resolve_slug_map` (one cached call per run). |
| Sourcify `/v2/contract/{chainId}/{addr}` | Verified matches returned for Arbitrum (42161) and Base (8453), not just Ethereum. | Verify the first deployment on Ethereum → Arbitrum → Base → OP → Polygon → BSC → Avalanche. |
| Ethplorer `getTokenInfo` | Extra fields (`holdersCount`, `transfersCount`) exist; Ethereum-only remains the hard limit. | not used yet (noted) |
| CryptoRank v3 (Sandbox key) | Map + profile available; every vesting endpoint is **Pro-only** (`ENDPOINT_NOT_AVAILABLE`). | Feed `off` until the plan changes; nothing fabricated. |
| GitHub | Anonymous is 60 requests/**hour** — with orgs now discoverable for most tokens, an unauthenticated feed would add a minute of sleep per token. | Feed gated on `DYOR_GITHUB_TOKEN` (free); the collector prints a note when off. |

**Schema defects in our own specs.** `inflation_rate` (defi/l1/monetary) and
`reserve_trend` (monetary) were listed in the class specs with **no source at
all** — 106 permanently empty slots in a 117-token run, deflating every token's
coverage figure and confidence. Removed from the specs (kept in
`FEATURE_DIRECTION` for when a source exists).

**Consistency.** One routine (`universe.make_target`) now attaches feeds for the
TVL universe, the reference baskets and on-demand analyze alike, so the anchor
distribution and the live record are measured on the same feature set — the
audit found the baskets were being built with fewer feeds than live tokens.

---

## 2. Baseline — Sep 20 run, 117 tokens (before)

Overall feature-slot outcome: **present 42.9%** · derived-null 15.8% · empty
12.8% · error 11.6% (CryptoRank outage) · off 10.0% · no-source 6.9%.

Per-token class-relative coverage: median ~40–50%; only 3 tokens ≥ 70%.

Worst features by class (present / applicable):

| Class | Feature | Before | Cause |
|---|---|---|---|
| l1 | `mc_tvl` | 1 / 17 | no protocol slug → no TVL |
| l1 | `top10_concentration` | 5 / 17 | non-ERC-20 (hard limit) |
| l1 | `address_growth` | 5 / 17 | Santiment slug misses |
| defi | `real_yield` | 20 / 77 | no holders-revenue series |
| defi | `address_growth` / `dev_commit_trend` | 32 / 23 of 77 | Santiment slug misses |
| defi | `social_sentiment` | 43 / 77 | CoinGecko returns null votes |
| stablecoin | `social_sentiment` | 1 / 9 | no votes |
| all | `unlock_overhang` | 0 | CryptoRank |
| all | `inflation_rate`, `reserve_trend` | 0 | **no source exists** |

---

## 3. After — same universe, new code

_(filled from the post-deploy run — see below)_

---

## 4. What remains out of reach on free data

- Holder concentration off Ethereum (Ethplorer is mainnet-only; Solscan/BscScan need keys).
- Unlock overhang / next-unlock value (CryptoRank Pro, or DefiLlama Pro).
- Social volume trend (Santiment key).
- Exchange reserves, inflation rate (Glassnode / CryptoQuant / a supply-history source).
- `days_since_last_commit` for ~all tokens is one free GitHub token away.
