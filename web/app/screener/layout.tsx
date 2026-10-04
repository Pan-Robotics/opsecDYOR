import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'Crypto token screener by tier — scored universe, filters, gate flags',
  description: "A weekly-refreshed universe of tokens scored 0–100 and grouped into tiers A–D. Filter by asset class, minimum tier, real yield and gate flags; open any token's full analysis.",
  path: '/screener',
});

export default function ScreenerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
