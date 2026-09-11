"use client";

import { useT } from "@/lib/i18n";
import { withPanelBase } from "@/lib/panel-base";
import type { OAuthProvider, ProviderStatus } from "@/lib/oauth/types";

function ProviderMark({ id }: { id: OAuthProvider }) {
  if (id === "github") {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <path
          fill="currentColor"
          d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.6 7.6 0 0 1 8 4.77c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"
        />
      </svg>
    );
  }
  if (id === "google") {
    return (
      <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
        <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62" />
        <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.8.54-1.83.86-3.05.86-2.35 0-4.34-1.58-5.05-3.71H.95v2.33A8.1 8.1 0 0 0 9 18" />
        <path fill="#FBBC05" d="M3.95 10.71A4.87 4.87 0 0 1 3.7 9c0-.6.1-1.17.25-1.71V4.96H.95A8.1 8.1 0 0 0 0 9c0 1.31.31 2.55.95 3.64z" />
        <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A8.1 8.1 0 0 0 .95 4.96L3.95 7.3C4.66 5.16 6.65 3.58 9 3.58" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#5865F2"
        d="M20.32 4.37A19.8 19.8 0 0 0 15.89 3l-.2.4a18.27 18.27 0 0 1 4.36 1.77 16.5 16.5 0 0 0-13.1 0A16.7 16.7 0 0 1 8.3 3.4L8.11 3A19.86 19.86 0 0 0 3.67 4.38C.53 9.05-.32 13.6.1 18.08A19.94 19.94 0 0 0 6.1 21l.5-.8a13.1 13.1 0 0 1-2.06-1 15.3 15.3 0 0 0 13 0 12.4 12.4 0 0 1-2.07 1l.5.8a19.9 19.9 0 0 0 6-2.91c.5-5.2-.85-9.71-4.65-13.73ZM8.02 15.33c-1.18 0-2.15-1.08-2.15-2.4 0-1.33.95-2.41 2.15-2.41s2.17 1.09 2.15 2.4c0 1.33-.95 2.41-2.15 2.41m7.96 0c-1.18 0-2.15-1.08-2.15-2.4 0-1.33.95-2.41 2.15-2.41s2.17 1.09 2.15 2.4c0 1.33-.96 2.41-2.15 2.41"
      />
    </svg>
  );
}

function providerLabel(id: OAuthProvider, t: (key: string) => string) {
  if (id === "github") return t("oauth.github");
  if (id === "google") return t("oauth.google");
  return t("oauth.discord");
}

export function OAuthButtons({
  providers,
  mode,
  returnTo,
  onUnlink,
}: {
  providers: ProviderStatus[];
  mode: "login" | "link";
  returnTo?: string;
  onUnlink?: (id: OAuthProvider) => Promise<void> | void;
}) {
  const t = useT();
  return (
    <div className="space-y-2">
      {providers.map((p) => {
        const href = withPanelBase(
          `/api/auth/oauth/${p.id}?intent=${mode}${
            returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""
          }`,
        );
        const label = providerLabel(p.id, t);
        if (mode === "link" && p.linked) {
          return (
            <div
              key={p.id}
              className="flex items-center justify-between gap-2 rounded-[9px] border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2"
            >
              <div className="flex min-w-0 items-center gap-2 text-sm">
                <ProviderMark id={p.id} />
                <span className="font-semibold">{label}</span>
                <span className="truncate text-[11px] text-[var(--muted)]">
                  {p.login || p.email || t("oauth.linked")}
                </span>
              </div>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => void onUnlink?.(p.id)}
              >
                {t("oauth.unlink")}
              </button>
            </div>
          );
        }
        if (!p.configured) {
          if (mode === "login") return null;
          return (
            <p key={p.id} className="hint">
              {t("oauth.notConfigured", { provider: label })}
            </p>
          );
        }
        return (
          <button
            key={p.id}
            type="button"
            className="btn w-full justify-center"
            onClick={() => {
              window.location.assign(href);
            }}
          >
            <ProviderMark id={p.id} />
            {mode === "login"
              ? t("oauth.continueWith", { provider: label })
              : t("oauth.link", { provider: label })}
          </button>
        );
      })}
    </div>
  );
}

export function oauthErrorMessage(
  code: string | null,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string | null {
  if (!code) return null;
  const key = `oauth.error.${code}`;
  const translated = t(key);
  return translated === key ? t("oauth.error.oauth_failed") : translated;
}
