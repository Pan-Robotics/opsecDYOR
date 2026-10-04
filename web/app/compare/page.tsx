import type { Metadata } from "next";
import Link from "next/link";
import { serverApi, type Analysis, type ExplainFeature } from "@/lib/api";
import { SITE, breadcrumbJsonLd, jsonLd, pageMeta, tierLetter } from "@/lib/seo";
import { DOMAIN_LABELS, METRICS, fmtMetric } from "@/lib/metrics";
import { TierBadge, fmt, fmtUsd } from "@/components/ui";
import ComparePicker from "@/components/ComparePicker";

// Several tokens, line for line: one column per token, one row per figure, the
// best value in each numeric row highlighted. Server-rendered from the board.
export const dynamic = "force-dynamic";

const ID_OK = /^[a-z0-9][a-z0-9-]{0,99}$/;
type Props = { searchParams: Promise<{ tokens?: string }> };

function parseIds(raw?: string): string[] {
  return Array.from(new Set((raw ?? "").split(",").map((s) => s.trim().toLowerCase()).filter((s) => ID_OK.test(s)))).slice(0, 6);
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const ids = parseIds((await searchParams).tokens);
  if (ids.length === 0) {
    return pageMeta({
      title: "Compare crypto tokens side by side",
      description: "Put up to six tokens next to each other: DYOR score and tier, every domain, every metric with its percentile, gate flags, coverage and market figures, line for line.",
      path: "/compare",
    });
  }
  const sorted = [...ids].sort();
  const res = await serverApi.compare(sorted, false);
  const names = (res?.tokens ?? []).map((t) => `${t.resolved?.name} (${t.resolved?.symbol})`);
  const title = names.length ? `${names.join(" vs ")}: DYOR scores compared` : "Compare crypto tokens side by side";
  return pageMeta({
    title,
    description: names.length
      ? `${names.join(", ")} compared line for line on DYOR: 0 to 100 score, tier, fundamentals, tokenomics, on-chain, social and developer domains, every metric with its percentile, gate flags and market figures.`
      : "Compare up to six tokens on DYOR.",
    path: `/compare?tokens=${encodeURIComponent(sorted.join(","))}`,
  });
}

type Row = { label: string; cells: { text: string; sub?: string; value?: number | null }[]; higherIsBetter?: boolean; muted?: boolean };

function featureRow(tokens: Analysis[], key: string): Row | null {
  const metric = METRICS.find((m) => m.key === key);
  const cells = tokens.map((t) => {
    const f = (t.explain?.features ?? []).find((x: ExplainFeature) => x.feature === key);
    if (!f) return { text: "n/a", value: null };
    if (f.status !== "scored") return { text: "n/a", sub: f.missing_reason ?? undefined, value: null };
    return { text: fmtMetric(f.value, metric?.unit), sub: f.percentile !== null ? `pct ${Math.round(f.percentile)}` : undefined, value: f.value };
  });
  if (cells.every((c) => c.value === null)) return null;
  return { label: metric?.label ?? key, cells, higherIsBetter: metric?.higherIsBetter };
}

export default async function ComparePage({ searchParams }: Props) {
  const ids = parseIds((await searchParams).tokens);
  const [index, res] = await Promise.all([serverApi.tokens(false), ids.length ? serverApi.compare(ids, false) : Promise.resolve(null)]);
  const options = (index?.tokens ?? []).map((t) => ({ id: t.id, name: t.name, symbol: t.symbol }));
  const tokens = (res?.tokens ?? []).filter((t) => t.resolved && t.score);
  const missing = res?.missing ?? [];

  const groups: { title: string; rows: Row[] }[] = [];
  if (tokens.length) {
    groups.push({
      title: "Score",
      rows: [
        { label: "DYOR score (0 to 100)", cells: tokens.map((t) => ({ text: fmt(t.score!.final_score), value: t.score!.final_score })), higherIsBetter: true },
        { label: "Tier", cells: tokens.map((t) => ({ text: t.score!.tier })) },
        { label: "Asset class", cells: tokens.map((t) => ({ text: t.record.class.label })) },
        { label: "Rank among class peers", cells: tokens.map((t) => ({ text: t.rank ? `#${t.rank} of ${t.peer_count + 1}` : "n/a", value: t.rank ? -t.rank : null })), higherIsBetter: true },
        { label: "Data coverage", cells: tokens.map((t) => ({ text: t.score!.coverage === null ? "n/a" : `${Math.round(t.score!.coverage)}% (${t.score!.features_present}/${t.score!.features_total})`, value: t.score!.coverage })), higherIsBetter: true },
        { label: "Confidence", cells: tokens.map((t) => ({ text: t.score!.confidence ?? "n/a" })) },
        { label: "Gate flags", cells: tokens.map((t) => ({ text: t.score!.flags.join(", ") || "none" })) },
      ],
    });
    groups.push({
      title: "Domains (0 to 100, with each class's weight)",
      rows: Object.keys(DOMAIN_LABELS).map((d) => ({
        label: DOMAIN_LABELS[d],
        cells: tokens.map((t) => {
          const v = t.score!.domain_scores[d];
          const w = t.record.class.weights?.[d];
          return v === null || v === undefined
            ? { text: w ? "no data" : "not judged", value: null }
            : { text: fmt(v), sub: w ? `weight ${Math.round(w * 100)}%` : undefined, value: v };
        }),
        higherIsBetter: true,
      })).filter((r) => r.cells.some((c) => c.value !== null)),
    });
    for (const d of Object.keys(DOMAIN_LABELS)) {
      const rows = METRICS.filter((m) => m.kind === "feature" && m.domain === d).map((m) => featureRow(tokens, m.key)).filter((r): r is Row => !!r);
      if (rows.length) groups.push({ title: `${DOMAIN_LABELS[d]} metrics (value, percentile vs class peers)`, rows });
    }
    groups.push({
      title: "Market",
      rows: [
        { label: "Market cap", cells: tokens.map((t) => ({ text: fmtUsd(t.record.market?.market_cap), value: t.record.market?.market_cap ?? null })) },
        { label: "FDV", cells: tokens.map((t) => ({ text: fmtUsd(t.record.market?.fdv), value: t.record.market?.fdv ?? null })) },
        { label: "24h volume", cells: tokens.map((t) => ({ text: fmtUsd(t.record.market?.volume_24h), value: t.record.market?.volume_24h ?? null })) },
        { label: "Price change 24h", cells: tokens.map((t) => ({ text: t.record.market?.price_change_24h_pct == null ? "n/a" : `${t.record.market.price_change_24h_pct.toFixed(1)}%`, value: t.record.market?.price_change_24h_pct ?? null })), higherIsBetter: true },
        { label: "From all-time high", cells: tokens.map((t) => ({ text: t.record.market?.ath_change_pct == null ? "n/a" : `${t.record.market.ath_change_pct.toFixed(0)}%`, value: t.record.market?.ath_change_pct ?? null })), higherIsBetter: true },
      ],
    });
    groups.push({
      title: "Data sources this run",
      rows: ["coingecko", "defillama", "santiment", "github", "ethplorer", "sourcify", "cryptorank"].map((feed) => ({
        label: feed, muted: true,
        cells: tokens.map((t) => ({ text: t.record.feeds?.[feed] ?? "n/a" })),
      })),
    });
  }

  const path = ids.length ? `/compare?tokens=${encodeURIComponent([...ids].sort().join(","))}` : "/compare";

  return (
    <div className="space-y-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(breadcrumbJsonLd([
        { name: "Home", path: "/" }, { name: "Compare", path },
      ])) }} />
      <div>
        <h1 className="text-2xl font-bold text-white">Compare tokens</h1>
        <p className="mt-1 max-w-3xl text-muted">
          Up to six tokens line for line: score and tier, every domain with its weight, every metric with its percentile against
          same-class peers, gate flags, coverage and market figures. The best value in each row is highlighted. Scores from the board
          {res?.collected_at ? ` run of ${res.collected_at.slice(0, 10)}` : ""}; open any column for the full ledger.
        </p>
      </div>

      <ComparePicker initial={ids} options={options} />

      {missing.length > 0 && (
        <div className="card border-amber-500/30 bg-amber-500/10 text-sm text-amber-200">
          Not on the board: {missing.map((m, i) => (
            <span key={m}>{i > 0 ? ", " : ""}<Link href={`/analyze?q=${encodeURIComponent(m)}`} className="underline">{m}</Link></span>
          ))}. Open the link to analyze it live.
        </div>
      )}

      {tokens.length > 0 && (
        <div className="card !p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge align-bottom">
                <th className="p-3 text-left text-xs uppercase text-muted">Line</th>
                {tokens.map((t) => (
                  <th key={t.resolved!.gecko_id} className="p-3 text-left">
                    <Link href={`/token/${encodeURIComponent(t.resolved!.gecko_id)}`} className="text-base font-semibold text-white hover:text-brand">{t.resolved!.name}</Link>
                    <div className="text-xs text-muted">{t.resolved!.symbol}</div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-2xl font-bold text-white">{fmt(t.score!.final_score)}</span>
                      <TierBadge tier={tierLetter(t.score!.tier)} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <GroupRows key={g.title} title={g.title} rows={g.rows} n={tokens.length} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {ids.length === 0 && (
        <div className="card text-sm text-muted">
          Try a pairing: {[["aave", "uniswap"], ["bitcoin", "ethereum", "solana"], ["tether", "usd-coin", "dai"], ["pepe", "dogecoin"]].map((set, i) => (
            <span key={set.join()}>{i > 0 ? " / " : ""}<Link href={`/compare?tokens=${set.join(",")}`} className="text-brand hover:text-brand2">{set.join(" vs ")}</Link></span>
          ))}. Or tick tokens in the <Link href="/screener" className="text-brand hover:text-brand2">screener</Link>.
        </div>
      )}
      <p className="text-xs text-muted">{SITE.fullName}. Research aid, not financial advice.</p>
    </div>
  );
}

function GroupRows({ title, rows, n }: { title: string; rows: Row[]; n: number }) {
  return (
    <>
      <tr className="border-b border-edge bg-panel2/40">
        <td colSpan={n + 1} className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">{title}</td>
      </tr>
      {rows.map((r) => {
        const nums = r.cells.map((c) => (typeof c.value === "number" ? c.value : null));
        const present = nums.filter((v): v is number => v !== null);
        const best = r.higherIsBetter === undefined || present.length < 2 ? null
          : (r.higherIsBetter ? Math.max(...present) : Math.min(...present));
        return (
          <tr key={r.label} className="border-b border-edge/60">
            <td className={`p-3 ${r.muted ? "text-muted" : "text-white"}`}>{r.label}</td>
            {r.cells.map((c, i) => {
              const isBest = best !== null && nums[i] === best;
              return (
                <td key={i} className={`p-3 tabular-nums ${isBest ? "text-emerald-300" : c.value === null && r.higherIsBetter !== undefined ? "text-muted" : "text-white"}`}>
                  <div title={c.sub && c.text === "n/a" ? c.sub : undefined}>{c.text}{isBest ? " *" : ""}</div>
                  {c.sub && c.text !== "n/a" && <div className="text-xs text-muted">{c.sub}</div>}
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
