"use client";

import { useEffect, useRef } from "react";

/**
 * Fetches remote state on mount and, when an interval is given, keeps refreshing
 * it while the component is mounted.
 *
 * `load` is called from a ref so a new function identity does not restart the
 * timer. Pass `resourceKey` when the fetched resource changes (id, section…).
 */
export function usePoll(
  load: () => void | Promise<void>,
  intervalMs?: number,
  resourceKey?: string | number,
) {
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    void loadRef.current();
    if (!intervalMs) return;
    const timer = setInterval(() => void loadRef.current(), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, resourceKey]);
}
