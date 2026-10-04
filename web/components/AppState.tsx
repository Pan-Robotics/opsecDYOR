"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

/**
 * App-wide sticky state. The provider lives in the root layout, which Next.js
 * keeps mounted across page navigation, so a page's state (the Analyze result,
 * the screener's ranking and selection, the compare set) survives clicking
 * away to another tab and back.
 *
 * The store is also mirrored to sessionStorage, per browser tab, so it survives
 * a reload or a hard navigation and is dropped when the tab closes. It is
 * restored in an effect after mount (never during server rendering or React
 * hydration, so the HTML always matches); values a page set before the restore
 * ran win over the stored ones. Keys starting with "cache:" stay in memory
 * only: bulky data that is cheap to refetch.
 *
 * The store is reactive `useState`, and it's included in the context VALUE so
 * that context consumers re-render when it changes. (A useRef + manual re-render
 * would NOT propagate, because the pages are passed as stable `children` from
 * the server layout; context subscription is what makes them update.)
 */
const STORAGE_KEY = "dyor:state:v1";
const VOLATILE_PREFIX = "cache:";

type Data = Record<string, unknown>;
type Store = {
  data: Data;
  set: (k: string, v: unknown) => void;
  hydrated: boolean;
};

const Ctx = createContext<Store | null>(null);

function readStored(): Data {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Data) : {};
  } catch {
    return {};
  }
}

function writeStored(data: Data) {
  try {
    const out: Data = {};
    for (const [k, v] of Object.entries(data)) {
      if (!k.startsWith(VOLATILE_PREFIX) && v !== undefined) out[k] = v;
    }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(out));
  } catch {
    // private mode, quota, or storage blocked: the in-memory store still works
  }
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<Data>({});
  const [hydrated, setHydrated] = useState(false);
  const latest = useRef<Data>(data);
  latest.current = data;

  const set = useCallback((k: string, v: unknown) => {
    setData((s) => {
      const next = typeof v === "function" ? (v as (p: unknown) => unknown)(s[k]) : v;
      return Object.is(s[k], next) ? s : { ...s, [k]: next };
    });
  }, []);

  // Restore the previous state of this browser tab once, after mount.
  useEffect(() => {
    const stored = readStored();
    setData((s) => ({ ...stored, ...s }));
    setHydrated(true);
  }, []);

  // Mirror changes back, debounced so typing in a filter box is not a write per key.
  useEffect(() => {
    if (!hydrated) return;
    const t = window.setTimeout(() => writeStored(data), 150);
    return () => window.clearTimeout(t);
  }, [data, hydrated]);

  // Flush immediately when the tab is hidden or unloaded.
  useEffect(() => {
    if (!hydrated) return;
    const flush = () => writeStored(latest.current);
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", flush);
    };
  }, [hydrated]);

  const value = useMemo<Store>(() => ({ data, set, hydrated }), [data, set, hydrated]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function useStore(): Store {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useStickyState must be used within AppStateProvider");
  return ctx;
}

/**
 * Like useState, but the value persists across page navigation (and reloads)
 * under `key`. The setter is stable per key (like useState's), so it is safe
 * in effect and callback dependency lists.
 */
export function useStickyState<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const { data, set: setStore } = useStore();
  const value = (key in data ? data[key] : initial) as T;
  const set = useCallback((next: T | ((p: T) => T)) => setStore(key, next), [key, setStore]);
  return [value, set];
}

/** Read a sticky value without owning it. */
export function useStickyValue<T>(key: string, fallback: T): T {
  const ctx = useStore();
  return (key in ctx.data ? ctx.data[key] : fallback) as T;
}

/** True once the stored state of this tab has been restored (always false on the server). */
export function useAppStateHydrated(): boolean {
  return useStore().hydrated;
}
