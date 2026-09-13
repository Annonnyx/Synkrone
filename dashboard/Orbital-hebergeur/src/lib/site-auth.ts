import { publicSiteOriginFromEnv } from "@/lib/discord/site-link-env";

export function publicSiteOrigin(): string {
  return publicSiteOriginFromEnv() || "http://127.0.0.1:3668";
}

export function normalizePanelReturnTo(returnTo?: string | null): string {
  const raw = String(returnTo || "").trim();
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || raw.includes("://")) {
    return "/hebergement/dashboard";
  }
  const pathOnly = raw.split("?")[0];
  if (pathOnly === "/hebergement/login" || pathOnly.startsWith("/hebergement/login/")) {
    return "/hebergement/dashboard";
  }
  if (pathOnly === "/hebergement" || pathOnly.startsWith("/hebergement/")) return pathOnly;
  if (pathOnly === "/login" || pathOnly.startsWith("/login/")) return "/hebergement/dashboard";
  if (pathOnly === "/dashboard" || pathOnly.startsWith("/dashboard/")) return `/hebergement${pathOnly}`;
  return "/hebergement/dashboard";
}

export function siteEnterPanel(returnTo?: string | null, oauthError?: string | null): string {
  const origin = publicSiteOrigin();
  const dest = normalizePanelReturnTo(returnTo);
  const qs = new URLSearchParams({ returnTo: dest });
  if (oauthError) qs.set("oauth_error", oauthError);
  return `${origin}/api/auth/enter-panel?${qs.toString()}`;
}
