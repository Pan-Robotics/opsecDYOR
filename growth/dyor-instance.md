# DYOR — Growth & Validation Instance

> Instance of `master-playbook.md`, filled for **DYOR**. Prompts are paste-ready
> (replace remaining `[BRACKETS]` / `>> FILL`). Worked top-to-bottom as we go.

**Product:** DYOR — an open, asset-class-aware crypto **token qualification** tool. Resolve any token (name / symbol / contract, cross-chain) → a 0–1 score, tier (A–D), gate flags, and a full report. Built on **free/open data** (DefiLlama, CoinGecko, CryptoRank v0, Ethplorer, Santiment, GitHub, Sourcify). CLI + FastAPI + Next.js web app.
**Archetype (Phase 0):** **Prosumer-creator**, with a **developer-tool / open-source distribution wedge**.
**Primary channels (Phase 0):** Crypto Twitter/X → Reddit (organic) → Open-source + HN → Farcaster → creator collabs → Telegram/Discord. **Avoid:** Meta/TikTok paid, LinkedIn paid, Google search ads.
**One-line positioning:** `>> FILL (draft) — "The open, no-paywall token scorer: judges Bitcoin like Bitcoin and a DeFi app like a DeFi app — transparent methodology, not a black box."`

> ⚠️ **Framing — we already built it.** The master template validates *before*
> building. DYOR exists and runs. So the validation surface is the **real product**
> (a public "Analyze any token" page), and the questions shift to: **distribution →
> retention → (if monetizing) willingness to pay.** Big advantage: no fake landing
> page; the token report is the magic moment and the shareable artifact.

> 🧭 **Honesty / regulatory.** Position as a **research aid — "not financial
> advice."** Never present a tier as a buy/sell call or guarantee. Free waitlist for
> Pro/alerts is honest; never take payment or promise features that don't exist.

---

## Phase 0 — Positioning & Channel Selection ✅ DONE

**Archetype:** Prosumer-creator (open-source dev-tool wedge). The end user is a
*fundamentals-first retail crypto investor* (not consumer-viral, not B2B), but the
cheapest, most credible distribution is the open/transparent angle vs. paywalled
black-box incumbents.

**ICP:**
- **Primary — "the fundamentals-pilled holder":** crypto-native, concentrated
  portfolio, follows Coin Bureau-style research, distrusts hype, already on
  DefiLlama + CoinGecko. Pain: *"14 tabs open to decide if a token is real — I want
  one honest read."* Lives on CT, Reddit, Telegram.
- **Secondary:** indie analysts / newsletter & YouTube creators / small fund &
  DAO-treasury researchers who'll **cite** it (citation = distribution).
- **Anti-ICP:** memecoin degens (don't want fundamentals) and large institutions
  (buy Nansen/Messari). Don't build for them.

**Channel mix (ranked):** ① Crypto Twitter/X (founder-led, score-card threads) ②
Reddit organic (r/CryptoCurrency, r/defi, r/ethfinance, r/CryptoTechnology) ③
Open-source + HN ("Show HN: open asset-class-aware token scorer") ④ Farcaster
(score-any-token frame) ⑤ creator collabs ⑥ TG/Discord alpha groups.
**Do-not-use:** Meta/TikTok paid · LinkedIn paid · Google search ads.

**Cheapest valid demand test:** Deploy the **public Analyze page (no signup to
use)**; seed ~8–10 organic score-card posts on trending/controversial tokens across
CT + Reddit. **Pass = ALL of:** ≥1,000 unique analyses in 2 weeks · ≥25% 7-day
return · ≥20 unsolicited organic shares · Pro/alerts waitlist ≥3% conversion.

**Riskiest assumption (kill-risk):** *Will serious researchers trust & act on an
opinionated tier/score, or dismiss it as "another black-box screener" and go back to
free raw DefiLlama/CoinGecko data they read themselves?* Mitigation bet =
**transparency/open methodology.** The test attacks it directly: do people engage
with the **call** (argue/screenshot/share the tier) or just use it as a data viewer?
Second risk: **willingness to pay** (crypto retail expects free → business may be
API/pro-alerts/B2B, not consumer subs).

**`>> FILL` (locked):** archetype ✓ · ICP ✓ · channel mix ✓ · kill-metric ✓

---

## Phase 1 — Find a Better Opportunity  ⬜ TODO

**Goal:** Find DYOR's defensible "blue ocean" wedge in a crowded screener market.

```
PROMPT 1 — OPPORTUNITY (DYOR)

I'm building DYOR, an open, asset-class-aware crypto token scorer (free data, a
0–1 score + A–D tier + gate flags, single-token analyze with cross-chain
resolution, CLI/API/web).

Research the crypto token-research / screener landscape — at least: Token Terminal,
Messari, Nansen, Artemis, Kaito, DefiLlama, CoinGecko, Glassnode, plus newer
"AI token research" tools. For each: positioning, pricing, ICP, primary channel,
and the ONE thing they're weak at.

Then propose five "blue ocean" angles for DYOR that stand out, biased toward angles
that distribute on Crypto Twitter / Reddit / open-source-HN. For each angle, name
the wedge ICP it wins first and why.
```
**Choose one angle → Phase 2.**  `>> FILL: competitor map · 5 angles · chosen angle`

---

## Phase 2 — Product Spec  🟨 MOSTLY EXISTS

The spec is effectively the framework doc + the built product. **Don't rewrite from
scratch** — distill a *positioning/messaging* spec from what exists.

```
PROMPT 2 — POSITIONING SPEC (DYOR)

Using the existing DYOR framework doc + the built product, write a concise
positioning spec (not the engineering spec — that's done):
1. One-liner, 3 value props, the before/after for the "fundamentals-pilled holder".
2. The 2–3 "magic moment" features most likely to drive shares on CT/Reddit
   (candidate: instant cross-chain Analyze → tier + flags; the asset-class call;
   the gate catching a dead/over-diluted token).
3. The shareable artifact format (the "score-card" image/embed for a token).
Save to "growth/Documentation/Positioning Spec.md".
```
`>> FILL: one-liner · magic-moment feature to lead with · score-card format`

---

## Phase 3 — Visual Assets  ⬜ TODO

DYOR is **product-trust** territory (like B2B): **real screen recordings + a
shareable score-card** out-convert glossy art. Skip AI hero shots.

```
PROMPT 3 — DYOR VISUALS

Produce a visual asset plan:
1. 6–8 real screenshots to capture (which screen, what it proves) — e.g. Analyze a
   well-known token (tier + flags), the tier-tabbed Screener, the asset-class badge,
   cross-chain resolution, the gate firing on a bad token.
2. A 30–60s screen-recording script: type a trending token → instant report →
   the payoff (the flag/tier nobody expected). What's on screen, what I say.
3. A "score-card" share image spec (token, tier, top flags, score) for CT/Farcaster.
Save to "growth/Reference Images/asset-plan.md".
```

---

## Phase 4 — Validation Surface  🟨 PRODUCT EXISTS

We don't fake a landing page — we **expose the real Analyze tool** + a Pro/alerts
waitlist.

```
PROMPT 4 — PUBLIC VALIDATION SURFACE (DYOR)

Turn the existing Next.js app into a public validation surface:
1. A clean public landing (hero = "score any token") that drops straight into
   Analyze; no signup required to run an analysis.
2. A shareable per-token result (URL like /t/<token>) that renders a score-card
   (OpenGraph image) so a shared link previews the tier + flags — built-in virality.
3. A "Pro / alerts" waitlist (email + the one feature they most want) — honest,
   no payment.
4. Usage analytics on every analysis (token, source, returning vs new) behind a
   password dashboard.
Keep it deployable to Vercel (frontend) + a hosted API. Don't deploy yet.
Honesty rule: research aid, "not financial advice"; waitlist only — no payments.
```
`>> FILL: public URL scheme · score-card OG image · waitlist + analytics`

---

## Phase 5 — Conversion / Usage Tracking  ⬜ TODO

```
PROMPT 5 — TRACKING (DYOR)

Instrument the public app so we can measure the Phase-0 kill-metric:
- Event on each completed analysis (the core action).
- Returning-user tracking (7-day return).
- Waitlist signup event.
- Share event (score-card copied / link shared).
Wire a lightweight, privacy-respecting analytics (self-host or Plausible-style) +
the dashboard. Verify events fire on real actions only.
```
**Success:** analyses, returns, shares, waitlist all visible in the dashboard.

---

## Phase 6 — Channel Modules (curated for DYOR)

> Run **only** these. The master's Meta module = **SKIP** (wrong audience + crypto
> ad policy). LinkedIn/Google paid = **SKIP**. DYOR's #1 channel (Crypto Twitter)
> isn't in the master — it's **Module E** below.

### Module E — Crypto Twitter / X  ⭐ PRIMARY
```
PROMPT 6E — CT/X ENGINE (DYOR)

Act as a crypto founder-content strategist. Draft a 2-week X plan (10 posts) for
me (the builder) to validate DYOR and build an audience of fundamentals-first
crypto investors. Mix:
- "I scored $TOKEN" score-card thread on a trending/controversial token (the flag
  nobody expected = the hook).
- Build-in-public: a real artifact (the asset-class scoring, the gate catching a
  dead token), with the why.
- Contrarian POV that filters for the ICP (e.g. "most 'fundamentals' dashboards are
  just raw data — a number with no judgment isn't research").
- Open-source flex: transparent methodology vs. black-box paid screeners.
- One soft CTA (try it / waitlist) per few value posts.
For each: hook (first line = scroll-stopper), body, 1 CTA. Operator voice, no
engagement-bait. Suggest 3 accounts to reply to where the ICP argues about tokens.
```

### Module C — Reddit (organic-FIRST)
> 9:1 rule, karma/age gates, read sub rules, disclose you're the maker. One bad
> post = banned.
```
PROMPT 6C — REDDIT (DYOR)

1. Find 6–10 subs where fundamentals-first crypto investors hang out (size +
   self-promo strictness): r/CryptoCurrency, r/defi, r/ethfinance,
   r/CryptoTechnology, r/CryptoMarkets, etc.
2. For the top 3: recurring pains about vetting tokens, the exact words used, tools
   they mention, what they wish existed.
3. A 2-week value-first plan: 5 helpful comment opportunities + 1 "I built this to
   solve my own DYOR" post (only where allowed), framed as feedback-seeking. Include
   the exact maker-disclosure line. Flag anything that breaks self-promo rules.
```

### Module D — Open-source / HN + niche technical
```
PROMPT 6D — OSS / HN (DYOR)

Write a "Show HN" post for DYOR (open, asset-class-aware token scorer; free data;
transparent methodology; CLI/API/web).
- Lead with the problem (paywalled black-box screeners vs. raw-data overload).
- Plain, technical explanation (this crowd is expert) + the open-source/methodology
  angle + honest status.
- 4–5 specific questions that prompt feedback (scoring choices, asset-class logic,
  data sources). Expect "is it open source?" — answer up front.
Also draft the GitHub README hook + the one-line repo description.
```

### Module F — Farcaster / creator collabs  ⬜
```
PROMPT 6F — FARCASTER + CREATORS (DYOR)

1. A Farcaster launch: a "score any token" frame concept + 3 casts (score-card on a
   trending token, build-in-public, contrarian).
2. A shortlist of 8 mid-tier crypto research creators (YouTube/newsletter/CT) whose
   audience = our ICP, and a value-first collab pitch (let them run DYOR live on
   their picks; co-branded score-cards).
```

---

## Phase 7 — Deploy  ⬜ TODO
```
PROMPT 7 — DEPLOY (DYOR)

Deploy the public app: Next.js → Vercel; FastAPI → a hosted Python host (Fly/
Render/Railway) with the CoinGecko/other keys as needed for rate limits; point
NEXT_PUBLIC_API_URL at it. Verify live: Analyze works, score-card OG images render,
waitlist + analytics fire, mobile clean, "not financial advice" present. Link the
live URL + dashboard.  `>> FILL: hosts · domain · tokens`
```

---

## Phase 8 — Launch (organic-FIRST, stagger)
- Stagger the CT thread, the Reddit value post, and the Show HN — **don't blast the
  same message the same hour.** Lead with the single most surprising score-card.
- No paid until organic proves the hook (Phase-0 thresholds).

---

## Phase 9 — Measure & Scale
```
PROMPT 9 — ANALYZE (DYOR)

From the usage dashboard + channel data: per-channel uniques, analyses, 7-day
return, shares, waitlist conversion. Identify the score-card posts / hooks that
drove the most analyses. Generate 5 variations of each winner. Against the Phase-0
kill-metric (≥1k analyses · ≥25% return · ≥20 shares · ≥3% waitlist) — is demand
real enough to invest in (Pro/alerts/API)? **Build-more / Iterate-angle / Kill.**
```

---

## Folder structure (this instance)
```
/growth
  /Documentation     - Positioning Spec.md
  /Reference Images  - asset-plan.md, screenshots, score-card
  /Marketing Assets
    /x               - threads, score-cards
    /reddit          - contribution plan, posts
    /oss             - Show HN, README hook
    /farcaster       - frame + casts, creator pitches
  /Results           - weekly-readouts.md
```

## Tooling (DYOR)
| Need | Tool |
|---|---|
| Research, spec, copy, code | Claude (this) |
| Visuals | **Real screen recordings + score-card OG images** (skip AI hero art) |
| Deploy | Vercel (web) + Fly/Render/Railway (API) |
| Paid (later, only if organic proves) | — (avoid Meta/LinkedIn/Google) |
| Organic | Crypto Twitter/X · Reddit · HN/GitHub · Farcaster · TG/Discord |
| Analytics | Self-host / Plausible-style + own usage dashboard |
