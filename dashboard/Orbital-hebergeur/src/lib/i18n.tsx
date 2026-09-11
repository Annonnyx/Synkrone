"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fr, type Dict } from "./i18n/fr";
import { en } from "./i18n/en";
import { LOCALE_COOKIE, type Locale } from "./i18n/shared";
import { silenceExtensionErrors } from "./silence-extension-errors";

silenceExtensionErrors();

export { LOCALES, LOCALE_COOKIE, type Locale } from "./i18n/shared";

const DICTS: Record<Locale, Dict> = { fr, en };

/** Reads the locale chosen on the client (cookie first, then localStorage). */
export function clientLocale(): Locale {
  if (typeof document === "undefined") return "fr";
  const fromCookie = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${LOCALE_COOKIE}=`))
    ?.split("=")[1];
  if (fromCookie === "en" || fromCookie === "fr") return fromCookie;
  try {
    const stored = localStorage.getItem(LOCALE_COOKIE);
    if (stored === "en" || stored === "fr") return stored;
  } catch {
    /* storage unavailable */
  }
  return "fr";
}

function lookup(dict: Dict, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name) =>
    vars[name] !== undefined ? String(vars[name]) : `{${name}}`,
  );
}

type I18nContextValue = {
  locale: Locale;
  dict: Dict;
  t: (key: string, vars?: Record<string, string | number>) => string;
  setLocale: (locale: Locale) => void;
};

const I18nContext = createContext<I18nContextValue>({
  locale: "fr",
  dict: fr,
  t: (key) => key,
  setLocale: () => undefined,
});

export function I18nProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    document.cookie = `${LOCALE_COOKIE}=${next};path=/;max-age=31536000;samesite=lax`;
    try {
      localStorage.setItem(LOCALE_COOKIE, next);
    } catch {
      /* storage unavailable */
    }
    if (typeof document !== "undefined") document.documentElement.lang = next;
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const value = lookup(DICTS[locale], key) ?? lookup(fr, key);
      return value === undefined ? key : interpolate(value, vars);
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, dict: DICTS[locale], t, setLocale }),
    [locale, t, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}

export function useT(): I18nContextValue["t"] {
  return useContext(I18nContext).t;
}
