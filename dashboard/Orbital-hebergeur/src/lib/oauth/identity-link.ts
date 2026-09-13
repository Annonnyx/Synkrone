export function isDiscordSnowflake(value: string | null | undefined): boolean {
  return /^\d{15,22}$/.test(String(value || "").trim());
}

export function discordIdFromPublicId(publicId: string | null | undefined): string | null {
  const id = String(publicId || "").trim();
  return isDiscordSnowflake(id) ? id : null;
}

export function discordIdFromIdentityRow(
  row: { discordId?: string; siteUserId?: string } | null | undefined,
): string | null {
  if (!row) return null;
  return discordIdFromPublicId(row.discordId) || discordIdFromPublicId(row.siteUserId);
}

export function discordIdFromSiteUser(
  panelUserId: string,
  user: { id?: string; dbId?: string; providers?: { discord?: string } } | null | undefined,
): string | null {
  if (!user) return null;
  const uid = String(panelUserId || "").trim();
  if (!uid) return null;
  if (String(user.dbId || "").trim() !== uid && String(user.id || "").trim() !== uid) return null;
  return (
    discordIdFromPublicId(user.id) || discordIdFromPublicId(user.providers?.discord)
  );
}

export type PanelIdentityPlan =
  | { action: "reuse"; userId: string }
  | { action: "link"; userId: string }
  | { action: "create" };

export function planPanelIdentityLink(input: {
  existingOauthUserId?: string | null;
  currentUserId?: string | null;
}): PanelIdentityPlan {
  const existing = String(input.existingOauthUserId || "").trim();
  if (existing) return { action: "reuse", userId: existing };
  const current = String(input.currentUserId || "").trim();
  if (current) return { action: "link", userId: current };
  return { action: "create" };
}

export function isPanelUserId(value: string | null | undefined): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    String(value || "").trim(),
  );
}
