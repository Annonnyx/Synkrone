import type { ReactNode } from "react";

export function UiBadge({
  tone = "default",
  children,
}: {
  tone?: "default" | "success" | "warning" | "danger" | "info" | "accent" | "gold";
  children: ReactNode;
}) {
  const cls =
    tone === "success"
      ? "badge-success"
      : tone === "warning"
        ? "badge-warning"
        : tone === "danger"
          ? "badge-danger"
          : tone === "info"
            ? "badge-info"
            : tone === "accent"
              ? "badge-accent"
              : tone === "gold"
                ? "badge-gold"
                : "";
  return <span className={`badge ${cls}`.trim()}>{children}</span>;
}
