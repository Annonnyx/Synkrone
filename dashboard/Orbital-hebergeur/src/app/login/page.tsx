import { redirect } from "next/navigation";
import { publicSiteOriginFromEnv } from "@/lib/discord/site-link-env";

export const dynamic = "force-dynamic";

type Search = { mode?: string; returnTo?: string; oauth_error?: string };

function siteLogin(qs: URLSearchParams) {
  const origin = publicSiteOriginFromEnv() || "http://127.0.0.1:3668";
  return `${origin}/login?${qs.toString()}`;
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Search> | Search;
}) {
  const params = await Promise.resolve(searchParams);
  const qs = new URLSearchParams({ intent: "panel" });
  if (params.mode === "register") qs.set("mode", "register");
  if (params.returnTo) qs.set("returnTo", params.returnTo);
  if (params.oauth_error) qs.set("oauth_error", params.oauth_error);
  redirect(siteLogin(qs));
}
