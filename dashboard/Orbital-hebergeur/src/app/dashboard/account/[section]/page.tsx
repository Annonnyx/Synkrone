"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { api } from "@/lib/client";
import { useI18n, useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { useToast } from "@/components/toast";
import { EmptyState, ErrorText, SecretBanner } from "@/components/panel";
import { PageHeader } from "@/components/ui";
import { OAuthButtons, oauthErrorMessage } from "@/components/oauth-buttons";
import type { OAuthProvider, ProviderStatus } from "@/lib/oauth/types";
import { KeyRound, ScrollText } from "lucide-react";

type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
};

type AuditLog = {
  id: string;
  action: string;
  detail: string | null;
  result: string;
  ip: string | null;
  serviceId: string | null;
  createdAt: string;
};

function AccountPageInner() {
  const { section } = useParams<{ section: string }>();
  const search = useSearchParams();
  const t = useT();
  const { locale } = useI18n();
  const toast = useToast();
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [user, setUser] = useState<{
    name: string;
    email: string;
    role: string;
    hasPassword?: boolean;
  } | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      if (section === "api-keys")
        setKeys((await api<{ keys: ApiKey[] }>("/api/account/api-keys", { silent: true })).keys);
      if (section === "audit")
        setLogs((await api<{ logs: AuditLog[] }>("/api/account/audit", { silent: true })).logs);
      if (section === "profile") {
        setUser((await api<{ user: typeof user }>("/api/auth/me", { silent: true })).user);
        setProviders((await api<{ providers: ProviderStatus[] }>("/api/auth/oauth", { silent: true })).providers);
        const linked = search.get("linked");
        if (linked) toast.success(t("account.linkedOk", { provider: linked }));
        setError(oauthErrorMessage(search.get("oauth_error"), t));
      } else {
        setError(null);
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [section, search, t, toast]);

  usePoll(load, undefined, section);

  const dateFmt = (iso: string) => new Date(iso).toLocaleString(locale);

  const titles: Record<string, string> = {
    "api-keys": t("account.apiKeys"),
    audit: t("account.audit"),
    profile: t("account.profile"),
  };
  const hints: Record<string, string> = {
    "api-keys": t("account.apiKeysHint"),
    audit: t("account.auditHint"),
    profile: t("account.profileHint"),
  };

  return (
    <div>
      <PageHeader title={titles[section] ?? section} subtitle={hints[section]} />
      <ErrorText error={error} />
      {secret && (
        <SecretBanner
          label={t("account.keyShownOnce")}
          value={secret}
          onClose={() => setSecret(null)}
        />
      )}

      {section === "api-keys" && (
        <div className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = e.target as HTMLFormElement;
              const input = form.elements.namedItem("name") as HTMLInputElement;
              const res = await api<{ secret: string }>("/api/account/api-keys", {
                json: { name: input.value },
              });
              setSecret(res.secret);
              input.value = "";
              toast.success(t("account.keyCreated"));
              void load();
            }}
          >
            <input className="input" name="name" placeholder={t("account.keyName")} required />
            <button className="btn btn-primary">{t("account.createKey")}</button>
          </form>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {keys.map((k) => (
              <div key={k.id} className="flex items-center justify-between px-4 py-2">
                <span>
                  <b>{k.name}</b>{" "}
                  <span className="font-mono text-[var(--muted)]">{k.prefix}…</span>
                </span>
                <div className="flex items-center gap-3 text-[var(--muted)]">
                  <span>
                    {k.revokedAt
                      ? t("account.revoked")
                      : k.lastUsedAt
                        ? t("account.usedAt", { date: dateFmt(k.lastUsedAt) })
                        : t("account.neverUsed")}
                  </span>
                  {!k.revokedAt && (
                    <button
                      className="btn btn-danger"
                      onClick={async () => {
                        await api(`/api/account/api-keys?id=${k.id}`, { method: "DELETE" });
                        toast.success(t("account.keyRevoked"));
                        void load();
                      }}
                    >
                      {t("account.revoke")}
                    </button>
                  )}
                </div>
              </div>
            ))}
            {keys.length === 0 && (
              <EmptyState icon={KeyRound} title={t("account.noKeys")} compact />
            )}
          </div>
        </div>
      )}

      {section === "audit" && (
        <div className="panel divide-y divide-[var(--line)] text-xs">
          {logs.map((l) => (
            <div key={l.id} className="flex justify-between gap-3 px-4 py-2">
              <span className="min-w-0">
                <span className="font-mono text-[var(--accent)]">{l.action}</span>{" "}
                <span className="text-[var(--muted)]">{l.detail}</span>
              </span>
              <span className="shrink-0 text-[var(--muted)]">
                {l.result} · {l.ip ?? "local"} · {dateFmt(l.createdAt)}
              </span>
            </div>
          ))}
          {logs.length === 0 && (
            <EmptyState icon={ScrollText} title={t("account.noAudit")} compact />
          )}
        </div>
      )}

      {section === "profile" && user && (
        <div className="space-y-3">
          <div className="panel space-y-1 p-4 text-sm">
            <div>
              {t("common.name")} : {user.name}
            </div>
            <div>
              {t("common.email")} : {user.email}
            </div>
            <div>
              {t("account.role")} : {user.role}
            </div>
          </div>
          <div className="panel space-y-3 p-4">
            <div className="text-sm font-semibold">{t("oauth.linkedAccounts")}</div>
            <p className="text-[11px] leading-relaxed text-[var(--muted)]">
              {t("oauth.linkedAccountsHint")}
            </p>
            <OAuthButtons
              providers={providers}
              mode="link"
              returnTo="/dashboard/account/profile"
              onUnlink={async (id: OAuthProvider) => {
                await api(`/api/auth/oauth/${id}`, { method: "DELETE" });
                void load();
              }}
            />
          </div>
          <form
            id="password"
            className="panel space-y-3 p-4"
            onSubmit={async (e) => {
              e.preventDefault();
              if (newPassword !== confirmPassword) {
                setError(t("account.passwordMismatch"));
                return;
              }
              setPasswordBusy(true);
              setError(null);
              try {
                await api("/api/auth/password", {
                  silent: true,
                  json: {
                    currentPassword: user.hasPassword ? currentPassword : undefined,
                    newPassword,
                  },
                });
                setCurrentPassword("");
                setNewPassword("");
                setConfirmPassword("");
                toast.success(t("account.passwordChanged"));
                void load();
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setPasswordBusy(false);
              }
            }}
          >
            <div className="text-sm font-semibold">
              {user.hasPassword === false ? t("account.setPassword") : t("account.changePassword")}
            </div>
            <p className="text-[11px] leading-relaxed text-[var(--muted)]">
              {user.hasPassword === false ? t("account.setPasswordHint") : t("account.passwordHint")}
            </p>
            {user.hasPassword !== false && (
              <div>
                <div className="label mb-1">{t("account.currentPassword")}</div>
                <input
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                />
              </div>
            )}
            <div>
              <div className="label mb-1">{t("account.newPassword")}</div>
              <input
                className="input"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            <div>
              <div className="label mb-1">{t("account.confirmPassword")}</div>
              <input
                className="input"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            <button className="btn btn-primary" disabled={passwordBusy}>
              {passwordBusy ? t("common.saving") : t("common.save")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default function AccountPage() {
  return (
    <Suspense>
      <AccountPageInner />
    </Suspense>
  );
}
