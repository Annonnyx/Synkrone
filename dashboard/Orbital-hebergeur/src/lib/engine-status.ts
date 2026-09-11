"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/client";

export type EngineSnap = { reachable: boolean; error?: string | null };

const INTERVAL_MS = 30_000;

let snapshot: EngineSnap | null = null;
let inflight: Promise<EngineSnap | null> | null = null;
let lastFetch = 0;
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<(value: EngineSnap | null) => void>();

async function fetchEngine(force = false): Promise<EngineSnap | null> {
  if (inflight) return inflight;
  if (!force && lastFetch && Date.now() - lastFetch < INTERVAL_MS) return snapshot;

  inflight = (async () => {
    try {
      const d = await api<{ docker: { reachable: boolean; error: string | null } }>("/api/engine", {
        silent: true,
      });
      snapshot = { reachable: d.docker.reachable, error: d.docker.error };
    } catch {
      snapshot = snapshot ?? { reachable: false, error: null };
    } finally {
      lastFetch = Date.now();
      inflight = null;
    }
    for (const listener of listeners) listener(snapshot);
    return snapshot;
  })();

  return inflight;
}

function ensureTimer() {
  if (timer) return;
    timer = setInterval(() => {
    void fetchEngine(true);
  }, INTERVAL_MS);
}

function subscribe(listener: (value: EngineSnap | null) => void) {
  listeners.add(listener);
  if (snapshot) listener(snapshot);
  void fetchEngine();
  ensureTimer();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Shared engine probe: one in-flight request, 30s cadence, survives remounts. */
export function useEngineStatus(): EngineSnap | null {
  const [engine, setEngine] = useState<EngineSnap | null>(snapshot);
  useEffect(() => subscribe(setEngine), []);
  return engine;
}
