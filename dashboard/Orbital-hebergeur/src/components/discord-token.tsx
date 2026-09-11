"use client";

import { useState } from "react";
import { Check, Copy, Eye, EyeOff, ExternalLink, KeyRound, ShieldCheck, Trash2 } from "lucide-react";
import { ErrorText } from "@/components/panel";
import { useT } from "@/lib/i18n";
import {
  DISCORD_PORTAL_URL,
  applicationIdFromToken,
  discordBotInviteUrl,
  isDiscordToken,
} from "@/lib/discord/token";

export function DiscordInviteLink({
  applicationId,
  compact = false,
}: {
  applicationId?: string | null;
  compact?: boolean;
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const href = discordBotInviteUrl(applicationId);
  if (!href) return null;

  const copy = async () => {
    await navigator.clipboard.writeText(href);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  if (compact) {
    return (
      <div className="flex flex-wrap gap-2">
        <a className="btn btn-primary" href={href} target="_blank" rel="noreferrer">
          <ExternalLink size={14} /> {t("discord.invite")}
        </a>
        <button type="button" className={`btn ${copied ? "btn-copied" : ""}`} onClick={() => void copy()}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? t("common.copied") : t("discord.copyInvite")}
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2.5">
      <div className="label mb-1">{t("discord.invite")}</div>
      <p className="mb-2 text-[11px] leading-relaxed text-[var(--muted)]">{t("discord.inviteHint")}</p>
      <div className="flex flex-wrap gap-2">
        <a className="btn btn-primary" href={href} target="_blank" rel="noreferrer">
          <ExternalLink size={14} /> {t("discord.invite")}
        </a>
        <button type="button" className={`btn ${copied ? "btn-copied" : ""}`} onClick={() => void copy()}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? t("common.copied") : t("discord.copyInvite")}
        </button>
      </div>
    </div>
  );
}

export function TokenHelp() {
  const t = useT();
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
      <div className="mb-1 flex items-center gap-1.5 font-semibold text-[var(--text)]">
        <KeyRound size={12} /> {t("discord.whereToken")}
      </div>
      <ol className="ml-4 list-decimal space-y-0.5">
        <li>
          {t("discord.step1").split("{portal}")[0]}
          <a
            className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
            href={DISCORD_PORTAL_URL}
            target="_blank"
            rel="noreferrer"
          >
            {t("discord.portal")} <ExternalLink size={10} />
          </a>
          {t("discord.step1").split("{portal}")[1]}
        </li>
        <li>{t("discord.step2")}</li>
        <li>{t("discord.step3")}</li>
        <li>{t("discord.step4")}</li>
        <li>{t("discord.step5")}</li>
      </ol>
      <div className="mt-1.5">{t("discord.warning")}</div>
    </div>
  );
}

/** Token field used by the creation wizard, where nothing is stored yet. */
export function TokenField({
  token,
  onToken,
  applicationId,
  onApplicationId,
}: {
  token: string;
  onToken: (value: string) => void;
  applicationId: string;
  onApplicationId: (value: string) => void;
}) {
  const t = useT();
  const [reveal, setReveal] = useState(false);
  const trimmed = token.trim();
  const valid = isDiscordToken(trimmed);
  const derived = valid ? applicationIdFromToken(trimmed) : null;

  return (
    <div className="space-y-3">
      <div>
        <div className="label mb-1">{t("discord.botToken")}</div>
        <div className="flex gap-2">
          <input
            className="input font-mono"
            type={reveal ? "text" : "password"}
            value={token}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => onToken(e.target.value)}
            placeholder={t("discord.optionalLater")}
          />
          <button
            type="button"
            className="btn"
            onClick={() => setReveal(!reveal)}
            title={reveal ? t("common.close") : t("common.view")}
          >
            {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        {trimmed.length > 0 && (
          <div className={`mt-1 text-[11px] ${valid ? "text-[var(--success)]" : "text-[var(--warning)]"}`}>
            {valid
              ? t("discord.validToken", { app: derived ? t("discord.forApp", { id: derived }) : "" })
              : t("discord.invalidToken")}
          </div>
        )}
      </div>
      <div>
        <div className="label mb-1">{t("discord.appIdOptional")}</div>
        <input
          className="input font-mono"
          value={applicationId}
          onChange={(e) => onApplicationId(e.target.value)}
          placeholder={derived ?? t("discord.readFromToken")}
        />
      </div>
      <DiscordInviteLink applicationId={applicationId.trim() || derived} />
      <TokenHelp />
    </div>
  );
}

/** Token panel used on an existing service: rotate, clear, show the fingerprint. */
export function DiscordTokenPanel({
  hasToken,
  fingerprint,
  applicationId,
  onSubmit,
  onApplicationId,
}: {
  hasToken: boolean;
  fingerprint: string | null;
  applicationId: string | null;
  onSubmit: (payload: { token: string; applicationId?: string }) => Promise<unknown>;
  onApplicationId: (value: string) => Promise<unknown>;
}) {
  const t = useT();
  const [token, setToken] = useState("");
  const [appId, setAppId] = useState(applicationId ?? "");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const trimmed = token.trim();
  const valid = isDiscordToken(trimmed);

  const run = async (value: string, clearing = false) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await onSubmit({ token: value, applicationId: appId.trim() });
      setToken("");
      setNotice(clearing ? t("discord.tokenRemoved") : t("discord.tokenStored"));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">{t("discord.botToken")}</span>
        {hasToken ? (
          <span className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] text-[var(--success)]"
            style={{ borderColor: "rgba(63, 107, 82, 0.45)" }}>
            <ShieldCheck size={12} /> {t("discord.storedFp", { fp: fingerprint ?? t("discord.unknown") })}
          </span>
        ) : (
          <span className="rounded border px-2 py-0.5 text-[11px] text-[var(--danger)]"
            style={{ borderColor: "rgba(168, 70, 47, 0.45)" }}>
            {t("discord.noToken")}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <input
          className="input font-mono"
          type={reveal ? "text" : "password"}
          value={token}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setToken(e.target.value)}
          placeholder={hasToken ? t("discord.pasteReplace") : t("discord.pasteToken")}
        />
        <button className="btn" type="button" onClick={() => setReveal(!reveal)}>
          {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
        <button
          className="btn btn-primary"
          disabled={busy || !valid}
          onClick={() => void run(trimmed)}
        >
          {hasToken ? t("discord.replaceToken") : t("discord.saveToken")}
        </button>
        {hasToken && (
          <button
            className="btn btn-danger"
            disabled={busy}
            onClick={() => {
              if (confirm(t("discord.removeConfirm"))) void run("", true);
            }}
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
      {trimmed.length > 0 && !valid && (
        <div className="text-[11px] text-[var(--warning)]">{t("discord.tokenHint")}</div>
      )}

      <div>
        <div className="label mb-1">{t("discord.appId")}</div>
        <div className="flex gap-2">
          <input
            className="input font-mono"
            value={appId}
            onChange={(e) => setAppId(e.target.value)}
            placeholder={t("discord.appIdPlaceholder")}
          />
          <button
            className="btn"
            disabled={busy || appId.trim() === (applicationId ?? "")}
            onClick={async () => {
              setBusy(true);
              setError(null);
              setNotice(null);
              try {
                await onApplicationId(appId.trim());
                setNotice(t("discord.appIdSaved"));
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("discord.saveId")}
          </button>
        </div>
      </div>

      <ErrorText error={error} />
      {notice && <div className="text-xs text-[var(--success)]">{notice}</div>}
      <DiscordInviteLink applicationId={appId.trim() || applicationId} />
      <TokenHelp />
    </div>
  );
}
