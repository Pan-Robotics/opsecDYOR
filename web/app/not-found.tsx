import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found", robots: { index: false, follow: true } };

export default function NotFound() {
  return (
    <div className="card space-y-3">
      <h1 className="text-2xl font-bold text-white">That page doesn&apos;t exist</h1>
      <p className="text-muted">Looking for a token? Search it by name, symbol or contract address, or browse every scored token.</p>
      <div className="flex flex-wrap gap-3">
        <Link href="/analyze" className="btn">Analyze a token</Link>
        <Link href="/tokens" className="btn-ghost">All scored tokens</Link>
        <Link href="/" className="btn-ghost !text-muted hover:!text-white">Home</Link>
      </div>
    </div>
  );
}
