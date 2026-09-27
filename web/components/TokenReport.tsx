import type { Analysis, ExplainFeature, ExplainGateRule } from "@/lib/api";
import { ClassBadge, DomainBars, fmt, fmtNum, fmtUsd, ScoreBar, Stat, TierBadge, tierColor } from "./ui";
import TokenLink from "./TokenLink";
import PriceChart from "./PriceChart";

// One feed status vocabulary everywhere: the dot colour, the word, what it means.
const FEED_STATUS: Record<string, { dot: string; label: string; meaning: string }> = {
  ok: { dot: "bg-emerald-400", label: "ok", meaning: "returned data for this token — it is in the score" },
  empty: { dot: "bg-white", label: "empty", meaning: "reachable, but has nothing on this token (not tracked there) — scored without it" },
  error: { dot: "bg-rose-500", label: "error", meaning: "the request failed this run (rate limit / outage) — scored without it; retried next refresh" },
  off: { dot: "bg-slate-600", label: "off", meaning: "not queried — no identifier for this token, or the source needs a key / plan we don't have" },
};
const FEED_ROLE: Record<string, string> = {
  coingecko: "price, market cap, supply, volume, community up-votes, watchlists, repo links",
  defillama: "fees, revenue, holders revenue, TVL, audit record (protocol, or chain for an L1)",
  santiment: "daily active addresses and dev-activity events over a 28-day window",
  github: "most recent push across the project's accounts (dead-token gate)",
  ethplorer: "top-10 holder shares (Ethereum ERC-20s only)",
  sourcify: "contract source verification",
  cryptorank: "vesting schedule / unlock overhang (Pro plan)",
};
const FEED_ORDER = ["coingecko", "defillama", "santiment", "github", "ethplorer", "sourcify", "cryptorank"];

// Link fields come from third-party metadata; only ever render http(s) URLs.
const safeHref = (u: string | null | undefined) => (u && /^https?:\/\//i.test(u) ? u : null);

// Raw figures keep their own units; scores are 0–100.
function fmtVal(v: unknown, unit: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return `(${v.map((x) => `${Number(x).toFixed(1)}%`).join(" + ")})`;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string") return v;
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  switch (unit) {
    case "usd": return fmtUsd(n);
    case "count": return Math.abs(n) >= 1000 ? fmtNum(n) : n.toLocaleString(undefined, { maximumFractionDigits: 1 });
    case "pct": return `${n.toFixed(1)}%`;
    case "ratio": return `${(n * 100).toFixed(1)}%`;
    case "x": return `${Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2)}×`;
    case "days": return `${Math.round(n)}`;
    default: return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
}

// "{market_cap} ÷ ({fees_total} × 365 ÷ {fees_days})" → "$1.0B ÷ ($2.0M × 365 ÷ 30)"
function working(f: ExplainFeature): string | null {
  if (!f.formula) return null;
  let s = f.formula;
  for (const i of f.inputs) s = s.split(`{${i.key}}`).join(fmtVal(i.value, i.unit));
  return s;
}

function FeatureRow({ f }: { f: ExplainFeature }) {
  const scored = f.status === "scored";
  const calc = working(f);
  return (
    <tr className={`border-t border-edge align-top ${scored ? "" : "text-muted"}`}>
      <td className="py-2 pr-3">
        <div className={scored ? "text-white" : ""} title={f.meaning}>{f.label}</div>
        <div className="text-xs text-muted">{f.direction}{f.source ? ` · ${f.source}` : ""}</div>
      </td>
      <td className="py-2 pr-3 text-xs">
        {f.inputs.length ? f.inputs.map((i) => (
          <div key={i.key} className="whitespace-nowrap">
            <span className="text-muted">{i.label}:</span>{" "}
            <span className="tabular-nums text-white">{fmtVal(i.value, i.unit)}</span>
          </div>
        )) : <span>—</span>}
      </td>
      <td className="py-2 pr-3 text-xs">
        {calc ? (
          <div className="tabular-nums">
            <div className="text-muted">{calc}</div>
            <div className="text-white">= <b>{fmtVal(f.value, f.unit)}</b></div>
          </div>
        ) : scored ? (
          <span className="tabular-nums text-white">{fmtVal(f.value, f.unit)}</span>
        ) : (
          <span className="italic">{f.missing_reason}</span>
        )}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">
        {scored ? (
          <div>
            <div className="text-white">{fmt(f.percentile, 0)}</div>
            {f.reference_n ? <div className="text-xs text-muted">vs {f.reference_n} peers</div> : null}
          </div>
        ) : "—"}
      </td>
      <td className="py-2 pr-3 text-right text-xs tabular-nums">{f.weight === null ? "—" : `${f.weight.toFixed(1)}%`}</td>
      <td className="py-2 text-right tabular-nums">{f.contribution === null ? "—" : <span className="text-white">+{fmt(f.contribution)}</span>}</td>
    </tr>
  );
}

function GateRow({ g }: { g: ExplainGateRule }) {
  const inactive = !g.active_on_open_data;
  return (
    <tr className={`border-t border-edge align-top ${inactive ? "text-muted" : ""}`}>
      <td className="py-2 pr-3">
        <span className={g.tripped ? "text-rose-300" : inactive ? "line-through decoration-edge" : "text-white"}>{g.rule}</span>
      </td>
      <td className="py-2 pr-3 text-xs">
        {g.evidence.map((e) => (
          <div key={e.label}>
            <span className="text-muted">{e.label}:</span>{" "}
            <span className="tabular-nums text-white">{fmtVal(e.value, e.unit)}</span>
            {e.threshold ? <span className="text-muted"> · {e.threshold}</span> : null}
          </div>
        ))}
        {!g.evidence.length && <span>—</span>}
      </td>
      <td className="py-2 pr-3 text-xs">{g.action === "zero" ? "zeroes the score" : `caps the score at ${g.cap}`}</td>
      <td className="py-2 text-right text-xs">
        {g.tripped ? <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-rose-300">tripped</span>
          : inactive ? <span title="needs a keyed source; cannot fire on open data">inactive</span>
          : <span className="text-emerald-300">pass</span>}
      </td>
    </tr>
  );
}

export default function TokenReport({ a }: { a: Analysis }) {
  const r = a.resolved!;
  const s = a.score;
  const rec = a.record;
  const m = rec.market;
  const ex = a.explain ?? null;
  const sources = rec.sources ?? {};
  const feeds = rec.feeds ?? null;
  const feedKeys = feeds
    ? [...FEED_ORDER.filter((k) => k in feeds), ...Object.keys(feeds).filter((k) => !FEED_ORDER.includes(k))]
    : [];

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
              {rec.audited === true && (
                <span className="pill border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">✓ audited</span>
              )}
              {rec.audited === false && (
                <span className="pill border border-rose-500/30 bg-rose-500/10 text-rose-300" title="DefiLlama has no audit on record for this protocol">no audit on record</span>
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
              <div className="text-4xl font-bold text-white">
                {fmt(s.final_score)}<span className="text-lg font-normal text-muted">/100</span>
              </div>
              <div className="mt-1"><TierBadge tier={s.tier} /></div>
              <div className="mt-1 text-xs text-muted">
                coverage {s.coverage === null ? "—" : `${Math.round(s.coverage)}%`}
                {s.confidence ? ` · ${s.confidence} confidence` : ""}
                {s.tier_stability != null ? ` · ${Math.round(s.tier_stability)}% tier-stable` : ""}
                {a.rank ? ` · rank #${a.rank}/${a.peer_count + 1}` : ""}
              </div>
            </div>
          )}
        </div>

        {s && (
          <>
            {s.flags.length > 0 && (
              <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
                <b>Gate flags:</b> {s.flags.join(", ")} — these capped or zeroed the score (see the gate table below).
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
            <p className="mb-3 text-xs text-muted">0–100. Each domain is the mean of its scored features&apos; percentiles against this asset class&apos;s reference basket — the working is tabled below.</p>
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
            {Object.entries(r.explorers).filter(([, url]) => safeHref(url)).map(([chain, url]) => (
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
                .map(([label, url]) => [label, safeHref(url)] as [string, string | null])
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
        </div>
      </div>

      {/* data sources: status per feed, a link to the source's own page, and the key */}
      {feeds && (
        <div className="card">
          <h3 className="font-semibold text-white">Data sources</h3>
          <p className="mt-1 text-xs text-muted">What each source supplied for this token, with a link to its own page so every figure below can be checked at the source.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {feedKeys.map((k) => {
              const st = feeds[k];
              const meta = FEED_STATUS[st] ?? { dot: "bg-slate-500", label: st, meaning: "" };
              const url = safeHref(sources[k]);
              return (
                <div key={k} className="flex items-start gap-2 rounded-lg border border-edge bg-panel2 px-3 py-2 text-sm">
                  <span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${meta.dot}`} title={meta.label} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer" className="font-medium text-sky-300 hover:text-sky-200">{k} ↗</a>
                      ) : (
                        <span className="font-medium text-white">{k}</span>
                      )}
                      <span className="text-xs text-muted">{meta.label}</span>
                      {k === "github" && rec.github_account && <code className="text-xs text-muted">{rec.github_account}</code>}
                    </div>
                    <div className="text-xs text-muted">{FEED_ROLE[k] ?? ""}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 text-xs uppercase text-muted">Key</div>
          <dl className="mt-1 grid gap-1 text-xs text-muted sm:grid-cols-2">
            {Object.entries(FEED_STATUS).map(([k, v]) => (
              <div key={k} className="flex items-start gap-2">
                <span className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${v.dot}`} />
                <span><b className="text-white">{v.label}</b> — {v.meaning}</span>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* the working: inputs → formula → value → percentile → weight → composite → gate → tier */}
      {ex && s && (
        <div className="card">
          <h3 className="font-semibold text-white">How the score is built</h3>
          <p className="mt-1 text-xs text-muted">
            {ex.method.class_label}. Each feature is computed from the raw figures shown, then ranked as a percentile (0–100)
            {ex.method.reference_anchored ? ` against the ${ex.method.class} reference basket` : " within the peer set (no reference basket cached)"};
            features average within a domain; domains are weighted, with the weights renormalized over the domains that have data
            {ex.method.penalize_missing_core ? " (a domain the class is defined by is floored, not skipped, when it has none)" : ""};
            any gate that trips caps the result. Points = percentile × weight; they add up to the raw score.
          </p>

          {ex.domains.map((d) => {
            const rows = ex.features.filter((f) => f.domain === d.domain);
            const w = Math.round(d.weight * 100);
            const wn = d.weight_renormalized === null ? null : Math.round(d.weight_renormalized * 100);
            return (
              <div key={d.domain} className="mt-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <span className="font-semibold text-white">{d.label}</span>
                    <span className="ml-2 text-xs text-muted">{d.description}</span>
                  </div>
                  <div className="text-xs tabular-nums text-muted">
                    weight {w}%{wn !== null && wn !== w ? ` → ${wn}% of what's present` : ""}
                    {" · "}{d.features_scored}/{d.features_total} features
                    {" · "}domain score <b className="text-white">{d.score === null ? "—" : fmt(d.score)}</b>
                    {d.penalized && <span className="ml-2 rounded bg-rose-500/10 px-1.5 py-0.5 text-rose-300">required domain with no data → floored</span>}
                    {d.score === null && !d.penalized && <span className="ml-2">(no data → weight redistributed)</span>}
                  </div>
                </div>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs uppercase text-muted">
                      <tr>
                        <th className="py-1 pr-3">Feature</th>
                        <th className="pr-3">Raw figures</th>
                        <th className="pr-3">Calculation</th>
                        <th className="pr-3 text-right">Percentile</th>
                        <th className="pr-3 text-right">Weight</th>
                        <th className="text-right">Points</th>
                      </tr>
                    </thead>
                    <tbody>{rows.map((f) => <FeatureRow key={f.feature} f={f} />)}</tbody>
                  </table>
                </div>
              </div>
            );
          })}

          {/* composite */}
          <div className="mt-6">
            <div className="font-semibold text-white">Composite</div>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted">
                  <tr>
                    <th className="py-1 pr-3">Domain</th>
                    <th className="pr-3 text-right">Weight</th>
                    <th className="pr-3 text-right">Renormalized</th>
                    <th className="pr-3 text-right">Domain score</th>
                    <th className="text-right">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {ex.domains.map((d) => (
                    <tr key={d.domain} className={`border-t border-edge ${d.score === null ? "text-muted" : ""}`}>
                      <td className="py-2 pr-3">{d.label}{d.required ? <span className="ml-1 text-xs text-muted">(required)</span> : null}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{Math.round(d.weight * 100)}%</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{d.weight_renormalized === null ? "—" : `${(d.weight_renormalized * 100).toFixed(1)}%`}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{d.score === null ? "no data" : d.penalized ? `${fmt(d.score)} (floored)` : fmt(d.score)}</td>
                      <td className="py-2 text-right tabular-nums text-white">{d.contribution === null ? "—" : `+${fmt(d.contribution)}`}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-edge font-semibold text-white">
                    <td className="py-2 pr-3" colSpan={4}>Raw score = Σ points</td>
                    <td className="py-2 text-right tabular-nums">{fmt(ex.gate.raw_score)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* gate */}
          <div className="mt-6">
            <div className="font-semibold text-white">Gate — hard disqualifiers</div>
            <p className="mt-1 text-xs text-muted">Each rule is checked against the figures shown; missing data never trips a rule. The strictest tripped rule sets the ceiling.</p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted">
                  <tr>
                    <th className="py-1 pr-3">Rule</th>
                    <th className="pr-3">Evidence</th>
                    <th className="pr-3">If tripped</th>
                    <th className="text-right">Result</th>
                  </tr>
                </thead>
                <tbody>{ex.gate.rules.map((g) => <GateRow key={g.rule} g={g} />)}</tbody>
                <tfoot>
                  <tr className="border-t border-edge font-semibold text-white">
                    <td className="py-2 pr-3" colSpan={3}>
                      {ex.gate.cap === null
                        ? "No rule tripped → final score = raw score"
                        : `Ceiling ${fmt(ex.gate.cap)} → final score = min(${fmt(ex.gate.raw_score)}, ${fmt(ex.gate.cap)})`}
                    </td>
                    <td className="py-2 text-right tabular-nums">{fmt(ex.gate.final_score)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* tier */}
          <div className="mt-6">
            <div className="font-semibold text-white">Tier</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {ex.tier.thresholds.map((t) => (
                <span key={t.label}
                      className={`pill border ${t.label === ex.tier.tier ? tierColor(t.label) : "border-edge text-muted"}`}>
                  {t.label} <span className="ml-1 opacity-70">≥ {t.min}</span>
                </span>
              ))}
            </div>
            <div className="mt-2 text-xs text-muted">
              {fmt(ex.gate.final_score)} → <span className="text-white">{ex.tier.tier}</span>
              {ex.tier.stability !== null ? ` · ${Math.round(ex.tier.stability)}% of ±20% weight perturbations keep this tier` : ""}
              {` · coverage ${ex.tier.coverage.present}/${ex.tier.coverage.total} of this class's features`}
              {ex.tier.coverage.pct !== null ? ` (${Math.round(ex.tier.coverage.pct)}%)` : ""}
              {` · ${ex.tier.confidence} confidence`}
            </div>
          </div>
        </div>
      )}

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
