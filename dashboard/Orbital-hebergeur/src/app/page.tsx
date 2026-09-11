import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { getDict } from "@/lib/i18n-server";
import { LanguageSelector } from "@/components/panel";

export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  const t = await getDict();

  return (
    <main className="relative z-10 flex min-h-screen flex-col justify-center px-6">
      <div className="logo-mosaic" aria-hidden="true" />
      <div className="absolute right-6 top-6">
        <LanguageSelector />
      </div>
      <div className="mx-auto w-full max-w-xl">
        <h1 className="font-serif text-[clamp(2.6rem,8vw,4.2rem)] font-bold leading-[1.1] tracking-tight">
          Synkrone
        </h1>
        <p className="mt-5 max-w-[46ch] text-left text-sm leading-relaxed text-[var(--muted)]">
          {t.landing.subtitle}
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link href="/login" className="btn btn-primary">
            {t.landing.openPanel}
          </Link>
          <Link href="/login?mode=register" className="btn">
            {t.landing.createAccount}
          </Link>
        </div>
      </div>
    </main>
  );
}
