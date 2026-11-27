"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { THEME_COOKIE, parseTheme, type Theme } from "./theme-shared";

function persist(theme: Theme) {
  document.cookie = `${THEME_COOKIE}=${theme};path=/;max-age=31536000;samesite=lax`;
  try {
    localStorage.setItem(THEME_COOKIE, theme);
  } catch {
    /* storage unavailable */
  }
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  setTheme: () => undefined,
});

export function ThemeProvider({
  initialTheme,
  children,
}: {
  initialTheme: Theme;
  children: ReactNode;
}) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  const setTheme = useCallback((next: Theme) => {
    const resolved = parseTheme(next);
    setThemeState(resolved);
    persist(resolved);
  }, []);

  useEffect(() => {
    const cookieMissing = !document.cookie.split("; ").some((part) => part.startsWith(`${THEME_COOKIE}=`));
    if (cookieMissing) {
      try {
        const stored = localStorage.getItem(THEME_COOKIE);
        if (stored === "light" || stored === "dark") {
          setThemeState(stored);
          persist(stored);
          return;
        }
      } catch {
        /* storage unavailable */
      }
    }
    persist(theme);
  }, [theme]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_COOKIE) return;
      const resolved = parseTheme(event.newValue);
      setThemeState(resolved);
      persist(resolved);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

export { THEME_COOKIE, THEMES, parseTheme, type Theme } from "./theme-shared";
