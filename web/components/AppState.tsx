"use client";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

/**
 * App-wide sticky state. The provider lives in the root layout, which Next.js
 * keeps mounted across page navigation — so a page's state (e.g. the Analyze
 * result + memo) survives clicking away to another tab and back.
 *
 * The store is reactive `useState`, and it's included in the context VALUE so
 * that context consumers re-render when it changes. (A useRef + manual re-render
 * would NOT propagate, because the pages are passed as stable `children` from
 * the server layout — context subscription is what makes them update.)
 */
type Store = {
  data: Record<string, unknown>;
  set: (k: string, v: unknown) => void;
};

const Ctx = createContext<Store | null>(null);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<Record<string, unknown>>({});
  const set = useCallback((k: string, v: unknown) => {
    setData((s) => ({ ...s, [k]: typeof v === "function" ? (v as (p: unknown) => unknown)(s[k]) : v }));
  }, []);
  const value = useMemo<Store>(() => ({ data, set }), [data, set]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Like useState, but the value persists across page navigation under `key`. */
export function useStickyState<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useStickyState must be used within AppStateProvider");
  const value = (key in ctx.data ? ctx.data[key] : initial) as T;
  const set = useCallback((next: T | ((p: T) => T)) => ctx.set(key, next), [key, ctx]);
  return [value, set];
}
