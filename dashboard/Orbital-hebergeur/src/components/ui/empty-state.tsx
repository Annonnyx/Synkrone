import type { ReactNode } from "react";

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="text-sm font-semibold">{title}</div>
      {hint ? <p className="max-w-md text-sm leading-relaxed text-[var(--muted)]">{hint}</p> : null}
      {action}
    </div>
  );
}

