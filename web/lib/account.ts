"use client";
import { useEffect, useState } from "react";

// The CryptoOpsec account behind the browser's shared session cookie. One POST
// to the accounts service answers "who is this" and silently renews the cookie.
export const ACCOUNTS_URL = (process.env.NEXT_PUBLIC_ACCOUNTS_URL ?? "https://accounts.cryptoopsec.com").replace(/\/$/, "");

export type AccountUser = { id: string; handle: string; display_name: string | null; avatar_url: string | null; plan: string; features: string[]; wallets: number };

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

export const loginUrl = (returnTo: string) => `${ACCOUNTS_URL}/login?return_to=${encodeURIComponent(returnTo)}`;
export const accountUrl = `${ACCOUNTS_URL}/account`;

export function useAccount() {
  const [state, setState] = useState<{ loading: boolean; user: AccountUser | null }>({ loading: true, user: null });
  useEffect(() => {
    let alive = true;
    fetchSession().then((user) => { if (alive) setState({ loading: false, user }); });
    const onFocus = () => fetchSession().then((user) => { if (alive) setState({ loading: false, user }); });
    window.addEventListener("focus", onFocus);
    return () => { alive = false; window.removeEventListener("focus", onFocus); };
  }, []);
  const refresh = async () => setState({ loading: false, user: await fetchSession() });
  return { ...state, refresh, setUser: (user: AccountUser | null) => setState({ loading: false, user }) };
}
