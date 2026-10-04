import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'Analyze a crypto token: score, tier, gates and the full working',
  description: 'Search any token by name, symbol or contract address. DYOR resolves it across chains and scores it 0 to 100 against same-class peers: fundamentals, tokenomics, on-chain usage, social and developer activity, with every raw figure and formula shown.',
  path: '/analyze',
});

export default function AnalyzeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
