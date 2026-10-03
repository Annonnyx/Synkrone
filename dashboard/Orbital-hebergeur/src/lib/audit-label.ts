import { en } from "./i18n/en";
import { fr } from "./i18n/fr";
import type { Locale } from "./i18n/shared";

const DICTS = { fr, en } as const;

function lookup(locale: Locale, key: string): string | undefined {
  let node: unknown = DICTS[locale];
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

/**
 * Human-readable label for a raw audit action (e.g. `service.restart`).
 * Dictionary keys mirror the raw segments, so `audit.` + action resolves
 * directly, including dynamic actions (`service.create.discord`,
 * `minecraft.plugin.install`, `oauth.link.github`). Unknown actions fall
 * back to French, then to the raw action string.
 */
export function auditActionLabel(action: string, locale: Locale = "fr"): string {
  return lookup(locale, `audit.${action}`) ?? lookup("fr", `audit.${action}`) ?? action;
}
