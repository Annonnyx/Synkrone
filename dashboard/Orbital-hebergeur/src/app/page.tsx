import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { publicSiteOriginFromEnv } from "@/lib/discord/site-link-env";

export const dynamic = "force-dynamic";

function siteLogin(query: string) {
  const origin = publicSiteOriginFromEnv() || "http://127.0.0.1:3668";
  return `${origin}/login?${query}`;
}

export default async function Home() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  redirect(siteLogin("intent=panel"));
}
