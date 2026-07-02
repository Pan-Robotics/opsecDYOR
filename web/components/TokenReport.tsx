import type { Analysis } from "@/lib/api";
import { ClassBadge, DomainBars, fmt, fmtNum, fmtUsd, ScoreBar, Stat, TierBadge } from "./ui";
import TokenLink from "./TokenLink";
import PriceChart from "./PriceChart";

const FEED_ICON: Record<string, string> = { ok: "🟢", empty: "⚪", error: "🔴", off: "⚫" };

export default function TokenReport({ a }: { a: Analysis }) {
  const r = a.resolved!;
  const s = a.score;
  const rec = a.record;
  const m = rec.market;

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-white">{r.name}</h1>
              <span className="text-muted">{r.symbol}</span>
              {rec.class && <ClassBadge label={rec.class.label} />}
              {rec.contract_verified && (
                <span className="pill border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">✓ verified</span>
              )}
            </div>
            <div className="mt-1 text-sm text-muted">
              matched by {r.matched_by}
              {r.market_cap_rank ? ` · CG rank #${r.market_cap_rank}` : ""} ·{" "}
              <code className="text-xs">{r.gecko_id}</code>
            </div>
            {rec.class && <div className="mt-2 max-w-xl text-sm text-muted">🏷️ {rec.class.description}</div>}
          </div>
          {s && (
            <div className="text-right">
              <div className="text-4xl font-bold text-white">{fmt(s.final_score, 3)}</div>
              <div className="mt-1"><TierBadge tier={s.tier} /></div>
              <div className="mt-1 text-xs text-muted">
                coverage {s.coverage === null ? "—" : `${Math.round(s.coverage * 100)}%`}
                {s.confidence ? ` · ${s.confidence} confidence` : ""}
                {s.tier_stability != null ? ` · ${Math.round(s.tier_stability * 100)}% tier-stable` : ""}
                {a.rank ? ` · rank #${a.rank}/${a.peer_count + 1}` : ""}
              </div>
            </div>
          )}
        </div>

        {s && (
          <>
            {s.flags.length > 0 && (
              <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
                <b>Gate flags:</b> {s.flags.join(", ")} — these capped or zeroed the score.
              </div>
            )}
            {s.advisories.map((adv) => (
              <div key={adv} className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                ⚠ {adv}
              </div>
            ))}
          </>
        )}
      </div>

      {/* market snapshot */}
      {m && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Price" value={m.price ? `$${m.price < 1 ? m.price.toPrecision(3) : m.price.toLocaleString()}` : "—"} />
          <Stat label="Market cap" value={fmtUsd(m.market_cap)} />
          <Stat label="FDV" value={fmtUsd(m.fdv)} />
          <Stat label="24h volume" value={fmtUsd(m.volume_24h)} />
          <Stat label="24h change" value={m.price_change_24h_pct === null ? "—" : `${m.price_change_24h_pct > 0 ? "+" : ""}${m.price_change_24h_pct.toFixed(1)}%`} />
          <Stat label="From ATH" value={m.ath_change_pct === null ? "—" : `${m.ath_change_pct.toFixed(0)}%`} />
          <Stat label="Circulating" value={fmtNum(m.circulating_supply)} />
          <Stat label="Total supply" value={fmtNum(m.total_supply)} />
        </div>
      )}

      {/* price chart */}
      <PriceChart id={r.gecko_id} />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* domain scores */}
        {s && (
          <div className="card">
            <h3 className="mb-3 font-semibold text-white">Domain scores</h3>
            <p className="mb-3 text-xs text-muted">Normalized 0–1 vs. the peer set, using this asset class&apos;s profile.</p>
            <DomainBars score={s} />
          </div>
        )}

        {/* cross-chain + resources */}
        <div className="card">
          <h3 className="mb-3 font-semibold text-white">Cross-chain &amp; resources</h3>
          <div className="text-sm text-muted">
            Present on <span className="text-white">{r.chains.length}</span> chain(s).
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(r.explorers).map(([chain, url]) => (
              <a key={chain} href={url} target="_blank" rel="noreferrer"
                 className="pill border border-edge bg-panel2 text-sky-300 hover:text-sky-200">
                {chain} ↗
              </a>
            ))}
          </div>
          <div className="mt-4">
            <div className="mb-1 text-xs uppercase text-muted">Links</div>
            <div className="flex flex-wrap gap-2 text-sm">
              {([
                ["🌐 Website", r.links.homepage],
                ["𝕏 / Twitter", r.links.twitter],
                ["💻 GitHub", r.links.github],
                ["💬 Discord", r.links.discord],
                ["✈️ Telegram", r.links.telegram],
                ["👽 Reddit", r.links.reddit],
                ["📄 Whitepaper", r.links.whitepaper],
                ["🦎 CoinGecko", r.coingecko_url],
              ] as [string, string | null | undefined][])
                .filter(([, url]) => url)
                .map(([label, url]) => (
                  <a key={label} href={url as string} target="_blank" rel="noreferrer"
                     className="pill border border-edge bg-panel2 text-brand hover:text-brand2">
                    {label} ↗
                  </a>
                ))}
            </div>
          </div>
          {rec.vc.num_backers !== null && (
            <div className="mt-4 text-sm text-muted">
              🏦 VC backers: <span className="text-white">{rec.vc.num_backers}</span>
              {rec.vc.had_public_sale ? " · had public sale" : ""}
            </div>
          )}
          {rec.feeds && (
            <div className="mt-4 text-xs text-muted">
              Feeds: {Object.entries(rec.feeds).map(([k, v]) => `${FEED_ICON[v] ?? "?"} ${k}`).join("   ")}
            </div>
          )}
        </div>
      </div>

      {/* metrics table */}
      <div className="card">
        <h3 className="mb-3 font-semibold text-white">The numbers behind it</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted">
              <tr><th className="py-2">Metric</th><th>Value</th></tr>
            </thead>
            <tbody>
              {Object.entries(rec.features).map(([k, v]) => (
                <tr key={k} className="border-t border-edge">
                  <td className="py-2 capitalize text-muted">{k.replace(/_/g, " ")}</td>
                  <td className="tabular-nums text-white">{typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* peers */}
      {a.peers.length > 1 && (
        <div className="card">
          <h3 className="mb-3 font-semibold text-white">Peer comparison</h3>
          <div className="space-y-2">
            {a.peers.map((p) => {
              const me = p.token === r.gecko_id;
              return (
                <div key={p.token} className={`flex items-center gap-3 rounded-lg px-2 py-1 ${me ? "bg-panel2" : ""}`}>
                  <div className="w-40 shrink-0 truncate text-sm">
                    {me ? <span className="text-white">⭐ {p.token}</span> : <TokenLink token={p.token} />}
                  </div>
                  <div className="flex-1"><ScoreBar value={p.final_score} /></div>
                  <div className="w-12 text-right text-sm tabular-nums">{fmt(p.final_score)}</div>
                  <div className="hidden w-32 text-right text-xs text-muted sm:block">{p.tier}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
