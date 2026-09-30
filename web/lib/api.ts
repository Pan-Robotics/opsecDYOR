const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8077";

export type Score = {
  token: string;
  raw_score: number | null;
  final_score: number | null;
  tier: string;
  coverage: number | null;
  features_present: number;
  features_total: number;
  tier_stability?: number | null;
  scale?: number;               // 100 — every score / domain score / coverage is 0–100
  confidence?: string;
  flags: string[];
  advisories: string[];
  domain_scores: Record<string, number | null>;
  class?: ClassInfo;
  market?: Market;
};

export type ClassInfo = {
  name: string;
  label: string;
  description: string;
  domains: string[];
  weights?: Record<string, number>;   // this class's domain weights (fractions)
  required_domains: string[];
};

export type Market = {
  price: number | null;
  market_cap: number | null;
  fdv: number | null;
  volume_24h: number | null;
  circulating_supply: number | null;
  total_supply: number | null;
  ath_change_pct: number | null;
  price_change_24h_pct: number | null;
} | null;

export type Resolved = {
  name: string;
  symbol: string;
  gecko_id: string;
  matched_by: string;
  market_cap_rank: number | null;
  chains: string[];
  platforms: Record<string, string>;
  explorers: Record<string, string>;
  coingecko_url: string;
  links: {
    homepage?: string | null; github?: string | null; twitter?: string | null;
    reddit?: string | null; telegram?: string | null; discord?: string | null;
    whitepaper?: string | null; explorers?: string[];
  };
};

export type RecordData = {
  features: Record<string, number>;
  market: Market;
  categories: string[] | null;
  feeds: Record<string, string> | null;
  sources?: Record<string, string | null> | null;   // feed → that source's page for this token
  stale?: Record<string, string | null> | null;     // feed → date of the stored values carried forward
  github_account?: string | null;
  contract_verified: boolean | null;
  audited: boolean | null;
  vc: { num_backers: number | null; had_public_sale: boolean | null };
  class: ClassInfo;
};

// --- the working behind the score (dyor/explain.py) ---------------------------
export type ExplainInput = {
  key: string; label: string; value: number | boolean | number[] | string | null;
  unit: string; source: string;
};
export type ExplainFeature = {
  feature: string; label: string; meaning: string; domain: string; direction: string;
  source: string | null; feed_status: string | null;
  inputs: ExplainInput[]; formula: string | null;
  value: number | null; unit: string | null;
  percentile: number | null; reference_n: number | null;
  weight: number | null; contribution: number | null;
  status: "scored" | "missing"; missing_reason: string | null;
};
export type ExplainDomain = {
  domain: string; label: string; description: string;
  weight: number; weight_renormalized: number | null;
  features_total: number; features_scored: number;
  score: number | null; penalized: boolean; required: boolean; contribution: number | null;
};
export type ExplainGateRule = {
  rule: string; action: string; cap: number | null; active_on_open_data: boolean; tripped: boolean;
  evidence: { label: string; value: number | boolean | string | null; unit: string; threshold: string | null }[];
};
export type Explain = {
  method: { class: string; class_label: string; normalization: string; reference_anchored: boolean;
            penalize_missing_core: boolean; missing_core_penalty: number | null; scale: number };
  features: ExplainFeature[];
  domains: ExplainDomain[];
  gate: { rules: ExplainGateRule[]; flags: string[]; cap: number | null; raw_score: number | null; final_score: number | null };
  tier: { tier: string; thresholds: { label: string; min: number }[]; stability: number | null;
          confidence: string; coverage: { present: number; total: number; pct: number | null } };
};

export type Analysis = {
  query: string;
  scale?: number;
  summary?: string | null;
  resolved: Resolved | null;
  score: Score | null;
  record: RecordData;
  explain?: Explain | null;
  peer_count: number;
  rank: number | null;
  peers: Score[];
  errors: { token: string; source: string; error: string }[];
  ok: boolean;
};

export type GateRule = { action: string; cap?: number; threshold?: number; active_on_open_data: boolean };

export type Methodology = {
  scale?: number;               // 100 — tier thresholds and gate caps are 0–100
  weights: Record<string, number>;
  weights_note?: string;
  class_weights?: Record<string, Record<string, number>>;
  tiers: { label: string; min: number; color: string }[];
  gating: Record<string, GateRule>;
  reference: { treasury_10y_yield_pct: number; reference_date: string };
  domains: Record<string, { label: string; description: string }>;
  glossary: { key: string; label: string; meaning: string; direction: string }[];
  break_thesis: string[];
  classes: ClassInfo[];
  class_labels: Record<string, { label: string; description: string }>;
};

async function req<T>(path: string, method = "GET"): Promise<T> {
  const r = await fetch(`${API}${path}`, { method, cache: "no-store" });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}
const get = <T>(p: string) => req<T>(p, "GET");

function penaltyParam(p?: boolean) {
  return p === undefined ? "" : `&penalize_missing_core=${p}`;
}

export const api = {
  analyze: (q: string, peerMode = "stored", penalizeMissingCore?: boolean) =>
    get<Analysis>(
      `/api/analyze?q=${encodeURIComponent(q)}&peer_mode=${peerMode}${penaltyParam(penalizeMissingCore)}`),
  screener: (source = "sample", peerGroups = false, penalizeMissingCore?: boolean) =>
    get<{ source: string; count: number; results: Score[] }>(
      `/api/screener?source=${source}&peer_groups=${peerGroups}${penaltyParam(penalizeMissingCore)}`),
  narratives: (by = "market_cap_change_24h") =>
    get<{ by: string; rows: any[] }>(`/api/narratives?by=${by}`),
  methodology: () => get<Methodology>(`/api/methodology`),
  memo: (q: string, peerMode = "class") =>
    get<{ query: string; memo: string }>(`/api/memo?q=${encodeURIComponent(q)}&peer_mode=${peerMode}`),
  screenFilter: (params: Record<string, string>) =>
    get<{ matched: number; universe: number; results: ScreenRow[] }>(
      `/api/screen?${new URLSearchParams(params).toString()}`),
  portfolio: (tokens: string, peerMode = "class") =>
    get<PortfolioResult>(`/api/portfolio?tokens=${encodeURIComponent(tokens)}&peer_mode=${peerMode}`),
  barbell: (n = 5) => get<BarbellResult>(`/api/barbell?n=${n}`),
  backtest: () => get<BacktestResult>(`/api/backtest`),
  chart: (id: string, days = 30) =>
    get<ChartData>(`/api/chart?id=${encodeURIComponent(id)}&days=${days}`),
  openapi: () => get<OpenApiSchema>(`/openapi.json`),
};

export type OpenApiParam = {
  name: string; in: string; required?: boolean;
  schema?: { default?: unknown; type?: string };
};
export type OpenApiOp = { summary?: string; description?: string; parameters?: OpenApiParam[] };
export type OpenApiSchema = { paths: Record<string, Record<string, OpenApiOp>> };

export type ChartData = {
  id: string; days: number; prices: [number, number][];
  first: number | null; last: number | null; change_pct: number | null;
};

export type ScreenRow = {
  token: string; class: string | null; score: number | null; tier: string;
  coverage: number | null; confidence: string; flags: string[];
};
export type PortfolioResult = {
  holdings: { token?: string; name?: string; symbol?: string; class?: string;
    score?: number | null; tier?: string | null; flags?: string[]; query?: string; error?: string }[];
  scored: number; tier_distribution: Record<string, number>;
  class_exposure: Record<string, number>; avg_score: number | null;
  flagged: string[]; notes: string[];
};
export type BarbellResult = {
  anchor: { token: string; tier: string | null; score: number | null };
  satellites: { token: string; class: string | null; score: number; tier: string }[];
  rationale: string;
};
export type BacktestResult = {
  samples: number; tokens?: number; note: string;
  by_tier?: Record<string, { n: number; avg_return: number; win_rate: number }>;
};
