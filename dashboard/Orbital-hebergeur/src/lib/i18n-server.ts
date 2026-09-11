import { cookies } from "next/headers";
import { fr, type Dict } from "./i18n/fr";
import { en } from "./i18n/en";
import { LOCALE_COOKIE, type Locale } from "./i18n/shared";

export async function getLocale(): Promise<Locale> {
  const store = await cookies();
  const value = store.get(LOCALE_COOKIE)?.value;
  return value === "en" ? "en" : "fr";
}

export async function getDict(): Promise<Dict> {
  return (await getLocale()) === "en" ? en : fr;
}
