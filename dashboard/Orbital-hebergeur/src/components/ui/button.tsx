import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "default" | "primary" | "ghost" | "danger" | "success";

export function Button({
  variant = "default",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children?: ReactNode;
}) {
  const extra =
    variant === "primary"
      ? "btn-primary"
      : variant === "ghost"
        ? "btn-ghost"
        : variant === "danger"
          ? "btn-danger"
          : variant === "success"
            ? "btn-success"
            : "";
  return (
    <button className={`btn ${extra} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}
