"use client";
import { useEffect, useSyncExternalStore } from "react";

// The CryptoOpsec account behind the browser's shared session cookie. One POST
// to the accounts service answers "who is this" and silently renews the cookie.
export const ACCOUNTS_URL = (process.env.NEXT_PUBLIC_ACCOUNTS_URL ?? "https://accounts.cryptoopsec.com").replace(/\/$/, "");

export type WaitlistTier = "pro" | "business" | "enterprise";
export const WAITLIST_TIERS: WaitlistTier[] = ["pro", "business", "enterprise"];
export const isWaitlistTier = (v: unknown): v is WaitlistTier => typeof v === "string" && (WAITLIST_TIERS as string[]).includes(v);
export type ContactKind = "email" | "x" | "telegram";
export const CONTACT_KINDS: { id: ContactKind; label: string; placeholder: string; via: string }[] = [
  { id: "email", label: "Email", placeholder: "you@example.com", via: "by email to" },
  { id: "x", label: "X", placeholder: "@handle", via: "on X to" },
  { id: "telegram", label: "Telegram", placeholder: "@handle", via: "on Telegram to" },
];
export type Waitlist = { tier: WaitlistTier; contact_kind: ContactKind | null; contact: string | null; note: string | null; created_at: string; updated_at?: string; activated_at: string | null };
export type AccountUser = {
  id: string; handle: string; display_name: string | null; avatar_url: string | null;
  plan: string; plan_until?: string | null; features: string[]; wallets: number; waitlist: Waitlist | null;
};

export async function fetchSession(): Promise<AccountUser | null> {
  try {
    const r = await fetch(`${ACCOUNTS_URL}/auth/session`, { method: "POST", credentials: "include" });
    if (!r.ok) return null;
    const d = (await r.json()) as { user: AccountUser | null };
    return d.user;
  } catch {
    return null;
  }
}

export async function signOut(): Promise<void> {
  try { await fetch(`${ACCOUNTS_URL}/auth/logout`, { method: "POST", credentials: "include" }); } catch { /* cookie may already be gone */ }
}

// The paid-tier waitlist lives on the account: join or change the request, or leave it.
// A 401 means the session lapsed; the caller sends the person to sign in.
export async function joinWaitlist(tier: WaitlistTier, contactKind: ContactKind, contact: string, note: string): Promise<{ waitlist: Waitlist } | { error: string; status: number }> {
  const campaign = campaignTag();
  try {
    const r = await fetch(`${ACCOUNTS_URL}/me/waitlist`, {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier, contact_kind: contactKind, contact, note, source: window.location.hostname, campaign }),
    });
    const d = (await r.json().catch(() => ({}))) as { waitlist?: Waitlist; error?: string };
    if (!r.ok || !d.waitlist) return { error: d.error ?? `request failed (${r.status})`, status: r.status };
    return { waitlist: d.waitlist };
  } catch {
    return { error: "the accounts service could not be reached; try again in a moment", status: 0 };
  }
}

export async function leaveWaitlist(): Promise<boolean> {
  try {
    const r = await fetch(`${ACCOUNTS_URL}/me/waitlist`, { method: "DELETE", credentials: "include" });
    return r.ok;
  } catch { return false; }
}

export const loginUrl = (returnTo: string) => `${ACCOUNTS_URL}/login?return_to=${encodeURIComponent(returnTo)}`;
export const accountUrl = `${ACCOUNTS_URL}/account`;

// One session for the whole page: every component that calls useAccount() reads
// the same store, so a change made in one place (joining the waitlist from the
// plans table, signing out from the header) shows everywhere at once.
type SessionState = { loading: boolean; user: AccountUser | null };
const SERVER_STATE: SessionState = { loading: true, user: null };
let state: SessionState = SERVER_STATE;
const listeners = new Set<() => void>();
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
const emit = () => { for (const fn of listeners) fn(); };
let inflight: Promise<AccountUser | null> | null = null;

/** Re-ask the accounts service who this is; concurrent callers share one request. */
export function refreshSession(): Promise<AccountUser | null> {
  if (!inflight) {
    inflight = fetchSession().then((user) => { state = { loading: false, user }; emit(); return user; }).finally(() => { inflight = null; });
  }
  return inflight;
}

export function setSessionUser(user: AccountUser | null) {
  state = { loading: false, user };
  emit();
}

export function useAccount() {
  const s = useSyncExternalStore(subscribe, () => state, () => SERVER_STATE);
  useEffect(() => {
    if (state.loading) void refreshSession();
    const onFocus = () => { void refreshSession(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);
  return { ...s, refresh: refreshSession, setUser: setSessionUser };
}

// Campaign tag from the link that brought the visitor (utm_campaign, else utm_content).
// Kept in sessionStorage so it survives the wallet sign-in round trip.
const CAMPAIGN_KEY = "dyor:campaign";
export function captureCampaign(): void {
  try {
    const q = new URLSearchParams(window.location.search);
    const tag = q.get("utm_campaign") || q.get("utm_content");
    if (tag) sessionStorage.setItem(CAMPAIGN_KEY, tag);
  } catch { /* private mode: attribution is lost, the sign-up still works */ }
}
export function campaignTag(): string | null {
  try { return sessionStorage.getItem(CAMPAIGN_KEY); } catch { return null; }
}
