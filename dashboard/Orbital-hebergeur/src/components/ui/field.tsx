import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Field({
  label,
  hint,
  children,
}: {
  label?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1">
      {label ? <div className="label">{label}</div> : null}
      {children}
      {hint ? <p className="hint">{hint}</p> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`input ${props.className ?? ""}`.trim()} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`select ${props.className ?? ""}`.trim()} {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`textarea ${props.className ?? ""}`.trim()} {...props} />;
}
