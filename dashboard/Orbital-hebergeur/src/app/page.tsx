import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { siteEnterPanel } from "@/lib/site-auth";

export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  redirect(siteEnterPanel("/hebergement/dashboard"));
}
