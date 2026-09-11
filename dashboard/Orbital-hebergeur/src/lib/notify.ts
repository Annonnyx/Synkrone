export type ToastKind = "success" | "error" | "info";

export type ToastInput = {
  kind: ToastKind;
  title: string;
  message?: string;
  /** Raw technical detail, hidden behind an expander. */
  detail?: string;
  /** Suggested corrective action, shown under the message. */
  actionHint?: string;
  durationMs?: number;
};

type Listener = (toast: ToastInput) => void;

const listeners = new Set<Listener>();

/** Non-React modules (e.g. the api() helper) publish through this bus. */
export function notify(toast: ToastInput): void {
  for (const listener of listeners) listener(toast);
}

export function onNotify(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
