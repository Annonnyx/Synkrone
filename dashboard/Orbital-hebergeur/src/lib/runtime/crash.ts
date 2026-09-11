const CONFIG_FATAL =
  /disallowed intents|BOT_TOKEN is not set|BOT_TOKEN not injected|invalid token/i;

function stripAnsi(line: string): string {
  return line.replace(/\u001b\[[0-9;]*m/g, "").trim();
}

export function isConfigFatalLogs(logs: string): boolean {
  return CONFIG_FATAL.test(logs);
}

/** Picks a readable crash cause from container logs (last fatal/error line). */
export function crashReasonFromLogs(
  logs: string,
  exitCode: number,
  oomKilled?: boolean,
  engineError?: string | null,
): string {
  if (oomKilled) return "Container was killed (out of memory)";
  const lines = logs.split(/\r?\n/).map(stripAnsi).filter(Boolean);
  const fatal = [...lines]
    .reverse()
    .find((line) => /\[fatal\]/i.test(line) || /^Error:/.test(line));
  if (fatal) {
    const match = fatal.match(/\[fatal\]\s*(.*)/i);
    return match?.[1] || fatal;
  }
  if (engineError) return engineError;
  return `exit code ${exitCode}`;
}
