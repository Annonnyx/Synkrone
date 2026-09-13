import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { DashboardShell } from "@/components/panel";
import { siteEnterPanel } from "@/lib/site-auth";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect(siteEnterPanel("/hebergement/dashboard"));
  return <DashboardShell user={{ name: user.name, email: user.email }}>{children}</DashboardShell>;
}
