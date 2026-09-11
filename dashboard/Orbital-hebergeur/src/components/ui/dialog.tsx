import type { ReactNode } from "react";

export function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="presentation">
      <button type="button" className="absolute inset-0" aria-label="Fermer" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className="panel relative z-10 w-full max-w-md p-5"
      >
        <h2 id="dialog-title" className="page-title text-2xl">
          {title}
        </h2>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}
