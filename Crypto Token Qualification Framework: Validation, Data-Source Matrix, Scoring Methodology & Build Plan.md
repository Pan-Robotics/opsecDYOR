# Crypto Token Qualification Framework: Validation, Data-Source Matrix, Scoring Methodology & Build Plan

## TL;DR
- **Most headline claims check out, but several are stale or imprecise.** Verified: spot BTC ETFs hold ~7% of supply (collectively 1.28–1.31M BTC per BTC.network, Apr 11 2026; Bitwise cites ~1.5M BTC ≈ 7.1% of the 21M max); CoinGecko's "11.6 million tokens failed" in 2025 of ~20.2M launched (53.2% dead); Hyperliquid's 97% fee-to-buyback and ~$1.3B annualized fees; Zcash SEC closure (Jan 15, 2026) and shielded pool grown from ~8% (2024) to ~30%; 10Y Treasury 4.46%. Corrected/nuanced: "$8B" tokenized Treasuries is now ~$13.5B (RWA.xyz, Apr 12 2026); "$400B stablecoin volume" conflates with ~$297B stablecoin **supply**; the "$97B 2025 unlocks" figure is real ($97.43B, Tokenomist) but single-sourced.
- **The data layer is buildable cheaply.** A free/low-cost core (DefiLlama + CoinGecko free + GitHub + Electric Capital open dataset + Santiment free GraphQL) covers fundamentals, supply, dev activity, and basic social; paid add-ons (Token Terminal, Glassnode Professional, Nansen, CoinGlass, CryptoRank) fill on-chain depth, pre-computed P/F & P/S, ETF flows, and unlock schedules.
- **Build it as a normalize-then-gate multi-factor scorer.** Resolve token identity on `chain:address` keyed to CoinGecko IDs / DefiLlama slugs (joined via `gecko_id`), normalize heterogeneous signals (percentile rank preferred), combine with explicit weights, and apply hard disqualifier gating so fatal flaws can't be averaged away. Use vcrpy/pytest-recording cassettes for TDD against external APIs.

---

## Key Findings

### PART 1 — Claim validation (verified vs stale vs fabricated)

| # | Claim | Verdict | Current corrected figure (date / source) |
|---|---|---|---|
| 1 | Spot BTC ETFs hold ~7% of supply | **VERIFIED** | Collectively 1.28–1.31M BTC (BTC.network, Apr 11 2026); Bitwise cites ~1.5M BTC ≈ 7.1% of 21M max supply; total net assets ~$96.5B (April 2026). |
| 2 | "$97B in token unlocks in 2025" | **VERIFIED (single-source)** | $97.43B total 2025 emissions (Tokenomist 2025 Review, Jan 2026). |
| 3 | "11.6M tokens failed", "over 50M cryptocurrencies" | **MIXED** | 11.6M failed in 2025 of ~20.2M launched since 2021 (CoinGecko, Jan 2026); 53.2% dead. The "50M" figure is NOT supported — CoinGecko tracks ~20.2M; CMC ~14.65M active. |
| 4 | Hyperliquid: 97% fees→buyback, ~43% of crypto fees in a week, ~$1.3B annualized | **MOSTLY VERIFIED** | 97% of trading fees to Assistance Fund (DefiLlama adapter says 99% net of builder/unit fees); ~$1.3B annualized fees mid-2026; Fund crossed $2B May 16, 2026. "43% in one week" NOT directly confirmed; closest verified is 46% of all 2025 buyback activity. |
| 5 | Zcash: SEC closed, 30% shielded, halving/inflation, ETF | **VERIFIED** | SEC closed investigation Jan 15, 2026; shielded pool grew from ~8% (2024) to ~30% (~4.5M ZEC); Nov 2024 halving cut inflation 4%→2%; Grayscale S-3 to convert to spot ETF (ticker ZCSH). |
| 6 | BTC exchange reserves 7-yr low; whales +270K BTC/30d | **VERIFIED (caveated)** | Reserves ~2.21–2.43M BTC (lowest since Dec 2017); whales (1,000+ BTC) accumulated ~270K BTC/30d (largest since 2013). Sourced to CryptoQuant/CoinGlass; some figures via secondary aggregators. |
| 7 | RWA: "$8B" tokenized Treasuries; "$400B" stablecoin volume | **STALE / CONFUSED** | Tokenized Treasuries ~$13.5B (Apr 12 2026, RWA.xyz); total non-stablecoin RWA ~$29–31.8B. Stablecoin SUPPLY ~$296.96B (June 15 2026) — NOT a payment "volume" figure. |
| 8 | 10Y Treasury ~4.5% | **VERIFIED** | 4.46% (June 18, 2026). |

### PART 2 — Data-source & API matrix (summary)

| Tool | Public API? | Free tier | Paid pricing | Auth | Key raw metrics exposed |
|---|---|---|---|---|---|
| **DefiLlama** | Yes | Yes (no key, no hard limit) | Pro $300/mo | none (free) / key (Pro) | TVL, fees, revenue, holders revenue, earnings, stablecoins, unlocks, RWA, raises, yields |
| **Token Terminal** | Yes (REST, 25+ endpoints, MCP) | Limited | Enterprise (contact sales) | API key | Pre-computed P/F, P/S, fees, revenue, earnings, active users, financial statements |
| **Messari** | Yes (v1/v2 REST) | Free 20 req/min | Enterprise (contact sales) | x-messari-api-key | Market data 40k+ assets, on-chain, unlocks, fundraising, mindshare/sentiment, research |
| **Nansen** | Yes (REST/CLI/MCP) | Free credits (10× cost) | Pay-per-call $0.01–$0.05; Pro ~$49–69/mo; VIP $1,899/mo | API key / x402 USDC | Smart Money flows, wallet labels, Token God Mode, holders, DEX trades |
| **Glassnode** | Yes (900+ endpoints) | Studio Standard free (Tier-1, daily) | Advanced ~$29; Professional ~$799–999/mo; API add-on only on Pro | api_key / X-Api-Key | Exchange reserves, whale cohorts, SOPR, MVRV, realized cap, HODL waves (tiered) |
| **CryptoQuant** | Yes (REST) | Limited | Paid tiers (Advisor/Professional) | API key | Exchange flows, netflow, whale ratio, MPI, NVT, fund/ETF data |
| **CoinGlass** | Yes (V4 REST + WS) | — | $29 / $79 / $299 / $699/mo + Enterprise | CG-API-KEY | ETF flows (unique), funding rates, OI, liquidations, long/short |
| **CoinGecko** | Yes (REST + WS) | Demo 30 calls/min, 10k/mo | Analyst $129/mo (500/min) → Pro/Enterprise; $250 per 500k calls | x-cg-pro-api-key | Prices, market cap, supply, 500+ categories, on-chain DEX, /coins/list ID map |
| **CoinMarketCap** | Yes | Free 50 calls/min | Tiered | API key | Prices, market cap, payload-based credit model (expensive batches) |
| **CryptoRank** | Yes (V2 REST + MCP) | Tiered | Credit-based plans | API key | Token unlocks/vesting, funding rounds, IDO/ICO, FDV, investor tiers |
| **Tokenomist (Token Unlocks)** | Limited | Dashboard free | — | — | Vesting/unlock schedules, emissions, insider vs non-insider |
| **Santiment** | Yes (GraphQL) | Free 1,000 calls/mo, 30-day history | from ~$49/mo | API key | Social volume, dev activity, on-chain, sentiment for 3,000+ assets |
| **LunarCrush** | Yes (REST v4 + MCP) | Free tier | Tiered | Bearer token | Galaxy Score, AltRank, social volume/dominance, sentiment |
| **SosoValue** | Yes (referenced for ETF flows) | — | — | API key | ETF flow data |
| **GitHub** | Yes | 60 req/hr unauth; 5,000/hr authed | free | token | Commits, contributors, repo stats |
| **Electric Capital** | Open dataset (no REST) | Yes (open-source) | free | none | crypto-ecosystems taxonomy (TOML→parquet→DuckDB); dev counts via developerreport.com |
| **Dune / Artemis / Footprint / The Graph / Covalent(GoldRush) / Allium / Flipside** | Yes (various) | Mostly freemium | Varies | API key | Custom SQL, multichain raw data, fundamentals (Artemis), streaming (Allium) |

### PART 3 — Scoring methodology
Standard crypto valuation formulas, tokenomics overhang metrics, on-chain thresholds, the 5-stage narrative lifecycle, and a normalize-then-gate composite scoring design — all detailed below.

### PART 4 — Architecture & TDD
ETL/ELT pattern with caching and rate-limit handling, token-identity resolution keyed on `chain:address`, recommended Python stack, and a cassette-based TDD plan.

---

## Details

### PART 1 — Detailed claim validation

**1. Spot Bitcoin ETF holdings.** BTC.network (Apr 11, 2026) states US spot Bitcoin ETFs "collectively hold between 1.28 and 1.31 million BTC"; Bitwise (via Investing.com) puts the collective figure at "approximately 1.5 million BTC, representing roughly 7.1% of Bitcoin's maximum 21 million supply." Total net assets reached ~$96.5B in April 2026. The top three issuers (BlackRock IBIT, Fidelity FBTC, Grayscale GBTC) controlled ~94% of AUM. **~7% is accurate.** Note BTC traded ~$72–78K in April 2026, ~25% below its January 2026 high (~$126K cycle high cited).

**2. Token unlocks 2025/2026.** Tokenomist's 2025 Token Unlocks Review (published Jan 2026) reports **$97.43B** in total token emissions for 2025 ("2025 was one of the largest emission years on record, with $97.43B in total tokens released across major sectors"). Breakdown: Q1 ~$31.3B and Q3 ~$33.0B were peaks; Q4 ~$14.1B was lowest. Insider unlocks $18.77B vs non-insider $78.66B. Largest TGE unlocks: WLFI $6.93B, PUMP $2.34B, XPL $2.32B. **Caveat:** essentially single-sourced; no independent aggregator published a competing annual total. No single-dollar 2026 projection exists — Tokenomist's qualitative view is that 2026 will be "shaped less by supply shocks and more by fundamentals."

**3. Number of tokens / dead tokens.** Per CoinGecko Research (Jan 2026, "Dead coins: How many cryptocurrencies have failed?"): "53.2% of all cryptocurrencies on GeckoTerminal have failed… In 2025 alone, 11.6 million tokens failed, representing… 86.3%" of all 2021–2025 failures; ~20.2M launched, 7.7M (34.9%) died in Q4 2025 after the Oct 10 liquidation cascade ($19B wiped in 24h). Total dead since 2021 ~13.4M. **The "over 50M cryptocurrencies" claim is unsupported** — CoinGecko tracks ~20.2M launches; CoinMarketCap tracked ~14.65M active tokens (up from 2.7M a year earlier), with Solana memecoins >60% of all tokens. Methodology: a token is "dead/failed" when it loses utility, liquidity and community — near-zero volume, no GitHub commits for 6+ months, or 99%+ price drop from ATH; also rug-pulls and voluntary deactivations.

**4. Hyperliquid (HYPE).** Per crypto.news (May 2026): "The Assistance Fund directs 97% of Hyperliquid's protocol fees into continuous, automated market purchases of HYPE… Hyperliquid's protocol revenue runs at roughly $1.3 billion in annualized fees as of mid-2026." DefiLlama's protocol adapter states **99% of perp/spot fees go to the Assistance Fund** (the "97%" is net of builder/unit fees). The Fund had spent >$1.3B buying back HYPE and crossed $2B in holdings (May 16, 2026). HYPE ranked #10 with ~$16.1B market cap (June 2026), hit an ATH ~$76.90 on June 16, 2026 (up from a ~$21–26 early-2026 trough; prior ATH $59.37 Sept 2025). Spot HYPE ETFs launched May 2026, drawing ~$172M net inflows. **The "captured 43% of all crypto market fees in one week" claim could not be directly verified**; the closest verified statistic is that Hyperliquid accounted for **46% of all crypto buyback activity in 2025**, with monthly buybacks averaging $65.5M. Buybacks are funded by real fees (not issuance), but analysts caution upcoming core-contributor unlocks pose supply risk — so "net deflationary vs unlocks" holds only while volumes/fees stay high.

**5. Zcash (ZEC).** Per crypto.news/CoinDesk (May 6, 2026): "The shielded pool grew from approximately 8% of total supply in 2024 to approximately 30% of total supply by mid-2026… approximately 4.5 million ZEC"; the SEC closed its "nearly two-year investigation into the Zcash Foundation on January 15, 2026, without enforcement action." November 2024 halving cut inflation from 4%→2% annually. Grayscale filed Form S-3 to convert its Zcash Trust into a spot ETF (intended ticker ZCSH) on NYSE Arca. 2026 price action: rallied to ATH ~$642 on May 9, 2026 (a 650–1,000% move from 2024 lows), making ZEC the largest privacy coin by market cap over Monero; cooled to ~$522 thereafter. FCMP++ upgrade targeted for 2026. Risk: EU MiCA privacy-coin restrictions by 2027.

**6. BTC on-chain accumulation.** Exchange reserves fell to **~2.21–2.43M BTC** in April 2026 — the lowest since December 2017 (a "7-year low," some sources say 9-year). Whales (1,000+ BTC) accumulated **~270K BTC in 30 days** (largest monthly since 2013); a record single-day 32,000 BTC exited exchanges March 7, 2026. Long-term holders control ~78.3% of supply. **Caveats from the sources themselves:** exchange-reserve data is noisy (internal wallet reshuffles can appear as flows); CoinGlass and Glassnode use different methodologies; several specific figures trace to secondary aggregators (Spoted Crypto) citing CryptoQuant/CoinGlass. Treat the direction as well-supported and the exact daily figures as approximate.

**7. RWA.** **Tokenized US Treasuries are now ~$13.5B** — per RWA.xyz via Bitcoin.com (Apr 12, 2026), "tokenized Treasuries hit $13.53B on Apr. 12" (top funds: Circle USYC $2.67B, BlackRock BUIDL $2.42B); total RWA market ~$29.22B. The "$8B" figure was accurate around late 2025/early 2026 (Motley Fool cited $8.7B Jan 2026) but is now **stale**. Total non-stablecoin tokenized RWA reached ~$31.8B mid-June 2026 (up ~300% YoY); six asset classes each exceed $1B. **Stablecoins: the "$400B" is a metric confusion** — total stablecoin SUPPLY is ~$296.96B (June 15, 2026 per RWA.xyz), not a payment "volume" figure. There is a meaningful distinction in RWA.xyz data between "distributed" (transferable, ~$26.7B) and "represented" (~$345B) value.

**8. 10Y Treasury yield.** **4.46% (June 18, 2026)** per TradingEconomics, CNBC, Advisor Perspectives; MacroMicro shows 4.45%. The ~4.5% "risk-free hurdle" is accurate. Context: the Fed (under new Chair Kevin Warsh) held rates and signaled possible hikes amid Middle East-driven inflation.

### PART 2 — Per-tool deep dive (raw vs derived)

**DefiLlama (foundation of the build; free).** Public API at `api.llama.fi` / `coins.llama.fi` / `stablecoins.llama.fi` / `yields.llama.fi`. Free tier needs no key and has no hard rate limit for normal traffic; Pro is $300/mo for higher limits and extra endpoints. Key endpoints: `/protocols`, `/protocol/{slug}`, `/tvl/{slug}`, `/v2/historicalChainTvl`, fees/revenue dashboard endpoints, `/stablecoins`, unlocks, RWA. **Data-model nuance critical to the scorer:** DefiLlama distinguishes **Fees** (total paid by users), **Revenue** (subset the protocol keeps — treasury/team/holders), **Holders Revenue** (subset distributed to token holders via buyback/burn/staking), and **Earnings** (net revenue after subtracting token incentives). TVL updates hourly; per-protocol accuracy depends on open-source adapters (well-vetted for Aave/Uniswap/Lido). Each protocol object carries `gecko_id` and `cmcId` — the join keys for cross-source identity.

**Token Terminal (best pre-computed fundamentals; paid).** REST API with 25+ endpoints plus MCP; works with Python/Jupyter. Pre-computes **P/F (circulating & fully diluted) = market cap / annualized fees** and **P/S = market cap / annualized revenue**, plus fees, revenue, earnings, expenses, cost of revenue, active users, and income statements across 100+ chains, 1,200+ apps, 3,000+ tokenized assets. Pricing is enterprise/contact-sales (no transparent self-serve tier). Weakness: EVM/top-protocol bias, less early-stage/non-EVM coverage.

**Messari (research + unlocks + market data).** REST v1/v2; `https://api.messari.io/api/v1/assets/{asset}/metrics`. Free tier 20 req/min; auth via `x-messari-api-key`; enterprise for custom limits and full feeds (research, unlocks, fundraising, mindshare/sentiment, screeners). 40,000+ assets, 200+ DeFi protocols, news from 500+ sources.

**Nansen (smart money / wallet labels).** Moved to a **pay-per-call x402 model** in 2026: Basic $0.01/call (token screener, balances, txns, DEX trades, PnL), Advanced $0.05/call (Smart Money net flows, holdings, inflows). Subscription Pro ~$49–69/mo; VIP $1,899/mo (granular Smart Money, API access). Free tier consumes 10× credits. 300M+ labeled addresses, 18–25+ chains. Endpoints grouped into Smart Money, Profiler, Token God Mode, Portfolio.

**Glassnode (on-chain depth; gated).** 900+ endpoints, 7,500+ metrics, 1,200+ assets. **Studio Standard is free (Tier-1 metrics, daily resolution); Advanced ~$29/mo (but many metrics only plot last ~30 days — a documented limitation); Professional ~$799–999/mo.** API access is a **Professional-only add-on**; calls consume data credits (1 credit BTC, 2 credits altcoins). Auth via `api_key` query param or `X-Api-Key` header. Exposes exchange balances, whale cohorts (addresses >1,000 BTC), SOPR, MVRV/MVRV-Z, realized cap, HODL waves, URPD — gated by tier. CLI and Excel add-in available.

**CryptoQuant (Glassnode alternative; on-chain flows).** REST at `api.cryptoquant.com/v1`. Namespaces: Exchange-Flows, Flow-Indicator (MPI, whale ratio), Market-Indicator (SSR), Network-Indicator (NVT), Miner-Flows, Fund-Data (ETF), Mempool. Note: flow endpoints don't support Point-in-Time accuracy (wallet clustering updates retroactively). Pricing is tiered (Advisor/Professional); API is a premium feature.

**CoinGlass (ETF flows / derivatives — a genuine data edge).** V4 REST + WebSocket at `open-api-v4.coinglass.com`; auth `CG-API-KEY`. **Pricing (2026): Hobbyist $29/mo (30 req/min, 80+ endpoints), Startup $79 (80/min), Standard $299 (300/min, commercial license), Professional $699 (1,200/min), Enterprise custom.** Unique `/api/bitcoin/etf/flow-history` and ETH/SOL/XRP ETF endpoints; plus funding rates, OI, liquidation heatmaps, long/short ratios, Hyperliquid whale positions.

**SosoValue.** Referenced as an ETF-flow data source (GBTC outflow figures sourced to SosoValue); has an API for ETF flow data. Treat as a CoinGlass alternative/complement for ETF flows.

**CoinGecko (identity hub + market data; generous free tier).** Public/Demo: 30 calls/min, 10,000/mo, no key for basic (public plan can be 5–15/min without registration). Paid: **Analyst $129/mo (500/min, 60+ endpoints), Lite/Pro/Pro+ higher; Enterprise custom; $250 per 500k calls; 1 call = 1 credit (flat, payload-independent — cheaper than CMC for batches).** Cached identical responses don't deduct credits. Critically exposes **`/coins/list?include_platform=true`** (the cross-chain ID→contract map), `/asset_platforms`, `/coins/{id}/contract/{address}`, `/search`, and **500+ categories** for narrative tracking. 18,000+ coins, 37M+ on-chain tokens, 250+ networks.

**CoinMarketCap.** Free 50 calls/min; **payload-based credit model** means large batch queries can cost up to 100× more credits than CoinGecko's flat model — a meaningful cost consideration for a screener polling many assets.

**CryptoRank (unlocks + funding rounds; good value).** V2 REST + MCP. Endpoints include `/v2/currencies/token-unlock` (upcoming unlocks), `/v2/funding-rounds`, `/v2/currencies/{id}/funding-rounds`, public-sales (IDO/ICO/IEO), full-metadata (FDV, next unlock, dominance — paid). Credit-based (1 credit/≤100 entries). 32,000+ assets, largest token-sale database, 10,000+ funds tracked. Strong for the tokenomics/allocation layer.

**Tokenomist (token.unlocks.app successor).** Source-verified vesting/unlock schedules for 500+ tokens, cliff vs linear labeling, insider vs non-insider. Primary dashboard is free; programmatic API availability is limited — for a build, prefer CryptoRank or DefiLlama unlocks endpoints for queryable data.

**GitHub API (dev activity).** Free; **60 req/hr unauthenticated vs 5,000 req/hr authenticated** (token). Commits, contributors, repo stats. Pair with Electric Capital's taxonomy to scope which repos belong to which ecosystem.

**Electric Capital (dev activity, open-source public good).** No commercial REST API; instead the **`electric-capital/crypto-ecosystems`** (now `open-dev-data`) taxonomy maps ecosystems→GitHub orgs/repos via TOML. Tooling: `uvx open-dev-data` downloads parquet files and loads into DuckDB for SQL. developerreport.com has a public dashboard. Definitions: Monthly Active Developer (≥1 commit/28d), Full-Time (10+ days/mo), Part-Time (2–9 days/mo). Workflow: use the taxonomy to enumerate repos, then hit the GitHub API for commit/contributor stats.

**Santiment (social + dev + on-chain; free GraphQL).** GraphQL-only at `api.santiment.net`; Python client `sanpy`. **Free tier: 1,000 calls/mo, 30-day history; paid from ~$49/mo.** 3,000+ assets. Social volume, dev activity, daily active addresses, sentiment, whale flows. Good free entry point for the social/dev layer.

**LunarCrush (social).** REST v4 at `lunarcrush.com/api4`; Bearer-token auth; MCP server. Free tier available, tiered paid. Exposes **Galaxy Score, AltRank, social mentions/interactions/contributors, social dominance, sentiment**. Note: exact Galaxy Score component weights have been proprietary since 2021.

**Aggregator/infra options.** **Dune Analytics API** (custom SQL over decoded chain data; freemium); **Artemis** (cross-chain fundamentals/KPIs); **Token Terminal** (above); **Messari** (above); **Footprint Analytics** (no-code + API analytics); **The Graph** (subgraph queries for protocol-specific on-chain data); **Covalent/GoldRush** (unified multichain balances/transfers REST); **Allium** (enterprise streaming/warehouse-grade, sub-minute); **Flipside** (free SQL + API). For a multi-source build, DefiLlama + CoinGecko + Dune/Flipside (free SQL) + Allium (if you need streaming) is a pragmatic ladder.

### PART 3 — Methodology & scoring

**1. Valuation formulas (as defined by Token Terminal / DefiLlama):**
- **P/F = Market Cap ÷ Annualized Fees** (Token Terminal publishes circulating and fully-diluted variants). Lower = cheaper per dollar of user-paid activity. Worked example: $1B mcap / $100M annualized fees = P/F of 10.
- **P/S = Market Cap ÷ Annualized Revenue** (revenue = fees retained by the protocol/holders). Fees ≥ Revenue always. Token Terminal: "Revenue measures the portion of fees that a project retains, as determined by its take rate."
- **MC/TVL = Market Cap ÷ TVL** (DefiLlama). Heuristic: <1 potentially undervalued, >5 potentially rich; compare within category; beware incentive-inflated/transient TVL.
- **FDV = Price × Total/Max Supply; Market Cap = Price × Circulating Supply; FDV/MCAP = total ÷ circulating supply.** High FDV/MCAP = large dilution overhang. DefiLlama also has "Outstanding FDV" = price × (total − unallocated treasury) for a more conservative measure.
- **Real yield** = holder yield funded by actual fees/revenue, not emissions. Operationalize with DefiLlama **Holders Revenue** and **Earnings** (revenue − incentives). Sustainable blue-chip yields ~3–15% APY; >50% on majors is usually emissions-driven.

**2. Tokenomics overhang metrics:**
- **Upcoming unlocks as % of circulating supply** (per event/30d/90d) and **as % of average daily volume** (absorption capacity — a $X unlock into thin volume is far riskier).
- **Float ratio** = circulating ÷ total supply (low float + high FDV = classic overhang).
- **Emission schedule / inflation rate** (annualized new supply), **vesting cliff risk** (large discrete unlocks), **insider vs non-insider share** of upcoming unlocks (Tokenomist labels these).

**3. On-chain health thresholds (practitioner):**
- **Active-address growth** (trend, not level); **holder concentration** via top-10/top-100 holder %, Nakamoto coefficient, Gini; **TVL momentum**; **transaction counts**; **exchange-reserve trend** (declining = accumulation). For Bitcoin-style cohorts: LTH supply %, whale-cohort accumulation, MVRV-Z (1.0–1.5 historically a value zone; >3.5 frothy), SOPR (reclaiming 1.0 = seller exhaustion).

**4. Narrative lifecycle (5-stage, practitioner/institutional framing):** **Emergence → Acceleration → Euphoria → Decline → Recycling** (FinanceFeeds, AInvest, JamesBachini; NYDIG's reflexive-narratives framework for BTC cycles). Narrative-relevant assets often retrace 70–90% from peaks. **Rotation signals:** (a) social volume vs price divergence (rising LunarCrush AltRank/Galaxy or Santiment social ahead of price = early); (b) sector TVL/fees flow (DefiLlama categories); (c) stablecoin supply flowing into a chain often precedes its token. CoinGecko's category endpoint + 500+ categories is the practical instrument for tracking which narrative is heating.

**5. Existing scoring systems to learn from:**
- **CoinGecko Trust Score** (exchanges, not tokens — don't misapply): 0–10 across Liquidity (4), Cybersecurity (2), Scale of Operations (1), Past Incidents (1), Proof of Reserves (1), API Coverage (0.5), Team Presence (0.5); explicitly "not a simple weighted sum"; recomputed weekly. Liquidity (most weighted) uses web-traffic-vs-reported-volume (ADUTV), spread, and per-pair trust.
- **LunarCrush Galaxy Score**: combines Price score, Average Sentiment, Social Engagement, and Correlation Rank into 0–100 (weights proprietary). **AltRank** = relative performance vs all assets (lower = better).
- **Nansen Smart-Money scores**, **Messari**, **Token Terminal** — fundamentals-led. Lesson: each is single-domain; your edge is combining domains.

**6. Composite scoring design:**
- **Normalize first** (the cardinal rule — otherwise the largest-magnitude factor dominates). Options: **percentile rank** (preferred — scale-invariant, outlier-robust, interpretable), z-score (`Z = (x−mean)/std`, control for scale but distorts multimodal data), min-max (`(x−min)/(max−min)`, good for bounded inputs; hold reference ranges fixed across runs for temporal comparability).
- **Combine with explicit weights**: `score = Σ wᵢ · normalizedᵢ`, weights summing to 1, grouped by domain (fundamental, tokenomics, on-chain, social, dev). Consider saturating transforms (`x/(x+α)`, α = median) to prevent single-factor runaway.
- **Gate, don't average, on disqualifiers**: hard red flags (unverified contract, anonymous team, no audit, extreme FDV/MCAP, dead-token criteria: no commits 6+ mo, 99%+ off ATH, near-zero volume) should cap or zero the score so a fatal flaw isn't offset by a strong factor elsewhere. Map final score to risk tiers by percentile thresholds.

### PART 4 — Architecture & TDD build plan

**Reference pipeline (ELT pattern):**
1. **Ingestion layer** — per-source async clients with rate-limit governors (token-bucket per API: GitHub 5,000/hr authed, CoinGecko 30/min free, CoinGlass per-tier), exponential backoff, and on-disk response caching (respect cache to avoid CoinGecko credit burn).
2. **Raw store** — land JSON/parquet (DuckDB is ideal for a single-founder build; Electric Capital's own tooling uses DuckDB).
3. **Normalization/entity-resolution layer** — resolve to canonical IDs (below).
4. **Metrics layer** — compute derived metrics (P/F, FDV/MCAP, unlock-%-of-volume, concentration) on top of raw fees/supply/holders.
5. **Scoring layer** — normalize → weight → gate.
6. **Presentation** — Streamlit or Dash for fast internal dashboards; FastAPI + Next.js if you want a productized UI. Scheduling via cron/APScheduler/Prefect/Dagster (Dagster/Prefect give retries + observability suited to flaky external APIs).

**Token-identity / entity resolution (the hard part):**
- Use **`chain:address` as the primary key** (lowercase addresses). CoinGecko's **`/coins/list?include_platform=true`** gives `id` → `{symbol, name, platforms{chain→contract}}`; **`/asset_platforms`** maps platform string-IDs (note: CoinGecko uses string IDs like `"polygon-pos"`, NOT numeric EVM chain IDs). DefiLlama uses `chain:address` natively and each protocol carries **`gecko_id`** and **`cmcId`** — the join keys across CoinGecko/CMC/DefiLlama. DefiLlama coins API uses `chain:address` directly (e.g., `ethereum:0xA0b8...`) and returns a confidence score (0–1) plus a `redirect` field for proxied prices. Build a crosswalk table keyed on CoinGecko `id` as canonical, joining DefiLlama slug via `gecko_id`. Match on contract+chain (tickers/symbols collide); watch per-chain decimal differences (USDC 6 vs 18 decimals across chains is a classic bug).

**Recommended Python stack:** `httpx` (async) for clients, `pandas`/`polars` for transforms, `duckdb` for storage/SQL, `pydantic` for response schema validation, `streamlit`/`dash` for UI, `prefect`/`dagster` for scheduling, `web3.py` for direct on-chain reads (holder distribution via Etherscan/Blockscout APIs or `eth_call`). Community wrappers exist for DefiLlama (`defillama-api`), Santiment (`sanpy`), Nansen (`nansen-cli`).

**TDD for data-integration:**
- **Cassette pattern**: `vcrpy` + `pytest-recording` (`@pytest.mark.vcr`, `--record-mode`). Record real API responses once to YAML cassettes; replay offline. Record modes: `once` (default), `new_episodes`, `none` (CI — fail on unseen requests), `all` (re-record). Filter/redact API keys via `vcr_config` `filter_headers` so secrets aren't committed.
- **Fine-grained mocking**: `responses`/`requests-mock` (for `requests`), `respx`/`pytest-httpx` (for `httpx`) — test error paths (429 rate limits, 404, malformed JSON). `pytest-httpserver`+`trustme` for client-library-agnostic local server tests; `aioresponses` for `aiohttp`.
- **Contract tests**: `schemathesis` (property-based against OpenAPI specs), `pact-python` (consumer-driven contracts), `jsonschema` for response validation — important because DefiLlama/CoinGecko schemas evolve.
- **Structure**: unit tests on pure metric functions (P/F, normalization, gating) with fixture data; integration tests on each API client via cassettes (replay-only in CI); contract tests on critical third-party schemas; a golden-dataset regression test for the end-to-end score.

---

## Recommendations

**Stage 1 — Free core MVP (validate the thesis cheaply):**
- Stand up DefiLlama (fees/revenue/TVL/unlocks/RWA) + CoinGecko free (prices/supply/categories/ID map) + GitHub (authed) + Electric Capital DuckDB + Santiment free GraphQL.
- Implement identity resolution on `chain:address`, compute P/F, P/S, MC/TVL, FDV/MCAP, unlock-%-of-volume, holder concentration, dev-activity trend.
- Ship a Streamlit dashboard and a first composite score (percentile-normalized, weighted, with hard disqualifier gating).
- **Benchmark to advance:** if the free data reproduces known good/bad calls (e.g., correctly flags high-FDV/low-float unlock overhangs and dead tokens), proceed.

**Stage 2 — Targeted paid add-ons (buy only what free can't derive):**
- **Token Terminal** if you want vendor-computed, standardized P/F & P/S rather than rolling your own from DefiLlama fees.
- **CoinGlass Standard ($299/mo)** for ETF flows + derivatives (the genuine data edge; commercial license included).
- **CryptoRank** for richer unlock/vesting/funding-round coverage; **Glassnode Professional** only if deep BTC/ETH on-chain cohorts become central; **Nansen pay-per-call** for smart-money confirmation signals.
- **Threshold to add a paid source:** only when a metric materially changes a score AND cannot be derived from free sources.

**Stage 3 — Hardening & scale:**
- Add Prefect/Dagster scheduling, contract tests on every external schema, and an alerting layer (narrative-rotation and unlock-cliff alerts).
- Consider Allium/Flipside/Dune if you need custom on-chain SQL or streaming.

**Cross-cutting:**
- Treat secondary aggregators (e.g., Spoted Crypto) as leads, not primary sources — wire the scorer to CryptoQuant/CoinGlass/Glassnode/RWA.xyz directly.
- Refresh stale constants (Treasury hurdle rate, RWA totals, supply figures) on a schedule — several claims here went stale within months.

## Caveats
- **Single-sourced figures:** the $97.43B 2025 unlock total (Tokenomist) and several BTC on-chain specifics (270K BTC/30d, 32K single-day) lack independent corroboration; the "43% of crypto fees in one week" HYPE claim could not be verified (closest verified: 46% of 2025 buybacks).
- **Metric confusion in source claims:** "$400B stablecoin volume" conflates with ~$297B stablecoin supply; "$8B tokenized Treasuries" is stale (now ~$13.5B); RWA "represented" (~$345B) vs "distributed" (~$26.7B) values differ ~13×.
- **Methodology limits:** CoinGecko Trust Score is for exchanges, not tokens; LunarCrush Galaxy Score weights are proprietary; narrative-lifecycle frameworks are practitioner/institutional, not peer-reviewed standards.
- **Forward-looking content flagged:** price targets (e.g., Arthur Hayes' $150 HYPE by Aug 2026, Standard Chartered's $100K BTC) are predictions, not facts and should not enter the scorer as data.
- **Data-quality reminders:** exchange-reserve data is noisy (wallet reshuffles); DefiLlama adapter accuracy varies for small protocols; Glassnode Advanced tier only plots ~30 days for many metrics; CMC's payload-based credits make batch polling expensive; CryptoQuant flow endpoints lack point-in-time accuracy.