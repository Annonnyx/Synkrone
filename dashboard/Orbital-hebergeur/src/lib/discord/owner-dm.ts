import { isDiscordSnowflake } from "@/lib/oauth/identity-link";

/** Best-effort owner DM. Closed DMs / missing token / unknown id fail silently. */
export async function dmDiscordUser(discordId: string, content: string): Promise<boolean> {
  const token = String(process.env.DISCORD_BOT_TOKEN || "").trim();
  if (!token || !isDiscordSnowflake(discordId)) return false;
  try {
    const channelRes = await fetch("https://discord.com/api/v10/users/@me/channels", {
      method: "POST",
      headers: {
        Authorization: `Bot ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ recipient_id: discordId }),
      signal: AbortSignal.timeout(4000),
    });
    if (!channelRes.ok) return false;
    const channel = (await channelRes.json()) as { id?: string };
    if (!channel.id) return false;
    const msgRes = await fetch(`https://discord.com/api/v10/channels/${channel.id}/messages`, {
      method: "POST",
      headers: {
        Authorization: `Bot ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content: content.slice(0, 1900) }),
      signal: AbortSignal.timeout(4000),
    });
    return msgRes.ok;
  } catch {
    return false;
  }
}
