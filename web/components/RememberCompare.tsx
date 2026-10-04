"use client";
import { useEffect } from "react";
import { useAppStateHydrated, useStickyState } from "./AppState";

// The compare page is server-rendered from ?tokens=; this records the set so the
// Compare tab in the nav (and "Add to comparison" links) return to it.
export default function RememberCompare({ ids }: { ids: string[] }) {
  const hydrated = useAppStateHydrated();
  const [current, setIds] = useStickyState<string[]>("compare:ids", []);
  const key = ids.join(",");
  const currentKey = current.join(",");
  useEffect(() => {
    if (!hydrated || currentKey === key) return;
    setIds(key ? key.split(",") : []);
  }, [hydrated, key, currentKey, setIds]);
  return null;
}
