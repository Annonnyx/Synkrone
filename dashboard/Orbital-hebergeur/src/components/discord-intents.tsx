"use client";

import {
  GATEWAY_INTENTS,
  discordBotPortalUrl,
  isPrivilegedIntent,
  suggestedPrivilegedIntents,
} from "@/lib/discord/intents";
import { useT } from "@/lib/i18n";

export function PrivilegedPortalChecklist({
  selected,
  applicationId,
}: {
  selected: string[];
  applicationId?: string | null;
}) {
  const t = useT();
  const privileged = GATEWAY_INTENTS.filter(
    (intent) => intent.privileged && selected.includes(intent.id),
  );
  if (privileged.length === 0) return null;
  return (
    <div className="rounded-xl border border-[var(--warning)]/40 bg-[var(--warning)]/10 px-3 py-2 text-xs">
      <p className="font-medium text-[var(--warning)]">{t("create.portalChecklistTitle")}</p>
      <p className="mt-1 text-[var(--muted)]">{t("create.portalChecklistIntro")}</p>
      <ul className="mt-2 space-y-1">
        {privileged.map((intent) => (
          <li key={intent.id}>
            [ ] {intent.portal} ({intent.id})
          </li>
        ))}
      </ul>
      <a
        className="btn mt-2"
        href={discordBotPortalUrl(applicationId)}
        target="_blank"
        rel="noreferrer"
      >
        {t("create.openDiscordPortal")}
      </a>
    </div>
  );
}

export function IntentPicker({
  selected,
  onToggle,
  modules = [],
  applicationId,
}: {
  selected: string[];
  onToggle: (id: string) => void;
  modules?: string[];
  applicationId?: string | null;
}) {
  const t = useT();
  const suggested = suggestedPrivilegedIntents(modules);
  const hasPrivileged = selected.some(isPrivilegedIntent);

  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--muted)]">{t("create.intentsHint")}</p>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {GATEWAY_INTENTS.map((intent) => {
          const on = selected.includes(intent.id);
          return (
            <button
              key={intent.id}
              type="button"
              onClick={() => onToggle(intent.id)}
              className="btn justify-start text-left"
              style={{
                borderColor: on ? "var(--accent)" : "var(--line)",
                color: on ? "var(--text)" : "var(--muted)",
              }}
            >
              <span className="min-w-0">
                <span className="block">
                  {on ? "[x]" : "[ ]"} {intent.id}
                  {intent.privileged && (
                    <span className="ml-2 text-[10px] text-[var(--gold)]">
                      {t("create.privilegedBadge")}
                    </span>
                  )}
                </span>
                {intent.privileged && intent.portal && (
                  <span className="mt-0.5 block text-[10px] text-[var(--muted)]">{intent.portal}</span>
                )}
              </span>
            </button>
          );
        })}
      </div>
      {hasPrivileged && (
        <div className="space-y-2">
          <p className="text-xs text-[var(--warning)]">{t("create.privilegedIntentWarn")}</p>
          <PrivilegedPortalChecklist selected={selected} applicationId={applicationId} />
        </div>
      )}
      {!hasPrivileged && suggested.length > 0 && (
        <p className="text-[11px] text-[var(--muted)]">
          {t("create.suggestedPrivileged", { list: suggested.join(", ") })}
        </p>
      )}
    </div>
  );
}
