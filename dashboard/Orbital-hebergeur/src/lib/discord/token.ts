/**
 * A Discord bot token is three base64url segments: the application id, a
 * creation timestamp and an HMAC. Validating the shape catches the two common
 * mistakes (pasting the client secret, or pasting the application id) before
 * the container is recreated with a token that can never log in.
 */
const TOKEN_SHAPE = /^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$/;

export function isDiscordToken(value: string): boolean {
  return TOKEN_SHAPE.test(value.trim());
}

/**
 * Decodes the application id embedded in the first segment, when it is valid.
 * Uses `atob` so the same helper runs in the browser form and on the server.
 */
export function applicationIdFromToken(value: string): string | null {
  const [head] = value.trim().split(".");
  if (!head) return null;
  const base64 = head.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  try {
    const decoded = atob(padded);
    return /^\d{15,25}$/.test(decoded) ? decoded : null;
  } catch {
    return null;
  }
}

export const DISCORD_PORTAL_URL = "https://discord.com/developers/applications";
