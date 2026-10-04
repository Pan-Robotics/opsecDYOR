import Link from "next/link";
import { fmt, ScoreBar, TierBadge } from "./ui";

/**
 * One token as a stacked row for narrow screens: name and class on top, the
 * score bar underneath, the tier letter on the right. The screener and the
 * token index render this under `md:hidden` and keep their tables for wider
 * screens, where the columns have room.
 */
export function MobileTokenRow({
  rank, id, name, symbol, classLabel, score, tier, coverage, flags, extra, select, muted = false,
}: {
  rank: number; id: string; name: string; symbol?: string | null; classLabel?: string | null;
  score: number | null; tier: string; coverage?: number | null; flags?: string[];
  extra?: React.ReactNode;     // e.g. the ranked metric's value
  select?: React.ReactNode;    // e.g. a compare checkbox
  muted?: boolean;
}) {
  return (
    <li className={`flex items-start gap-3 border-b border-edge/60 px-3 py-3 last:border-0 ${muted ? "text-muted" : ""}`}>
      {select && <div className="mt-1 shrink-0">{select}</div>}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="w-6 shrink-0 text-xs tabular-nums text-muted">{rank}</span>
          <Link href={`/token/${encodeURIComponent(id)}`} className="truncate font-medium text-white hover:text-brand">{name}</Link>
          {symbol && <span className="shrink-0 text-xs text-muted">{symbol}</span>}
        </div>
        <div className="mt-0.5 pl-8 text-xs text-muted">
          {classLabel}
          {coverage !== undefined && coverage !== null ? `, ${Math.round(coverage)}% coverage` : ""}
        </div>
        <div className="mt-1.5 flex items-center gap-2 pl-8">
          <div className="flex-1"><ScoreBar value={score} /></div>
          <span className="w-10 text-right text-sm tabular-nums text-white">{fmt(score)}</span>
        </div>
        {extra && <div className="mt-1 pl-8 text-xs">{extra}</div>}
        {flags && flags.length > 0 && <div className="mt-1 pl-8 text-xs text-rose-300">{flags.join(", ")}</div>}
      </div>
      <div className="shrink-0 pt-0.5"><TierBadge tier={tier} compact /></div>
    </li>
  );
}
