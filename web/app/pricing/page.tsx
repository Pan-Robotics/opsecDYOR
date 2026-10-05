import type { Metadata } from "next";
import Link from "next/link";
import Pricing from "@/components/Pricing";
import { breadcrumbJsonLd, faqJsonLd, jsonLd, pageMeta } from "@/lib/seo";

// The plans page: the same table as the home page, with the questions a person
// has before joining the waitlist. Server-rendered copy, client-side waitlist.
export const metadata: Metadata = pageMeta({
  title: "Plans and waitlist: free research, paid API, MCP and tools",
  description: "DYOR's analyzer, screener, compare view and token pages are free for everyone. Pro, Business and Enterprise tiers add API keys, the hosted MCP server at scale, the Tools page, deeper data and alerts. Join the waitlist and your tier is switched on at launch.",
  path: "/pricing",
});

const FAQ = [
  { q: "Is DYOR still free?",
    a: "Yes. The analyzer, screener, compare view and every token page are free, need no account, and stay that way. Until the paid tiers launch, everything else on the site is free as well." },
  { q: "What do the paid tiers add?",
    a: "The pipes and the depth rather than a different score: API keys with a monthly quota, keyed access to the hosted MCP server for AI agents, the Tools page (portfolio scorer, barbell builder, backtest), deeper data panels such as the unlock calendar and developer and social series, and alerts. Business adds seats and team routing; Enterprise is a custom quota with an SLA." },
  { q: "Does paying change my scores?",
    a: "No. One scoring model runs for everyone and the paid upstream data feeds it for everyone. A free visitor and a paying subscriber see the same number for the same token; subscriptions fund the data and buy access to more of it." },
  { q: "What happens when I join the waitlist?",
    a: "The tier you chose is recorded on your CryptoOpsec account, together with any contact you gave for the launch notice. On launch day the plan is switched on for that account. Nothing is charged until you decide to pay, and you can change or leave the request from the account page at any time." },
  { q: "How will I pay at launch?",
    a: "With the wallet you sign in with, in stablecoins, or by card for teams that need invoices. Pricing is announced at launch; waitlist members hear first." },
  { q: "Why join now rather than at launch?",
    a: "Demand decides what gets built and bought first: which data sources, which tools, how large the quotas are. A waitlist entry is a vote, and it costs nothing." },
];

export default function PricingPage() {
  return (
    <div className="space-y-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(faqJsonLd(FAQ)) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(breadcrumbJsonLd([
        { name: "Home", path: "/" }, { name: "Plans", path: "/pricing" },
      ])) }} />
      <Pricing heading="h1" />
      <section>
        <h2 className="mb-3 font-semibold text-white">Questions</h2>
        <div className="space-y-3">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="card group">
              <summary className="cursor-pointer font-medium text-white">{q}</summary>
              <p className="mt-2 text-sm text-muted">{a}</p>
            </details>
          ))}
        </div>
        <p className="mt-4 text-sm text-muted">
          Meanwhile: <Link href="/analyze" className="text-brand hover:text-brand2">analyze a token</Link>,{" "}
          <Link href="/screener" className="text-brand hover:text-brand2">open the screener</Link> or{" "}
          <Link href="/api-mcp" className="text-brand hover:text-brand2">read the API and MCP docs</Link>.
        </p>
      </section>
    </div>
  );
}
