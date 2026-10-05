// The planned plans, one place for the home page table and the pricing page.
// Nothing here is live: everything is free until the tiers launch, and the
// waitlist records which tier a person wants so it can be switched on then.
export type TierId = "free" | "pro" | "business" | "enterprise";

export type Tier = { id: TierId; name: string; price: string; tagline: string; audience: string; paid: boolean };

export const TIERS: Tier[] = [
  { id: "free", name: "Free", price: "$0", tagline: "The research, open to everyone", audience: "Anyone doing their own research", paid: false },
  { id: "pro", name: "Pro", price: "$8.99 a month", tagline: "The pipes: keys, agents, tools", audience: "Analysts and agent builders", paid: true },
  { id: "business", name: "Business", price: "$49.99 a month", tagline: "Pro for a team", audience: "Funds, research desks, trading teams", paid: true },
  { id: "enterprise", name: "Enterprise", price: "Custom", tagline: "Your quota, your terms", audience: "Platforms and data buyers", paid: true },
];

export const PAID_TIERS = TIERS.filter((t) => t.paid);
export const tierById = (id: string) => TIERS.find((t) => t.id === id);

// true: included; false: not included; string: the allowance or the shape it takes.
export type Row = { label: string; hint?: string; values: Record<TierId, string | boolean> };

export const ROWS: Row[] = [
  { label: "Analyzer, screener, compare, token pages", hint: "The score is the same for everyone; no account needed",
    values: { free: true, pro: true, business: true, enterprise: true } },
  { label: "Live analyses per day", hint: "Fresh pulls from the sources, on top of the weekly board",
    values: { free: "20", pro: "200", business: "2,000", enterprise: "Custom" } },
  { label: "Tools: portfolio scorer, barbell builder, backtest",
    values: { free: "Preview", pro: true, business: true, enterprise: true } },
  { label: "REST API keys", hint: "Scores, tiers, percentiles and derived metrics, documented on the API page",
    values: { free: "Public endpoints, fair use", pro: "1 key, 10,000 calls a month", business: "5 keys, 100,000 calls a month", enterprise: "Custom quota, SLA" } },
  { label: "Hosted MCP server for AI agents", hint: "Claude, Cursor and other agents call DYOR as tools",
    values: { free: "50 calls a day", pro: "Keyed, shares the API quota", business: "Keyed, shares the API quota", enterprise: "Custom" } },
  { label: "Deeper data", hint: "Unlock calendar, developer and social series, derivatives positioning later",
    values: { free: "Locked preview", pro: true, business: true, enterprise: true } },
  { label: "Alerts on tier changes and unlocks",
    values: { free: false, pro: "Telegram or webhook", business: "Team routing", enterprise: "Custom" } },
  { label: "Seats", values: { free: "1", pro: "1", business: "5", enterprise: "Custom" } },
  { label: "Support", values: { free: "Public channels", pro: "Priority", business: "Priority", enterprise: "Dedicated" } },
];
