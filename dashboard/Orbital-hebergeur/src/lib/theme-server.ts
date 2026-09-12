import { cookies } from "next/headers";
import { THEME_COOKIE, parseTheme, type Theme } from "./theme-shared";

export async function getTheme(): Promise<Theme> {
  const store = await cookies();
  return parseTheme(store.get(THEME_COOKIE)?.value);
}
