"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, ChevronDown, Info, X, XCircle } from "lucide-react";
import { notify, onNotify, type ToastInput, type ToastKind } from "@/lib/notify";
import { useT } from "@/lib/i18n";

type Toast = ToastInput & { id: number };

const ICONS: Record<ToastKind, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const ICON_COLOR: Record<ToastKind, string> = {
  success: "var(--success)",
  error: "var(--danger)",
  info: "var(--info)",
};

function ToastCard({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const Icon = ICONS[toast.kind];

  return (
    <div className={`toast toast-${toast.kind} w-80 px-4 py-3`} role="status">
      <div className="flex items-start gap-3">
        <Icon size={17} className="mt-0.5 shrink-0" style={{ color: ICON_COLOR[toast.kind] }} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-snug">{toast.title}</div>
          {toast.message && (
            <div className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">
              {toast.message}
            </div>
          )}
          {toast.actionHint && (
            <div className="mt-1.5 text-xs leading-relaxed text-[var(--text)]">
              {toast.actionHint}
            </div>
          )}
          {toast.detail && (
            <div className="mt-1.5">
              <button
                className="flex items-center gap-1 text-[11px] font-semibold text-[var(--muted)] hover:text-[var(--text)]"
                onClick={() => setExpanded((v) => !v)}
              >
                <ChevronDown
                  size={12}
                  style={{ transform: expanded ? "rotate(180deg)" : undefined, transition: "transform .15s" }}
                />
                {t("common.details")}
              </button>
              {expanded && (
                <pre className="console scroll mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap break-all p-2 text-[11px] text-[var(--muted)]">
                  {toast.detail}
                </pre>
              )}
            </div>
          )}
        </div>
        <button
          className="shrink-0 text-[var(--muted)] transition hover:text-[var(--text)]"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  useEffect(() => {
    const off = onNotify((input) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-4), { ...input, id }]);
      const duration = input.durationMs ?? (input.kind === "error" ? 10_000 : 5_000);
      timers.current.set(id, setTimeout(() => dismiss(id), duration));
    });
    const active = timers.current;
    return () => {
      off();
      for (const timer of active.values()) clearTimeout(timer);
      active.clear();
    };
  }, [dismiss]);

  return (
    <>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 [&>*]:pointer-events-auto">
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onClose={() => dismiss(toast.id)} />
        ))}
      </div>
    </>
  );
}

/** Convenience helpers for user-initiated actions. */
export function useToast() {
  const t = useT();
  return {
    success: (title: string, message?: string) => notify({ kind: "success", title, message }),
    info: (title: string, message?: string) => notify({ kind: "info", title, message }),
    error: (title: string, message?: string, detail?: string) =>
      notify({ kind: "error", title, message, detail }),
    saved: () => notify({ kind: "success", title: t("toast.saved") }),
  };
}
