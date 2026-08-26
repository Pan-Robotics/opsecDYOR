import Link from "next/link";

const FEATURES: { href: string; icon: string; title: string; body: string; tag: string }[] = [
  {
    href: "/analyze", icon: "🔍", title: "Analyze any token", tag: "name · symbol · contract",
    body: "Search by name, ticker, or contract address — it resolves the unified token across every chain. Get an asset-class-aware 0–1 score, A–D tier, gate flags, confidence + robustness, a market snapshot, every web/social link, a peer comparison, and a one-click analyst memo.",
  },
  {
    href: "/screener", icon: "📊", title: "Tier screener", tag: "build · filter",
    body: "A scored universe grouped into tier tabs (A→D). Build a fresh top-N by TVL in the background, or filter by asset class, minimum tier, real yield, and gate flags. Click any token to dive into its full analysis.",
  },
  {
    href: "/tools", icon: "🧪", title: "Portfolio · Barbell · Backtest", tag: "construction",
    body: "Score a whole portfolio (tier + narrative exposure, flagged risks). Build the thesis' Barbell — a BTC anchor plus qualified, ungated satellites. Backtest whether the tiers actually predicted forward returns.",
  },
  {
    href: "/narratives", icon: "🔥", title: "Narrative rotation", tag: "early signals",
    body: "Which sectors are heating — AI, DePIN, RWA, gaming, privacy — ranked by momentum across 700+ CoinGecko categories. Spot capital rotation before price follows.",
  },
  {
    href: "/methodology", icon: "📖", title: "Transparent methodology", tag: "not a black box",
    body: "Every weight, tier threshold, hard disqualifier gate, asset-class profile, and metric definition — out in the open. Read exactly why a token scored the way it did.",
  },
];

const STEPS = [
  ["Ingest", "Live data from free/open sources — DefiLlama, CoinGecko, CryptoRank, Ethplorer, Santiment, GitHub, Sourcify."],
  ["Classify", "Type each token — DeFi, L1, monetary, memecoin, stablecoin — and judge it on what matters for it."],
  ["Measure", "Derived metrics: P/F, P/S, FDV/MCAP, token-sink, unlock overhang, holder concentration, growth."],
  ["Score", "Normalize across same-class peers, weight by domain, then gate — hard red flags cap or zero the score."],
  ["Rank", "Map the 0–1 score to a tier — A (high conviction) → D (avoid) — with a confidence + robustness read."],
];

const CLASSES = [
  ["DeFi protocol", "Fees, revenue, TVL, value accrual."],
  ["L1 / platform", "Ecosystem TVL, adoption, dev activity."],
  ["Monetary", "Scarcity + accumulation — no revenue expected."],
  ["Memecoin", "Distribution, liquidity, social attention."],
  ["Stablecoin", "Adoption + distribution; not a price play."],
];

export default function Home() {
  return (
    <div className="space-y-16">
      {/* hero */}
      <section className="pt-6">
        <div className="pill border border-brand/30 bg-brand/10 text-brand">Flight to fundamentals · open data · agent-ready</div>
        <h1 className="mt-4 max-w-3xl text-4xl font-bold tracking-tight text-white sm:text-5xl">
          Qualify any crypto token on the dimensions that actually matter.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          DYOR scores tokens on real revenue, durable tokenomics, and actual usage —{" "}
          <span className="text-white">asset-class-aware</span>, so Bitcoin isn&apos;t judged like a DeFi app.
          Search any token, screen a universe, build a portfolio, or call it from your AI agent. Built on free, open data.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link href="/analyze" className="btn">🔍 Analyze a token</Link>
          <Link href="/screener" className="rounded-lg border border-edge px-4 py-2 text-sm font-semibold text-white hover:bg-panel2">Open the screener</Link>
          <Link href="/methodology" className="rounded-lg border border-edge px-4 py-2 text-sm font-semibold text-muted hover:bg-panel2 hover:text-white">How scoring works</Link>
        </div>
      </section>

      {/* feature grid */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Everything DYOR does</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {FEATURES.map((f) => (
            <Link key={f.href} href={f.href}
              className="card group transition hover:border-brand/50 hover:bg-panel2">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{f.icon}</span>
                  <h3 className="font-semibold text-white">{f.title}</h3>
                </div>
                <span className="pill border border-edge bg-panel2 text-muted">{f.tag}</span>
              </div>
              <p className="mt-2 text-sm text-muted">{f.body}</p>
              <div className="mt-3 text-sm font-medium text-brand opacity-0 transition group-hover:opacity-100">Open →</div>
            </Link>
          ))}
          {/* MCP / agent card */}
          <div className="card bg-gradient-to-br from-panel to-panel2">
            <div className="flex items-center gap-2">
              <span className="text-xl">🧭</span>
              <h3 className="font-semibold text-white">Agent-callable (MCP)</h3>
              <span className="pill ml-auto border border-brand2/30 bg-brand2/15 text-brand2">for AI agents</span>
            </div>
            <p className="mt-2 text-sm text-muted">
              DYOR ships a <span className="text-white">hosted MCP server</span> — Claude, Cursor, Manus and other agents can call
              it as tools: <code>analyze_token</code>, <code>screen_tokens</code>, <code>analyst_memo</code>,{" "}
              <code>score_portfolio</code>, <code>build_barbell</code>, <code>backtest</code>. No install — point your agent
              at the URL and ask “is $TOKEN worth a look?” for an opinionated, gated read.
            </p>
            <div className="mt-3 rounded-lg border border-edge bg-bg/60 p-2 font-mono text-xs text-muted">claude mcp add --transport http dyor https://dyor.cryptoopsec.com/mcp</div>
            <Link href="/api-mcp" className="mt-3 inline-block text-sm font-semibold text-brand hover:text-brand2">
              API &amp; MCP docs — endpoints, connection, tools →
            </Link>
          </div>
        </div>
      </section>

      {/* how it works */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">How it works</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map(([h, b], i) => (
            <div key={h} className="card">
              <div className="text-xs text-brand">Step {i + 1}</div>
              <div className="mt-1 font-semibold text-white">{h}</div>
              <div className="mt-2 text-sm text-muted">{b}</div>
            </div>
          ))}
        </div>
      </section>

      {/* asset classes */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Judged on their own terms</h2>
        <p className="mt-1 text-sm text-muted">Each token is classified and scored with a class-appropriate profile — “no protocol revenue” is fatal for a DeFi app but a non-issue for Bitcoin.</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CLASSES.map(([label, desc]) => (
            <div key={label} className="card">
              <div className="font-semibold text-white">{label}</div>
              <div className="mt-1 text-sm text-muted">{desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* trust / gate / open */}
      <section className="grid gap-4 md:grid-cols-3">
        <div className="card">
          <div className="font-semibold text-white">🚫 The gate</div>
          <p className="mt-1 text-sm text-muted">Hard disqualifiers <b className="text-white">cap or zero</b> a score so a flaw can&apos;t be averaged away — unverified contract, extreme FDV/MCAP, or a dead token (no commits 6mo+, ~99% off ATH, near-zero volume).</p>
        </div>
        <div className="card">
          <div className="font-semibold text-white">🎯 Confidence + robustness</div>
          <p className="mt-1 text-sm text-muted">Every score says how complete the data is and whether the tier survives re-weighting — so a thin or fragile call is labelled, not hidden.</p>
        </div>
        <div className="card">
          <div className="font-semibold text-white">🟢 Open &amp; free</div>
          <p className="mt-1 text-sm text-muted">No paywall, no black box. Built entirely on free/open data, with a transparent, inspectable methodology and an open API.</p>
        </div>
      </section>

      {/* testimonial — unsolicited public feedback on X from a source in the data stack */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">What others are saying</h2>
        <figure className="card mt-4 border-brand/30 bg-gradient-to-br from-panel to-panel2">
          <blockquote className="text-lg leading-relaxed text-white">
            <span aria-hidden="true" className="mr-1 font-orbitron text-2xl text-brand">“</span>
            Nice work — and thanks for including{" "}
            <a href="https://x.com/ethplorer" target="_blank" rel="noopener noreferrer"
              className="text-brand hover:text-brand2">@ethplorer</a>{" "}
            in the data stack. We tested four projects in DYOR and found its risk signals broadly
            aligned with our own framework based on stablecoin reserves and the Printing-Press
            Index (PPI).
          </blockquote>
          <figcaption className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <a href="https://x.com/ethplorer" target="_blank" rel="noopener noreferrer"
              className="font-semibold text-white hover:text-brand">Ethplorer</a>
            <span className="text-muted">Ethereum token explorer &amp; analytics · on X</span>
            <span className="pill border border-edge bg-panel2 text-muted">holder-concentration source</span>
          </figcaption>
        </figure>
      </section>

      {/* CTA */}
      <section className="card flex flex-col items-start gap-3 bg-gradient-to-br from-panel to-panel2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-lg font-semibold text-white">Search any token — by name, symbol, or contract address.</div>
          <div className="text-sm text-muted">Research aid, not financial advice.</div>
        </div>
        <Link href="/analyze" className="btn whitespace-nowrap">Start analyzing →</Link>
      </section>
    </div>
  );
}
