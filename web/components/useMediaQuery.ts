"use client";
import { useSyncExternalStore } from "react";

/**
 * True when the media query matches. False during server rendering and
 * hydration, so the server and first client render agree; it flips right after
 * mount on a narrow screen. Use it to render ONE layout for the current width
 * instead of mounting both and hiding one with CSS.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Below Tailwind's md breakpoint: phones and small tablets in portrait. */
export const NARROW = "(max-width: 767px)";
