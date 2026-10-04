import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'Crypto token screener: rank by score, domain or metric, filter, compare',
  description: "Rank every token on the DYOR board by composite score, by a single domain such as tokenomics or fundamentals, or by one metric such as real yield or holder concentration, best or worst first. Filter by asset class, tier, gate flags and data coverage, and compare picks line for line.",
  path: '/screener',
});

export default function ScreenerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
