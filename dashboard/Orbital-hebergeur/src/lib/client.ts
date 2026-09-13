"use client";

import { explainError } from "@/lib/errors";
import { clientLocale } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { withPanelBase } from "@/lib/panel-base";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export type ApiOptions = RequestInit & {
  json?: unknown;
  /** Don't raise the automatic failure toast (background polls, inline forms). */
  silent?: boolean;
};

export async function api<T = unknown>(path: string, init?: ApiOptions): Promise<T> {
  const { silent, ...rest } = init ?? {};
  const opts: RequestInit = { ...rest, cache: "no-store" };
  if (init?.json !== undefined) {
    opts.method = init.method ?? "POST";
    opts.body = JSON.stringify(init.json);
    opts.headers = { ...(init.headers ?? {}), "Content-Type": "application/json" };
  }
  let res: Response;
  try {
    res = await fetch(withPanelBase(path), opts);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Network error";
    if (!silent) raiseErrorToast(message, 0);
    throw new ApiError(message, 0);
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!res.ok) {
    const payload = data as { error?: string; code?: string } | null;
    const message = payload?.error ?? `Request failed with status ${res.status}`;
    if (!silent) raiseErrorToast(message, res.status, payload?.code);
    throw new ApiError(message, res.status, payload?.code);
  }
  return data as T;
}

function raiseErrorToast(message: string, status: number, code?: string) {
  const explained = explainError(code ? `${code} ${message}` : message, clientLocale());
  notify({
    kind: "error",
    title: explained.title,
    message: explained.explanation,
    actionHint: explained.action,
    detail: status ? `${status} — ${message}` : message,
  });
}

export const STATE_COLORS: Record<string, string> = {
  RUNNING: "#6fcb8f",
  STARTING: "#b8823d",
  RESTARTING: "#b8823d",
  STOPPING: "#b8823d",
  CREATING: "#8fa096",
  DELETING: "#a8462f",
  STOPPED: "#8fa096",
  SUSPENDED: "#b8823d",
  CRASHED: "#a8462f",
  ERROR: "#a8462f",
};

export function fmtBytesMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

export function fmtUptime(seconds: number): string {
  if (!seconds) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${seconds % 60}s`;
}
