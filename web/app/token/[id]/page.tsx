import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { serverApi } from "@/lib/api";
import { SITE, abs, breadcrumbJsonLd, jsonLd, snippet, tierLetter } from "@/lib/seo";
import TokenReport from "@/components/TokenReport";
import TokenLink from "@/components/TokenLink";

// Permanent, server-rendered page per token on the board: the full report in
// HTML (a crawler sees the ledger), regenerated hourly, with its own title,
// description, canonical and Open Graph image. Unknown ids fall through to a
// live analysis instead of a dead end.
export const revalidate = 3600;
export const dynamicParams = true;
export async function generateStaticParams() {
  return [];
}

const ID_OK = /^[a-z0-9][a-z0-9-]{0,99}$/;

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const a = ID_OK.test(id) ? await serverApi.token(id) : null;
  if (!a || !a.resolved || !a.score) {
    return { title: "Token", robots: { index: false, follow: true } };
  }
  const r = a.resolved;
  const s = a.score;
  const title = `${r.name} (${r.symbol}) score ${s.final_score}/100, tier ${s.tier} | ${SITE.fullName}`;
  const description = snippet(a.summary ?? `${r.name} scored ${s.final_score}/100 (tier ${tierLetter(s.tier)}) by DYOR on fundamentals, tokenomics, on-chain usage, social and developer activity.`);
  const path = `/token/${encodeURIComponent(id)}`;
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: path },
    openGraph: { type: "article", url: path, siteName: SITE.fullName, title, description,
                 modifiedTime: a.source?.collected_at ?? undefined },
    twitter: { card: "summary_large_image", title, description, ...(SITE.twitter ? { site: SITE.twitter } : {}) },
  };
}

export default async function TokenPage({ params }: Props) {
  const { id } = await params;
  const a = ID_OK.test(id) ? await serverApi.token(id) : null;
  if (!a || !a.resolved || !a.score) {
    // Not on the board (or the board is empty): a live analysis is the right page.
    redirect(`/analyze?q=${encodeURIComponent(id)}`);
  }
  const r = a.resolved;
  const s = a.score;
  const cls = a.record.class;
  const path = `/token/${encodeURIComponent(id)}`;
  const peers = (a.peers ?? []).filter((p) => p.token !== id).slice(0, 8);
  const webPage = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "@id": `${abs(path)}#webpage`,
    url: abs(path),
    name: `${r.name} (${r.symbol}): DYOR score and tier`,
    description: snippet(a.summary ?? "", 300),
    isPartOf: { "@id": `${SITE.url}/#website` },
    dateModified: a.source?.collected_at ?? undefined,
    about: { "@type": "Thing", name: `${r.name} (${r.symbol})`, sameAs: r.coingecko_url },
    inLanguage: "en",
  };

  return (
    <div className="space-y-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(breadcrumbJsonLd([
        { name: "Home", path: "/" }, { name: "Tokens", path: "/tokens" }, { name: `${r.name} (${r.symbol})`, path },
      ])) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(webPage) }} />

      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <ol className="flex flex-wrap items-center gap-1">
          <li><Link href="/" className="hover:text-white">Home</Link></li>
          <li aria-hidden>›</li>
          <li><Link href="/tokens" className="hover:text-white">Tokens</Link></li>
          <li aria-hidden>›</li>
          <li className="text-white">{r.name} ({r.symbol})</li>
        </ol>
      </nav>

      <TokenReport a={a} headingTag="h1" permalink={false} />

      {a.summary && (
        <section className="card">
          <h2 className="font-semibold text-white">In one paragraph</h2>
          <p className="mt-2 text-sm text-muted">{a.summary}</p>
        </section>
      )}

      <section className="card">
        <h2 className="font-semibold text-white">About this page</h2>
        <p className="mt-2 text-sm text-muted">
          This is {r.name}&apos;s permanent DYOR page, scored from the board run of{" "}
          <span className="text-white">{a.source?.collected_at ? a.source.collected_at.slice(0, 10) : "n/a"}</span>
          {" "}against {a.peer_count} other {cls?.label ?? "same-class"} tokens. Scores are 0 to 100; the tier maps
          A at 80 or above, B at 60, C at 40, D below. Every figure above shows its raw inputs, formula, percentile and weight;
          see the <Link href="/methodology" className="text-brand hover:text-brand2">methodology</Link> for how the
          classes, gates and weights work. For today&apos;s numbers,{" "}
          <Link href={`/analyze?q=${encodeURIComponent(id)}`} className="text-brand hover:text-brand2">run a live analysis</Link>.
          Research aid, not financial advice.
        </p>
        {peers.length > 0 && (
          <div className="mt-3 text-sm text-muted">
            Other {cls?.label ?? "same-class"} tokens on the board:{" "}
            {peers.map((p, i) => (
              <span key={p.token}>{i > 0 ? ", " : ""}<TokenLink token={p.token} /> ({p.final_score}/100)</span>
            ))}
            {". "}<Link href="/tokens" className="text-brand hover:text-brand2">All scored tokens</Link>
          </div>
        )}
      </section>
    </div>
  );
}
