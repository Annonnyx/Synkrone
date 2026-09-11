"use client";

/**
 * React Context DevTool throws in `onCommitFiberRoot` on React 19. Next.js
 * treats that as an app error, re-renders the overlay, which commits again.
 */
function isExtensionNoise(value: unknown): boolean {
  const text =
    typeof value === "string"
      ? value
      : value instanceof Error
        ? `${value.name} ${value.message} ${value.stack ?? ""}`
        : "";
  return text.includes("__reactContextDevtoolDebugId");
}

let installed = false;

export function silenceExtensionErrors() {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener(
    "error",
    (event) => {
      if (!isExtensionNoise(event.error ?? event.message)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    },
    true,
  );

  window.addEventListener(
    "unhandledrejection",
    (event) => {
      if (!isExtensionNoise(event.reason)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    },
    true,
  );

  const nativeError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    if (args.some((arg) => isExtensionNoise(arg))) return;
    nativeError(...args);
  };
}
