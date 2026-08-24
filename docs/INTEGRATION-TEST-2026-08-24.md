# Full Data-Integration Test — 2026-08-24

**Question asked:** are all data channels and calculations functioning, and why
does a token's analysis change when nothing about it should have changed?

**Answer:** every supplier is functioning and the calculations are sound. The
drift is real, reproducible, and comes from neither — it comes from the
reference anchor, which is not actually fixed.

Basket: **117 tokens** spanning all five asset classes (DefiLlama top-80 by TVL
∪ every class reference basket). Two full live collections, 23.5 min and 23.0
min. Raw artifacts and scripts: see the scratchpad `dyortest/` directory
(`run_A.json`, `run_B.json`, `analysis.json`, `anchor_drift.json`,
`cache_pinning.json`, `fix_probe.json`, `tradeoff.json`, `idmap.json`).

---

## 1. Supplier health — all green, no hard failures

116 of 117 targets produced a record. The single miss is `linear-protocol-lnr`
(no CoinGecko market data — a delisted token, correctly reported not silently
dropped).

| Supplier | ok | empty | error | off | success on configured |
|---|---:|---:|---:|---:|---:|
| coingecko | 116 | 0 | 0 | 0 | **100.0%** |
| ethplorer | 75 | 0 | 0 | 41 | **100.0%** |
| defillama | 91 | 3 | 0 | 22 | **96.8%** |
| sourcify | 71 | 4 | 0 | 41 | **94.7%** |
| github | 11 | 2 | 0 | 103 | **84.6%** |
| cryptorank | 71 | 45 | 0 | 0 | **61.2%** |
| santiment | 41 | 75 | 0 | 0 | **35.3%** |

**Zero hard errors from any supplier.** A separate wire-level smoke test (one
call per endpoint, cache bypassed, response shape asserted) passed 13/14 — the
only failure is `santiment.social_volume`, which is the known key-gated metric
the collector skips when no key is configured. It is not wired into scoring.

`off` means the feed was never configured for that token (no eth contract, no
GitHub org), not a failure.

### The two coverage holes are id-mapping, not breakage

Both `santiment_slug` and `cryptorank_key` are set best-effort to the gecko_id.
Resolving the 75 Santiment misses against Santiment's own 2,854-project list:

- **49** are genuinely not tracked by Santiment → honest `n/a`, nothing to fix
- **17** have a valid slug but the metric returned empty (free-tier asset limits)
- **9** exist under a *different* slug → recoverable with a real id map
  (`tornado-cash`→`torn`, `starknet`→`starknet-token`, `polkadot`→`polkadot-new`,
  `quickswap`→`p-quickswap-new`, `benqi`→`a-benqi`, …)

`polkadot` and `aptos` are both in the **L1 reference basket**, so this directly
thins the L1 anchor — the l1 basket carries `address_growth` for only 5 of its
12 tokens.

---

## 2. Calculations — sound

**2 violations across 116 tokens × ~20 features** (range checks, plus identity
checks recomputing `float_ratio` and `fdv_mcap_ratio` from the raw market
snapshot):

- `savings-xdai` float_ratio = **1.00034**
- `ethena-usde` float_ratio = **1.00038**

Both are CoinGecko reporting circulating supply marginally above total supply.
Cosmetic — but `float_ratio` is contractually `[0,1]` and should be clamped.

Everything else checks out: no negative ratios, no out-of-range concentrations
or sentiment, no `contract_verified: False` (correct — it is True-or-None by
design), and both derived ratios reproduce exactly from supply figures.

### Determinism and peer-set invariance both hold

| Test | Result |
|---|---|
| Same records scored 5× | **0 mismatches** |
| Records shuffled 5× | **0 mismatches** |
| Peer-set invariance (full universe / same class / random-15 / alone), 32-token stored run | **0 tier changes**, max score spread **0.0000** |
| Peer-set invariance, live 116-token basket, all 5 classes | **0/116 tier changes** |

The documented invariant — a token's tier is identical whether it is the
analyze subject, a peer, or a screener row — **holds exactly**, given a fixed
anchor.

### Classifier

`defi` 81 · `l1` 13 · `stablecoin` 9 · `meme` 7 · `monetary` 6 · `general` **0**.
No token fell into `general`, which is the class with no reference basket at all.

---

## 3. Run-to-run data drift is negligible

Two full collections 23 minutes apart. Only two fields moved:

| Field | Supplier | Changed | Max relative Δ |
|---|---|---:|---:|
| `days_since_last_commit` | github | 11/11 | 270% |
| `dev_commit_trend` | santiment | 5/28 | 4.6% |

`days_since_last_commit` is `now − last_push`, so it moves by construction — and
it is a gate input, not a scored feature. `dev_commit_trend` moves because
Santiment is the one client with **no cache at all** and its 28-day window is
built from `datetime.now()` at microsecond precision, so every call slides.

**Net effect on output: 0 of 116 scores moved. 0 tier changes.**

So the suppliers are not the source of the drift you noticed.

---

## 4. Root cause: the reference anchor is not fixed

`reference_distributions()` builds each class's distribution as **curated basket
∪ the latest persisted run** (`dyor/reference.py`). The yardstick therefore
changes whenever *any* same-class token is persisted.

Reproduced in a sandboxed DB copy, scoring byte-identical records:

| Trigger | Scores moved | Tier changes | Max Δ |
|---|---:|---:|---:|
| A smaller run persisted (screener rebuild, different top-N) | **29/32** | **6** | 0.188 |
| **One unrelated token** analyzed + persisted | **27/32** | **2** | 0.018 |
| Original run restored | 0/32 | 0 | 0.0000 |

`aave` C→D, `rocket-pool` B→C, `convex-finance` B→C — none of their own data
changed. The exact zero on restore proves the mechanism is anchor composition,
not randomness.

**Production triggers:** `/api/analyze?persist=true` (the API opts in), the
screener's "Build / refresh", and `dyor refresh` on cron. Analysing one token on
the site shifts every other token in its class.

### Second half: the anchor also depends on when a process started

`reference_distributions` is `@lru_cache`d for process lifetime and cleared only
by `build_references()`.

- Same warm worker, after an external persist: **0/32 changed** — it keeps serving the stale anchor
- A fresh process at the same DB moment: **29/32 differ from that worker, 6 different tiers**

So the website and the CLI can disagree about the same token, and the site's
answers jump after every `pm2 restart` — with no data change behind it.

---

## 5. The fix, and what it costs

Probe: monkeypatching `_same_class_stored` to return `[]` (anchor = curated
basket only) and re-running the exact scenarios above →
**0 moved, 0 tier changes, 0 NaN scores.** The drift disappears completely.

But the enrichment exists for a reason, and dropping it naively costs coverage:

| Class | Lost to relative fallback | Distribution thinning |
|---|---|---|
| monetary | none | none |
| meme | none | none |
| stablecoin | none | none |
| l1 | `mc_tvl`, `top10_concentration` | mild (13→12, 8→7) |
| defi | `top10_concentration` | **severe** — `float_ratio` 35→10, `fdv_mcap_ratio` 33→9, `mc_tvl` 29→5, `price_to_fees` 25→5 |

A 4–5 value distribution quantises percentiles into fifths, which is its own
source of jumpiness. So the correct fix is three steps, in order:

1. **Enrich the curated baskets properly.** `build_references._target` sets no
   `eth_contract`, which is exactly why the basket has no holder data — pass one
   from the CoinGecko coins_list, the way `universe.py` already does. Widen the
   baskets too (defi is 10 tokens; ~30 gives stable percentiles).
2. **Then decouple** — drop `_same_class_stored` from `reference_distributions`
   so the anchor is genuinely frozen and only `dyor reference` moves it.
3. **Key the cache to basket version** (or clear it on reference rebuild) so a
   long-lived API worker and a fresh CLI process can never disagree. Less urgent
   once step 2 lands, since the anchor stops moving.

Steps 1 and 2 can ship together; `monetary`, `meme` and `stablecoin` can be
decoupled immediately at zero cost.

---

## 6. Other findings

- **Three of the five gate rules are inert on live data.** `anonymous_team` and
  `no_audit` read `team_anonymous` / `audited`, which exist only in
  `sample_data.py`. `unverified_contract` needs an explicit `False` that open
  sources never produce. Live gating is effectively `extreme_fdv_mcap` +
  low-volume `dead_token`. The benchmark passes 4/4 on synthetic records that
  *do* carry those fields, so it does not cover this gap.
- **`docs/STAGES.md:73` is stale** — it says `dead_token` leans on a 99%-drawdown
  criterion; `config.yaml` and `gate.py` both removed drawdown deliberately.
- **Santiment has no cache and no quota guard.** Every analyze makes 2 live calls
  against a documented 1,000/month free tier — roughly 500 token-analyses a
  month for the whole hosted service. This test alone used ~470. When the quota
  runs out, `address_growth` and `dev_commit_trend` silently become `n/a`,
  coverage drops, and scores shift again. A FileCache (like every other client
  has) plus a day-rounded window would fix both the quota burn and the residual
  `dev_commit_trend` drift.
- **`float_ratio` should be clamped** to `[0,1]`.

---

## 7. Addendum — fixes implemented and verified (same day)

All fixes from §5–§6 were implemented and verified the same afternoon:

| Fix | Where |
|---|---|
| Anchor = curated basket ONLY (`_same_class_stored` removed) | `dyor/reference.py` |
| Anchor cache keyed per (class, basket version = `max(updated_at)`), re-read per lookup — warm workers converge with fresh CLIs without restart | `dyor/reference.py` |
| Baskets widened: defi 10→26, l1 12→15; `build_references` resolves `eth_contract` per basket token (one coins_list call) | `dyor/classes.py`, `dyor/reference.py` |
| Santiment on-disk POST cache (same TTL as GETs) + `use_cache` param | `dyor/ingestion/santiment.py` |
| Santiment window rounded to UTC midnight (cacheable + drift-free) | `dyor/collect.py` |
| `SLUG_OVERRIDES` id map (polkadot→polkadot-new, starknet→starknet-token, …8 entries) | `dyor/ingestion/santiment.py` |
| `float_ratio` clamped to [0, 1] | `dyor/metrics/tokenomics.py` |
| Stale docs corrected (drawdown criterion, inert gate rules) | `docs/STAGES.md` |

**Verification** (sandboxed copy of the rebuilt DB, byte-identical records, the
exact scenarios that failed before):

| Scenario | Before | After |
|---|---|---|
| Smaller run persisted (screener rebuild) | 29/32 moved, 6 tier flips | **0 / 0** |
| One unrelated token analyzed + persisted | 27/32 moved, 2 tier flips | **0 / 0** |
| Warm worker vs fresh process after a rebuild | 29/32 disagree, 6 tiers | **converge, no restart** |

`dyor reference` rebuilt the baskets live: 61 tokens stored (defi 25 — 
`synthetix-network-token` failed to collect; l1 15; monetary/meme/stablecoin 7
each). The enrichment worked: `top10_concentration` is now **anchored** for defi
(18 values), stablecoin (7) and present for l1/meme, where before it fell back
to relative for every class. Tests: **198 passed** (5 new regression tests
covering the frozen anchor, version-keyed cache, Santiment cache, slug map, and
the clamp).

**Notes.** Rebuilding the baskets is a deliberate one-time recalibration — local
scores shift once against the new anchor, then stay put. **Deployed to the VPS
the same day** (commit `0973ff0` → github.com/Pan-Robotics/opsecDYOR; code
rsync'd, verified baskets grafted into the server DB preserving its own 11 runs,
`dyor-api`+`dyor-mcp` restarted). Live drift regression PASSED: analyzing
litecoin (same class, persisted) left bitcoin's score bit-identical. Remaining
known limits: `social_trend`/`inflation_rate` stay relative (key-gated / no
source), and three gate rules stay inert on live data (§6).
