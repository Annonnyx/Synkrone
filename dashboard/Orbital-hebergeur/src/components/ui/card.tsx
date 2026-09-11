import type { HTMLAttributes, ReactNode } from "react";

export function Card({
  hover = false,
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { hover?: boolean; children?: ReactNode }) {
  return (
    <div className={`panel ${hover ? "panel-hover" : ""} ${className}`.trim()} {...props}>
      {children}
    </div>
  );
}
