import { redirect } from "next/navigation";
import { siteEnterPanel } from "@/lib/site-auth";

export const dynamic = "force-dynamic";

type Search = { returnTo?: string; oauth_error?: string };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Search> | Search;
}) {
  const params = await Promise.resolve(searchParams);
  redirect(siteEnterPanel(params.returnTo || "/hebergement/dashboard", params.oauth_error));
}
