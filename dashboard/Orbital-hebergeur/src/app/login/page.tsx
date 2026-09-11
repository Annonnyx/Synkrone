"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { ErrorText, LanguageSelector, Logo } from "@/components/panel";
import { OAuthButtons, oauthErrorMessage } from "@/components/oauth-buttons";
import type { ProviderStatus } from "@/lib/oauth/types";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const t = useT();
  const [mode, setMode] = useState<"login" | "register">(
    params.get("mode") === "register" ? "register" : "login",
  );
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    oauthErrorMessage(params.get("oauth_error"), t),
  );
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [formReady, setFormReady] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/api/auth/${mode}`, { json: { email, name, password }, silent: true });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    setFormReady(true);
  }, []);

  useEffect(() => {
    void api<{ providers: ProviderStatus[] }>("/api/auth/oauth", { silent: true })
      .then((res) => setProviders(res.providers.filter((p) => p.configured)))
      .catch(() => setProviders([]));
  }, []);

  return (
    <main className="relative z-10 mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="logo-mosaic" aria-hidden="true" />
      <div className="panel login-panel p-7">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <Logo size={26} />
            <div className="font-serif text-xl font-bold leading-none tracking-tight">Synkrone</div>
          </div>
          <LanguageSelector />
        </div>
        <h1 className="page-title mt-6 text-3xl">
          {mode === "login" ? t("login.signInTitle") : t("login.registerTitle")}
        </h1>

        {providers.length > 0 && (
          <div className="mt-6">
            <OAuthButtons providers={providers} mode="login" />
            <div className="my-5 text-center text-[12px] text-[var(--muted)]">
              {t("login.divider")}
            </div>
          </div>
        )}

        {formReady ? (
          <form className="space-y-3" onSubmit={submit}>
            {mode === "register" && (
              <div>
                <div className="label mb-1">{t("login.name")}</div>
                <input
                  className="input"
                  name="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  autoComplete="name"
                />
              </div>
            )}
            <div>
              <div className="label mb-1">{t("login.email")}</div>
              <input
                className="input"
                type="email"
                name="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
              />
            </div>
            <div>
              <div className="label mb-1">{t("login.password")}</div>
              <input
                className="input"
                type="password"
                name="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>
            <ErrorText error={error} />
            <button className="btn btn-primary w-full justify-center" disabled={busy}>
              {busy ? (
                <>
                  <span className="spinner" /> {t("login.pleaseWait")}
                </>
              ) : mode === "login" ? (
                t("login.signIn")
              ) : (
                t("login.register")
              )}
            </button>
          </form>
        ) : (
          <div className="space-y-3" aria-hidden="true">
            <div>
              <div className="label mb-1">{t("login.email")}</div>
              <div className="input min-h-9" />
            </div>
            <div>
              <div className="label mb-1">{t("login.password")}</div>
              <div className="input min-h-9" />
            </div>
            <div className="btn btn-primary w-full justify-center opacity-45">{t("login.signIn")}</div>
          </div>
        )}

        <button
          type="button"
          className="mt-4 text-xs text-[var(--muted)] underline transition hover:text-[var(--text)]"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? t("login.noAccount") : t("login.hasAccount")}
        </button>
        {providers.length === 0 && (
          <p className="mt-3 text-[11px] leading-relaxed text-[var(--muted)]">{t("login.oauthNote")}</p>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
