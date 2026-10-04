import type { Metadata } from "next";
import Link from "next/link";
import { serverApi, type TokenListing } from "@/lib/api";
import { breadcrumbJsonLd, jsonLd, pageMeta, tierLetter } from "@/lib/seo";
import { fmt, ScoreBar, TierBadge } from "@/components/ui";

// The crawlable index of the board: every scored token with a link to its
// permanent page, rendered on the server from the latest run.
export const dynamic = "force-dynamic";

export const metadata: Metadata = pageMeta({
  title: "All scored crypto tokens — DYOR scores and tiers",
  description: "Every token on the DYOR board with its 0–100 score, A–D tier, asset class and gate flags, grouped by tier and refreshed weekly. Open any token for the full ledger: raw figures, formulas, percentiles and weights.",
  path: "/tokens",
});

const TIERS: [string, string][] = [["A", "high conviction"], ["B", "qualified"], ["C", "watchlist"], ["D", "avoid"]];

export default async function TokensPage() {
  const index = await serverApi.tokens(false);
  const tokens = index?.tokens ?? [];
  const byTier: Record<string, TokenListing[]> = { A: [], B: [], C: [], D: [] };
  const unscored: TokenListing[] = [];
  for (const t of tokens) {
    const k = tierLetter(t.tier);
    if (byTier[k]) byTier[k].push(t); else unscored.push(t);
  }
  const date = index?.collected_at ? index.collected_at.slice(0, 10) : null;

  return (
    <div className="space-y-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(breadcrumbJsonLd([
        { name: "Home", path: "/" }, { name: "Tokens", path: "/tokens" },
      ])) }} />
      <div>
        <h1 className="text-2xl font-bold text-white">All scored tokens</h1>
        <p className="mt-1 max-w-3xl text-muted">
          {tokens.length} tokens on the board{date ? `, scored from the run of ${date}` : ""}: the top protocols by TVL plus every
          asset class&apos;s reference basket. Scores are 0–100 against same-class peers; the tier maps A ≥ 80, B ≥ 60, C ≥ 40, D below.
          Each page shows the full working. For filters and live rebuilds use the{" "}
          <Link href="/screener" className="text-brand hover:text-brand2">screener</Link>; for a token that isn&apos;t listed,{" "}
          <Link href="/analyze" className="text-brand hover:text-brand2">analyze it live</Link>.
        </p>
      </div>

      {tokens.length === 0 && (
        <div className="card text-muted">The board is empty on this instance — the weekly refresh hasn&apos;t run yet.</div>
      )}

      {TIERS.map(([letter, name]) => byTier[letter].length > 0 && (
        <section key={letter} className="space-y-2">
          <h2 className="text-lg font-semibold text-white">
            Tier {letter} <span className="text-sm font-normal text-muted">— {name} · {byTier[letter].length} token{byTier[letter].length === 1 ? "" : "s"}</span>
          </h2>
          <div className="card !p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-muted">
                <tr className="border-b border-edge">
                  <th className="p-3 w-8">#</th><th className="p-3">Token</th><th className="p-3">Class</th>
                  <th className="p-3 w-48">Score</th><th className="p-3">Tier</th><th className="p-3">Coverage</th><th className="p-3">Flags</th>
                </tr>
              </thead>
              <tbody>
                {byTier[letter].map((t, i) => (
                  <tr key={t.id} className="border-b border-edge/60 hover:bg-panel2/40">
                    <td className="p-3 text-muted">{i + 1}</td>
                    <td className="p-3 font-medium">
                      <Link href={`/token/${encodeURIComponent(t.id)}`} className="text-white hover:text-brand">
                        {t.name}{t.symbol ? <span className="ml-1 text-muted">{t.symbol}</span> : null}
                      </Link>
                    </td>
                    <td className="p-3 text-muted">{t.class_label}</td>
                    <td className="p-3"><div className="flex items-center gap-2"><ScoreBar value={t.final_score} /><span className="w-12 text-right tabular-nums">{fmt(t.final_score)}</span></div></td>
                    <td className="p-3"><TierBadge tier={t.tier} /></td>
                    <td className="p-3 tabular-nums text-muted">{t.coverage === null ? "—" : `${Math.round(t.coverage)}%`}</td>
                    <td className="p-3 text-xs text-rose-300">{t.flags.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      {unscored.length > 0 && (
        <div className="card text-sm text-muted">
          Insufficient data to score: {unscored.map((t, i) => (
            <span key={t.id}>{i > 0 ? ", " : ""}<Link href={`/token/${encodeURIComponent(t.id)}`} className="text-white hover:text-brand">{t.name}</Link></span>
          ))}
        </div>
      )}
    </div>
  );
}
