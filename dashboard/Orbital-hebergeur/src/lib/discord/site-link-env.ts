/** Env injected into Discord containers so `/config` can sign the `/serveur` link. */

export function publicSiteOriginFromEnv(env: NodeJS.Dict<string> = process.env): string {
  const raw = String(
    env.PUBLIC_SITE_ORIGIN ||
      env.PUBLIC_ORIGIN ||
      env.SYNKRONE_PANEL_ORIGIN ||
      env.ORBITAL_PUBLIC_ORIGIN ||
      "",
  )
    .trim()
    .replace(/\/hebergement\/?$/, "")
    .replace(/\/$/, "");
  return raw;
}

export function configLinkSecretFromEnv(env: NodeJS.Dict<string> = process.env): string {
  return String(env.SESSION_SECRET || env.BOT_CONFIG_SECRET || env.PLATFORM_SECRET_KEY || "").trim();
}

export function discordSiteLinkEnv(env: NodeJS.Dict<string> = process.env): Record<string, string> {
  const origin = publicSiteOriginFromEnv(env);
  const secret = configLinkSecretFromEnv(env);
  return {
    ...(origin ? { PUBLIC_SITE_ORIGIN: origin } : {}),
    ...(secret ? { BOT_CONFIG_SECRET: secret, SESSION_SECRET: secret } : {}),
  };
}
