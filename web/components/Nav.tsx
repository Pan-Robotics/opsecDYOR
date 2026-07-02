"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: [string, string][] = [
  ["/", "Home"],
  ["/analyze", "Analyze"],
  ["/screener", "Screener"],
  ["/tools", "Tools"],
  ["/narratives", "Narratives"],
  ["/methodology", "Methodology"],
  ["/api-mcp", "API & MCP"],
];

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.cryptoopsec.com";

export default function Nav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b border-brand/20 bg-panel/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        {/* back to the main CryptoOpsec site */}
        <a
          href={SITE_URL}
          className="flex items-center gap-1 text-xs text-muted transition hover:text-brand"
          title="Back to CryptoOpsec"
        >
          <span aria-hidden>←</span>
          <span className="font-orbitron font-bold tracking-tight text-brand">CryptoOpsec</span>
        </a>

        <span className="hidden text-edge sm:inline">/</span>

        <Link href="/" className="flex items-center gap-2 font-orbitron font-bold tracking-tight text-white">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-brand to-brand2 text-[#04101b]">
            🧭
          </span>
          DYOR
        </Link>

        <nav className="flex flex-wrap gap-1 text-sm">
          {LINKS.map(([href, label]) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-1.5 transition ${
                  active ? "bg-panel2 text-brand" : "text-muted hover:text-white"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
