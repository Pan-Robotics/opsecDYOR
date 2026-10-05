import type { Metadata } from "next";
import Link from "next/link";
import { SITE, appJsonLd, jsonLd } from "@/lib/seo";
import VideoEmbed from "@/components/VideoEmbed";
import Pricing from "@/components/Pricing";

export const metadata: Metadata = {
  title: { absolute: SITE.title },
  description: SITE.description,
  alternates: { canonical: "/" },
};

const FEATURES: { href: string; icon: string; title: string; body: string; tag: string }[] = [
  {
    href: "/analyze", icon: "🔍", title: "Analyze any token", tag: "name, symbol, contract",
    body: "Search by name, ticker, or contract address; it resolves the unified token across every chain. Get an asset-class-aware 0 to 100 score, A to D tier, gate flags, confidence and robustness, a market snapshot, every web and social link, a peer comparison, a share card, and a one-click analyst memo.",
  },
  {
    href: "/screener", icon: "📊", title: "Screener", tag: "rank, filter, compare",
    body: "Rank the whole board by composite score, by one domain such as tokenomics, or by one metric such as real yield or holder concentration, best or worst first. Filter by asset class, tier, gate flags and coverage, then compare your picks line for line.",
  },
  {
    href: "/tools", icon: "🧪", title: "Portfolio, Barbell, Backtest", tag: "construction",
    body: "Score a whole portfolio (tier and narrative exposure, flagged risks). Build the thesis' Barbell: a BTC anchor plus qualified, ungated satellites. Backtest whether the tiers actually predicted forward returns.",
  },
  {
    href: "/narratives", icon: "🔥", title: "Narrative rotation", tag: "early signals",
    body: "Which sectors are heating (AI, DePIN, RWA, gaming, privacy), ranked by momentum across 700+ CoinGecko categories. Spot capital rotation before price follows.",
  },
  {
    href: "/methodology", icon: "📖", title: "Transparent methodology", tag: "not a black box",
    body: "Every weight, tier threshold, hard disqualifier gate, asset-class profile, and metric definition, out in the open. Read exactly why a token scored the way it did.",
  },
];

const STEPS = [
  ["Ingest", "Live data from free, open sources: DefiLlama, CoinGecko, CryptoRank, Ethplorer, Santiment, GitHub, Sourcify."],
  ["Classify", "Type each token (DeFi, L1, monetary, memecoin, stablecoin) and judge it on what matters for it."],
  ["Measure", "Derived metrics: P/F, P/S, FDV/MCAP, token-sink, unlock overhang, holder concentration, growth."],
  ["Score", "Normalize across same-class peers, weight by domain, then gate: hard red flags cap or zero the score."],
  ["Rank", "Map the 0 to 100 score to a tier, from A (high conviction) to D (avoid), with a confidence and robustness read."],
];

const CLASSES = [
  ["DeFi protocol", "Fees, revenue, TVL, value accrual."],
  ["L1 / platform", "Ecosystem TVL, adoption, dev activity."],
  ["Monetary", "Scarcity and accumulation; no revenue expected."],
  ["Memecoin", "Distribution, liquidity, social attention."],
  ["Stablecoin", "Adoption + distribution; not a price play."],
];

export default function Home() {
  return (
    <div className="space-y-16">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(appJsonLd()) }} />
      {/* hero */}
      <section className="pt-6">
        <div className="pill border border-brand/30 bg-brand/10 text-brand">Flight to fundamentals, open data, agent-ready</div>
        <h1 className="mt-4 max-w-3xl text-[2rem] font-bold leading-tight tracking-tight text-white sm:text-5xl">
          Qualify any crypto token on the dimensions that actually matter.
        </h1>
        <p className="mt-4 max-w-2xl text-base text-muted sm:text-lg">
          DYOR scores tokens on real revenue, durable tokenomics, and actual usage. It is{" "}
          <span className="text-white">asset-class-aware</span>, so Bitcoin is not judged like a DeFi app.
          Search any token, screen a universe, build a portfolio, or call it from your AI agent. Built on free, open data.
        </p>
        {/* the case for the whole thing, in someone else's words: two independent Coin Bureau primers */}
        <div className="mt-6 max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Why fundamentals, why now</div>
          <div className="mt-2 grid gap-4 sm:grid-cols-2">
            <VideoEmbed id="ymC44d3Godo" title="Crypto Has CHANGED (You Need To Know How)" by="Coin Bureau" />
            <VideoEmbed id="JbnZ4AzZ2ik" title="How to Research Crypto Like a Pro in 2026" by="Coin Bureau" />
          </div>
          <p className="mt-2 text-sm text-muted">
            Two short primers on how the market has changed and how to research a token properly. DYOR turns that process
            into a score, with the working shown. Independent videos, not affiliated with DYOR.
          </p>
        </div>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link href="/analyze" className="btn">🔍 Analyze a token</Link>
          <Link href="/screener" className="btn-ghost">Open the screener</Link>
          <Link href="/methodology" className="btn-ghost !text-muted hover:!text-white">How scoring works</Link>
          {/* straight to the plans and the waitlist; green so it stands apart from the gold actions */}
          <a href="#pricing" className="inline-flex min-h-[2.5rem] items-center justify-center rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-[#04101b] transition hover:bg-emerald-400">
            Join now
          </a>
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
              <div className="mt-3 text-sm font-medium text-brand opacity-0 transition group-hover:opacity-100">Open</div>
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
              DYOR ships a <span className="text-white">hosted MCP server</span>. Claude, Cursor, Manus and other agents can call
              it as tools: <code>analyze_token</code>, <code>screen_tokens</code>, <code>analyst_memo</code>,{" "}
              <code>score_portfolio</code>, <code>build_barbell</code>, <code>backtest</code>. No install: point your agent
              at the URL and ask “is $TOKEN worth a look?” for an opinionated, gated read.
            </p>
            <div className="mt-3 break-all rounded-lg border border-edge bg-bg/60 p-2 font-mono text-xs text-muted">claude mcp add --transport http dyor https://dyor.cryptoopsec.com/mcp</div>
            <Link href="/api-mcp" className="mt-3 inline-block text-sm font-semibold text-brand hover:text-brand2">
              API and MCP docs: endpoints, connection, tools
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
        <p className="mt-1 text-sm text-muted">Each token is classified and scored with a class-appropriate profile. No protocol revenue is fatal for a DeFi app but a non-issue for Bitcoin.</p>
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
          <p className="mt-1 text-sm text-muted">Hard disqualifiers <b className="text-white">cap or zero</b> a score so a flaw cannot be averaged away: extreme FDV/MCAP, no audit on record (DefiLlama), or a dead token (no push in six months or more on any GitHub account we can find for it and no Santiment dev activity to contradict that, or near-zero volume). Contract-verification and team gates need keyed sources and are marked inactive on open data.</p>
        </div>
        <div className="card">
          <div className="font-semibold text-white">🎯 Confidence + robustness</div>
          <p className="mt-1 text-sm text-muted">Every score says how complete the data is and whether the tier survives re-weighting, so a thin or fragile call is labelled, not hidden.</p>
        </div>
        <div className="card">
          <div className="font-semibold text-white">🟢 Free core, open methodology</div>
          <p className="mt-1 text-sm text-muted">The analyzer, screener, compare view and token pages are free, need no account, and show the same score to everyone. No black box: the methodology is inspectable and the API is documented. Paid tiers add the pipes and the depth; see the <a href="#pricing" className="text-brand hover:text-brand2">plans</a>.</p>
        </div>
      </section>

      {/* testimonial — unsolicited public feedback on X from a source in the data stack */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">What others are saying</h2>
        <figure className="card mt-4 border-brand/30 bg-gradient-to-br from-panel to-panel2">
          <blockquote className="text-lg leading-relaxed text-white">
            <span aria-hidden="true" className="mr-1 font-orbitron text-2xl text-brand">“</span>
            Nice work, and thanks for including{" "}
            <a href="https://x.com/ethplorer/status/2080368802261254331" target="_blank" rel="noopener noreferrer"
              className="text-brand hover:text-brand2">@ethplorer</a>{" "}
            in the data stack. We tested four projects in DYOR and found its risk signals broadly
            aligned with our own framework based on stablecoin reserves and the Printing-Press
            Index (PPI).
          </blockquote>
          <figcaption className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <a href="https://x.com/ethplorer/status/2080368802261254331" target="_blank" rel="noopener noreferrer"
              className="font-semibold text-white hover:text-brand">Ethplorer</a>
            <a href="https://x.com/ethplorer/status/2080368802261254331" target="_blank" rel="noopener noreferrer"
              className="text-muted hover:text-white">Ethereum token explorer and analytics. View the post on X</a>
            <span className="pill border border-edge bg-panel2 text-muted">holder-concentration source</span>
          </figcaption>
        </figure>
      </section>

      {/* plans and the waitlist */}
      <Pricing />

      {/* CTA */}
      <section className="card flex flex-col items-start gap-3 bg-gradient-to-br from-panel to-panel2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-lg font-semibold text-white">Search any token by name, symbol, or contract address.</div>
          <div className="text-sm text-muted">Research aid, not financial advice.</div>
        </div>
        <Link href="/analyze" className="btn whitespace-nowrap">Start analyzing</Link>
      </section>
    </div>
  );
}
