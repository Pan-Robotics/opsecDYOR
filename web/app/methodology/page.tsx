import type { Metadata } from "next";
import Link from "next/link";
import { serverApi } from "@/lib/api";
import { breadcrumbJsonLd, faqJsonLd, jsonLd, pageMeta } from "@/lib/seo";

// Server-rendered so the weights, tiers, gates and the metric glossary are in
// the HTML a crawler reads — this is the page that explains what a DYOR score is.
export const dynamic = "force-dynamic";

export const metadata: Metadata = pageMeta({
  title: "Methodology: how DYOR scores crypto tokens",
  description: "How a DYOR score is built: percentiles against a same-class reference basket, per-domain averages, class-specific weights, hard disqualifier gates and A to D tiers, with every metric defined (P/F, P/S, MC/TVL, real yield, FDV/MCAP, float, holder concentration, address growth, dev activity).",
  path: "/methodology",
});

const FAQ = [
  { q: "What is a DYOR score?",
    a: "A 0 to 100 composite for one crypto token. Each feature (for example price-to-fees or holder concentration) is ranked as a percentile against a fixed reference basket of same-class tokens, features are averaged per domain (fundamentals, tokenomics, on-chain, social, developers), domains are weighted with class-specific weights, and any hard disqualifier that trips caps or zeroes the result." },
  { q: "What do the tiers mean?",
    a: "The tier is a fixed mapping of the final score: A (high conviction) is 80 and above, B (qualified) 60 to 79.9, C (watchlist) 40 to 59.9, D (avoid) below 40. Tiers are a research shorthand, not a buy or sell recommendation." },
  { q: "Why isn't Bitcoin judged on revenue like a DeFi protocol?",
    a: "Tokens are classified first (DeFi protocol, L1 / platform, monetary, memecoin, stablecoin) and each class scores only the dimensions that matter for it. A monetary asset has no fundamentals domain, so missing protocol revenue cannot hurt it; a DeFi app with no measurable fees, revenue or TVL has its fundamentals domain floored instead of skipped." },
  { q: "What are the gates?",
    a: "Hard disqualifiers checked after the composite: extreme FDV/MCAP (above 10x) caps the score at 40; no audit on record at DefiLlama caps a DeFi protocol at 50; a dead token (no push in 180 days on any GitHub account found for it with no Santiment developer activity to contradict it, or near-zero daily volume) zeroes the score. Missing data never trips a gate." },
  { q: "Where does the data come from?",
    a: "Free, open sources only: CoinGecko (market data, supply, community votes, watchlists), DefiLlama (fees, revenue, holders revenue, TVL, audits; parent protocols aggregate their versions), Santiment (daily active addresses and developer activity over a 90-day window), GitHub (most recent push), Ethplorer (top-10 holder shares), Sourcify (contract verification). Every token page lists each source's status and links to its page." },
  { q: "Why do scores move between weeks?",
    a: "Because the token's own data moved: a changed TVL, fee run-rate, usage trend or supply figure. The reference baskets that scores are ranked against change only when they are deliberately rebuilt, percentiles are interpolated and treat near-identical values as ties, and a source that fails on a given run has its last stored values carried forward and labelled stale, so outages and provider rounding do not move a score." },
];

export default async function MethodologyPage() {
  const m = await serverApi.methodology(false);

  return (
    <div className="space-y-8">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(faqJsonLd(FAQ)) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(breadcrumbJsonLd([
        { name: "Home", path: "/" }, { name: "Methodology", path: "/methodology" },
      ])) }} />
      <div>
        <h1 className="text-2xl font-bold text-white">📖 Methodology</h1>
        <p className="mt-1 max-w-3xl text-muted">
          Normalize, weight, gate, tier: asset-class-aware. Scores run 0 to 100: each feature is a percentile against the
          asset class&apos;s reference basket, averaged per domain, weighted with that class&apos;s weights, then capped by any gate
          that trips. Every token page shows the working behind each number.
        </p>
      </div>

      {!m && (
        <div className="card text-muted">The methodology service is temporarily unavailable; the definitions below still apply.</div>
      )}

      {m && (
        <>
          <section className="grid gap-4 lg:grid-cols-2">
            <div className="card">
              <h2 className="mb-3 font-semibold text-white">Domain weights (default / DeFi)</h2>
              {Object.entries(m.weights).map(([d, w]) => (
                <div key={d} className="flex items-center gap-3 py-1">
                  <div className="w-28 capitalize text-muted">{d}</div>
                  <div className="h-2 flex-1 rounded-full bg-edge">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${w * 100}%` }} />
                  </div>
                  <div className="w-12 text-right tabular-nums">{Math.round(w * 100)}%</div>
                </div>
              ))}
              {m.class_weights && (
                <div className="mt-4">
                  <div className="mb-1 text-xs uppercase text-muted">Per asset class</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="text-left uppercase text-muted">
                        <tr><th className="py-1 pr-2">class</th>{Object.keys(m.weights).map((d) => <th key={d} className="pr-2 text-right">{d}</th>)}</tr>
                      </thead>
                      <tbody>
                        {Object.entries(m.class_weights).filter(([c]) => c !== "general").map(([c, w]) => (
                          <tr key={c} className="border-t border-edge">
                            <td className="py-1 pr-2 text-white">{c}</td>
                            {Object.keys(m.weights).map((d) => <td key={d} className="pr-2 text-right tabular-nums">{w[d] != null ? `${Math.round(w[d] * 100)}%` : "n/a"}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <div className="card">
              <h2 className="mb-3 font-semibold text-white">Tiers</h2>
              <div className="flex flex-wrap gap-2">
                {m.tiers.map((t) => (
                  <span key={t.label} className="pill border border-edge bg-panel2 text-white">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: t.color }} /> {t.label}
                    <span className="ml-1 text-muted">{t.min}+</span>
                  </span>
                ))}
              </div>
              <h2 className="mb-2 mt-5 font-semibold text-white">Hurdle</h2>
              <p className="text-sm text-muted">
                10Y treasury <b className="text-white">{m.reference.treasury_10y_yield_pct}%</b> (as of {m.reference.reference_date}).
                A token paying real yield below it is flagged.
              </p>
            </div>
          </section>

          <section>
            <h2 className="mb-3 font-semibold text-white">Asset classes</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {m.classes.map((c) => (
                <div key={c.name} className="card">
                  <div className="font-semibold text-white">{c.label}</div>
                  <div className="mt-1 text-sm text-muted">{c.description}</div>
                  <div className="mt-2 text-xs text-muted">Judged on: {c.domains.join(", ")}</div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-3 font-semibold text-white">Gate: hard disqualifiers</h2>
            <div className="card space-y-2 text-sm">
              {Object.entries(m.gating).map(([g, rule]) => (
                <div key={g} className="flex flex-wrap items-center gap-2">
                  <span className={rule.active_on_open_data ? "text-white" : "text-muted line-through decoration-edge"}>
                    • {g.replace(/_/g, " ")}
                  </span>
                  <span className="pill border border-edge bg-panel2 text-muted">
                    {rule.action === "zero" ? "zeroes" : `caps at ${rule.cap}`}
                    {rule.threshold ? `, above ${rule.threshold}x` : ""}
                  </span>
                  {!rule.active_on_open_data && (
                    <span className="pill border border-amber-500/30 bg-amber-500/10 text-amber-300">inactive on open data, needs a keyed source</span>
                  )}
                </div>
              ))}
              <p className="pt-1 text-xs text-muted">
                Gates marked inactive are wired but cannot fire on free data: contract verification is True-or-unknown (Sourcify can&apos;t prove a negative), and team-anonymity facts have no keyless source.
              </p>
            </div>
          </section>

          <section>
            <h2 className="mb-3 font-semibold text-white">Metric glossary</h2>
            <div className="card !p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted">
                  <tr className="border-b border-edge"><th className="p-3">Metric</th><th className="p-3">Good</th><th className="p-3">Meaning</th></tr>
                </thead>
                <tbody>
                  {m.glossary.map((g) => (
                    <tr key={g.key} className="border-b border-edge/60">
                      <td className="p-3 font-medium text-white">{g.label}</td>
                      <td className="p-3">{g.direction === "lower" ? "lower is better" : "higher is better"}</td>
                      <td className="p-3 text-muted">{g.meaning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="mb-3 font-semibold text-white">🧠 Break your thesis</h2>
            <ul className="card list-disc space-y-1 pl-8 text-sm text-muted">
              {m.break_thesis.map((q) => <li key={q}>{q}</li>)}
            </ul>
          </section>
        </>
      )}

      <section>
        <h2 className="mb-3 font-semibold text-white">Frequently asked</h2>
        <div className="space-y-3">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="card group">
              <summary className="cursor-pointer font-medium text-white">{q}</summary>
              <p className="mt-2 text-sm text-muted">{a}</p>
            </details>
          ))}
        </div>
        <p className="mt-4 text-sm text-muted">
          See it applied: <Link href="/tokens" className="text-brand hover:text-brand2">every scored token</Link> or{" "}
          <Link href="/analyze" className="text-brand hover:text-brand2">analyze one live</Link>.
        </p>
      </section>
    </div>
  );
}
