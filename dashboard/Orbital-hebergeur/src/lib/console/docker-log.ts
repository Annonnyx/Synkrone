/** Docker `timestamps=true` prefix: 2026-09-12T13:27:42.123456789Z message */
const DOCKER_TS =
  /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)(Z|[+-]\d{2}:\d{2})\s+([\s\S]*)$/;

export function stripDockerTimestamp(line: string): { at?: string; message: string } {
  const text = String(line ?? "");
  const match = text.match(DOCKER_TS);
  if (!match) return { message: text };
  const iso = `${match[1]}${match[2]}`;
  const date = new Date(iso);
  return {
    at: Number.isNaN(date.getTime()) ? undefined : date.toISOString(),
    message: match[3] ?? "",
  };
}

export function fallbackConsoleAt(at?: string | Date | null): string | undefined {
  if (!at) return undefined;
  if (at instanceof Date) {
    return Number.isNaN(at.getTime()) ? undefined : at.toISOString();
  }
  const date = new Date(at);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export function consoleLineFields(
  message: string,
  fallbackAt?: string | Date | null,
): { message: string; at?: string } {
  const parsed = stripDockerTimestamp(message);
  return {
    message: parsed.message,
    at: parsed.at ?? fallbackConsoleAt(fallbackAt),
  };
}

export function formatConsoleClock(at?: string | Date | null): string {
  if (!at) return "";
  const date = at instanceof Date ? at : new Date(at);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
