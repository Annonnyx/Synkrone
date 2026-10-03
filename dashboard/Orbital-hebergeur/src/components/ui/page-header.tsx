import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3 sm:items-end">
      <div className="min-w-0">
        <h1 className="page-title break-words">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--muted)]">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex w-full flex-wrap gap-2 sm:w-auto">{actions}</div> : null}
    </div>
  );
}
