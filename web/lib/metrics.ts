// The things a reader can rank or filter the board by: the composite, each
// domain, and each scored feature. Mirrors dyor/app/copy.py FEATURE_META and
// dyor/explain.py FEATURE_UNIT; keep the three in step when a feature changes.
export type MetricKind = "score" | "domain" | "feature";
export type Metric = {
  key: string;            // "final_score" | domain name | feature name
  kind: MetricKind;
  label: string;
  higherIsBetter: boolean;
  unit?: "x" | "ratio" | "count" | "per_day" | "score";
  domain?: string;        // for features: the domain they belong to
  blurb: string;
};

export const DOMAIN_LABELS: Record<string, string> = {
  fundamental: "Fundamentals", tokenomics: "Tokenomics", onchain: "On-chain", social: "Social", dev: "Developers",
};

export const METRICS: Metric[] = [
  { key: "final_score", kind: "score", label: "Final score", higherIsBetter: true, unit: "score", blurb: "The composite, 0 to 100, after the gate." },
  { key: "fundamental", kind: "domain", label: "Fundamentals", higherIsBetter: true, unit: "score", blurb: "Valuation against real cash flow: P/F, P/S, MC/TVL, real yield." },
  { key: "tokenomics", kind: "domain", label: "Tokenomics", higherIsBetter: true, unit: "score", blurb: "Supply structure: dilution, float, unlocks, value accrual." },
  { key: "onchain", kind: "domain", label: "On-chain", higherIsBetter: true, unit: "score", blurb: "Usage and distribution: address growth, holder concentration." },
  { key: "social", kind: "domain", label: "Social", higherIsBetter: true, unit: "score", blurb: "Attention: community votes, watchlists, social trend." },
  { key: "dev", kind: "domain", label: "Developers", higherIsBetter: true, unit: "score", blurb: "Sustained developer activity." },
  { key: "real_yield", kind: "feature", domain: "fundamental", label: "Real yield", higherIsBetter: true, unit: "ratio", blurb: "Holders revenue over market cap, annualized." },
  { key: "price_to_fees", kind: "feature", domain: "fundamental", label: "Price / fees", higherIsBetter: false, unit: "x", blurb: "Market cap over annualized fees. Lower is cheaper." },
  { key: "price_to_sales", kind: "feature", domain: "fundamental", label: "Price / sales", higherIsBetter: false, unit: "x", blurb: "Market cap over annualized revenue the protocol keeps." },
  { key: "mc_tvl", kind: "feature", domain: "fundamental", label: "MC / TVL", higherIsBetter: false, unit: "x", blurb: "Market cap over total value locked." },
  { key: "value_accrual", kind: "feature", domain: "tokenomics", label: "Token sink", higherIsBetter: true, unit: "ratio", blurb: "Share of revenue routed to holders." },
  { key: "fdv_mcap_ratio", kind: "feature", domain: "tokenomics", label: "FDV / MCAP", higherIsBetter: false, unit: "x", blurb: "Fully diluted over circulating value. High means dilution ahead." },
  { key: "float_ratio", kind: "feature", domain: "tokenomics", label: "Float", higherIsBetter: true, unit: "ratio", blurb: "Circulating over total supply." },
  { key: "unlock_overhang", kind: "feature", domain: "tokenomics", label: "Unlock overhang", higherIsBetter: false, unit: "ratio", blurb: "Share of max supply still vesting." },
  { key: "top10_concentration", kind: "feature", domain: "onchain", label: "Top-10 holders", higherIsBetter: false, unit: "ratio", blurb: "Supply held by the ten largest wallets." },
  { key: "address_growth", kind: "feature", domain: "onchain", label: "Address growth", higherIsBetter: true, unit: "ratio", blurb: "Daily active addresses, last 30-day mean vs first 30-day mean of a 90-day window." },
  { key: "social_sentiment", kind: "feature", domain: "social", label: "Sentiment", higherIsBetter: true, unit: "ratio", blurb: "CoinGecko community up-vote share." },
  { key: "watchlist_users", kind: "feature", domain: "social", label: "Watchlists", higherIsBetter: true, unit: "count", blurb: "CoinGecko users tracking the token." },
  { key: "social_trend", kind: "feature", domain: "social", label: "Social trend", higherIsBetter: true, unit: "ratio", blurb: "Trend in social volume (needs a Santiment key)." },
  { key: "dev_activity", kind: "feature", domain: "dev", label: "Dev activity", higherIsBetter: true, unit: "per_day", blurb: "Developer-activity events per day over 90 days." },
];

export const metricByKey = (key: string) => METRICS.find((m) => m.key === key);

export function fmtMetric(v: number | null | undefined, unit: Metric["unit"]): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  switch (unit) {
    case "score": return v.toFixed(1);
    case "x": return `${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)}x`;
    case "ratio": return `${(v * 100).toFixed(1)}%`;
    case "per_day": return `${v.toFixed(1)}/day`;
    case "count": return v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v.toLocaleString();
    default: return String(v);
  }
}
