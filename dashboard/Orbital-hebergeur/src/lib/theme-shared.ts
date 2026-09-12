export type Theme = "light" | "dark";

export const THEMES: Theme[] = ["light", "dark"];
export const THEME_COOKIE = "synkrone_theme";

export function parseTheme(value: string | null | undefined): Theme {
  return value === "dark" ? "dark" : "light";
}
