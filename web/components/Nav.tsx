"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { useStickyValue } from "./AppState";
import UserMenu from "./UserMenu";

const LINKS: [string, string][] = [
  ["/", "Home"],
  ["/analyze", "Analyze"],
  ["/screener", "Screener"],
  ["/tokens", "Tokens"],
  ["/compare", "Compare"],
  ["/tools", "Tools"],
  ["/narratives", "Narratives"],
  ["/methodology", "Methodology"],
  ["/api-mcp", "API & MCP"],
];

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.cryptoopsec.com";

// One header for every width: brand row, then a single-line tab strip that
// scrolls sideways on narrow screens (the active tab is kept in view) and sits
// inline beside the brand from the md breakpoint up. Two short rows on a phone
// instead of three wrapped ones, so the sticky header leaves room for the page.
export default function Nav() {
  const path = usePathname();
  const strip = useRef<HTMLElement>(null);
  // The Compare tab returns to the set being compared in this tab, not to an empty page.
  const compareIds = useStickyValue<string[]>("compare:ids", []);
  const hrefFor = (base: string) =>
    base === "/compare" && compareIds.length ? `/compare?tokens=${encodeURIComponent(compareIds.join(","))}` : base;
  const isActive = (base: string) => path === base || (base !== "/" && path.startsWith(base + "/"));

  useEffect(() => {
    const nav = strip.current;
    const el = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !el || nav.scrollWidth <= nav.clientWidth) return;
    const left = el.offsetLeft - (nav.clientWidth - el.offsetWidth) / 2;
    nav.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  }, [path]);

  return (
    <header className="sticky top-0 z-20 border-b border-brand/20 bg-panel/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-1 px-4 pt-2 md:py-3">
        <Link href="/" className="flex items-center gap-2 font-orbitron font-bold tracking-tight text-white">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-brand to-brand2 text-[#04101b]">
            🧭
          </span>
          DYOR
        </Link>

        {/* back to the main CryptoOpsec site */}
        <a
          href={SITE_URL}
          className="ml-auto flex items-center gap-1 text-xs text-muted transition hover:text-brand md:order-first md:ml-0"
          title="Back to CryptoOpsec"
        >
          <span aria-hidden>←</span>
          <span className="font-orbitron font-bold tracking-tight text-brand">CryptoOpsec</span>
        </a>
        <span className="hidden text-edge md:order-first md:inline">/</span>

        {/* CryptoOpsec account: sign in, or the handle with account and sign-out */}
        <div className="md:order-last"><UserMenu /></div>

        <nav
          ref={strip}
          aria-label="Primary"
          className="no-scrollbar -mx-4 flex w-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 py-1.5 pr-10 text-sm [mask-image:linear-gradient(to_right,transparent,black_1rem,black_calc(100%-2.5rem),transparent)] md:order-2 md:mx-0 md:w-auto md:min-w-0 md:flex-1 md:px-0 md:py-0 md:[mask-image:none]"
        >
          {LINKS.map(([base, label]) => {
            const active = isActive(base);
            return (
              <Link
                key={base}
                href={hrefFor(base)}
                aria-current={active ? "page" : undefined}
                className={`shrink-0 rounded-lg px-3 py-1.5 whitespace-nowrap transition ${
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
