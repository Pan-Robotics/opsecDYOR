"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { accountUrl, loginUrl, signOut, useAccount } from "@/lib/account";

// Sign-in control for the header. Anonymous: a link to the hosted wallet login
// that returns here. Signed in: the handle with a small menu (account, sign out).
export default function UserMenu() {
  const { loading, user, setUser } = useAccount();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (loading) return <span className="inline-block h-8 w-16 rounded-lg bg-panel2/40" aria-hidden />;

  if (!user) {
    return (
      <a
        href={loginUrl("/")}
        onClick={(e) => { e.preventDefault(); window.location.assign(loginUrl(window.location.href)); }}
        className="inline-flex min-h-[2rem] items-center rounded-lg border border-brand/40 px-3 text-xs font-semibold text-brand hover:bg-brand/10"
      >
        Sign in
      </a>
    );
  }

  const label = user.display_name || `@${user.handle}`;
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex min-h-[2rem] max-w-[11rem] items-center gap-2 rounded-lg border border-edge bg-panel2 px-3 text-xs text-white hover:border-brand/50"
      >
        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand to-brand2 text-[10px] font-bold text-[#04101b]">
          {user.handle.replace(/^wallet-/, "").slice(0, 1).toUpperCase()}
        </span>
        <span className="truncate">{label}</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-56 overflow-hidden rounded-lg border border-edge bg-panel shadow-xl">
          <div className="border-b border-edge px-3 py-2 text-xs text-muted">
            <div className="truncate text-white">@{user.handle}</div>
            <div>{user.plan === "free" ? "Free plan" : `${user.plan} plan`}, {user.wallets} wallet{user.wallets === 1 ? "" : "s"}</div>
            {user.waitlist && !user.waitlist.activated_at && <div className="text-emerald-300">On the {user.waitlist.tier} waitlist</div>}
          </div>
          {/* the account page gets the page we are on, so its header can lead straight back here */}
          <a role="menuitem" href={accountUrl}
            onClick={(e) => { e.preventDefault(); window.location.assign(`${accountUrl}?return_to=${encodeURIComponent(window.location.href)}`); }}
            className="block px-3 py-2 text-sm text-white hover:bg-panel2">Account</a>
          <Link role="menuitem" href="/pricing" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-white hover:bg-panel2">Plans and waitlist</Link>
          <button
            role="menuitem"
            type="button"
            onClick={async () => { await signOut(); setUser(null); setOpen(false); }}
            className="block w-full px-3 py-2 text-left text-sm text-white hover:bg-panel2"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
