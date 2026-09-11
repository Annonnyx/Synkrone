export type ConsolePrefs = {
  wrap: boolean;
  fontPx: number;
  heightPx: number;
};

export const DEFAULT_CONSOLE_PREFS: ConsolePrefs = {
  wrap: true,
  fontPx: 13,
  heightPx: 420,
};

export const FONT_CHOICES = [11, 13, 15] as const;
export const HEIGHT_CHOICES = [280, 420, 640] as const;

const PREFS_KEY = "orbital:console:prefs";
const prefsListeners = new Set<() => void>();

export function subscribeConsolePrefs(onStoreChange: () => void) {
  prefsListeners.add(onStoreChange);
  return () => {
    prefsListeners.delete(onStoreChange);
  };
}

export function getConsolePrefsSnapshot(): string {
  try {
    return localStorage.getItem(PREFS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function getConsolePrefsServerSnapshot(): string {
  return "";
}

export function writeConsolePrefs(prefs: ConsolePrefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* private mode / quota */
  }
  for (const listener of prefsListeners) listener();
}

export function parseConsolePrefs(raw: string | null): ConsolePrefs {
  if (!raw) return { ...DEFAULT_CONSOLE_PREFS };
  try {
    const parsed = JSON.parse(raw) as Partial<ConsolePrefs>;
    const fontPx = FONT_CHOICES.includes(parsed.fontPx as (typeof FONT_CHOICES)[number])
      ? (parsed.fontPx as number)
      : DEFAULT_CONSOLE_PREFS.fontPx;
    const heightPx = HEIGHT_CHOICES.includes(parsed.heightPx as (typeof HEIGHT_CHOICES)[number])
      ? (parsed.heightPx as number)
      : DEFAULT_CONSOLE_PREFS.heightPx;
    return {
      wrap: parsed.wrap !== false,
      fontPx,
      heightPx,
    };
  } catch {
    return { ...DEFAULT_CONSOLE_PREFS };
  }
}

export function readConsolePrefs(): ConsolePrefs {
  try {
    return parseConsolePrefs(localStorage.getItem(PREFS_KEY));
  } catch {
    return { ...DEFAULT_CONSOLE_PREFS };
  }
}

