import type { ReactNode } from "react";

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="scroll overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return (
    <th className="border-b border-[var(--line)] px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
      {children}
    </th>
  );
}

export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`border-b border-[var(--line)] px-3 py-2.5 align-middle ${className}`.trim()}>{children}</td>;
}
