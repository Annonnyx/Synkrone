import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { Sidebar } from "@/components/panel";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar user={{ name: user.name, email: user.email }} />
      <div className="scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </div>
    </div>
  );
}
