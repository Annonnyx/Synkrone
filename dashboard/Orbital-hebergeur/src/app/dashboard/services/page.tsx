"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { Plus, Server } from "lucide-react";
import { api, fmtBytesMb } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { PageHeader } from "@/components/ui";
import { Bar, EmptyState, ErrorText, Skeleton, StateBadge, TypeIcon } from "@/components/panel";

type Service = {
  id: string;
  name: string;
  type: string;
  state: string;
  slug: string;
  memoryLimitMb: number;
  cpuLimit: number;
  container: { name: string; image: string } | null;
  stats: { memoryMb: number; cpuPercent: number } | null;
};

function List() {
  const params = useSearchParams();
  const type = params.get("type");
  const t = useT();
  const [services, setServices] = useState<Service[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [minecraftEnabled, setMinecraftEnabled] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api<{ services: Service[] }>("/api/dashboard", { silent: true });
      setServices(d.services);
      setError(null);
      api<{ minecraftEnabled: boolean }>("/api/platform", { silent: true })
        .then((p) => setMinecraftEnabled(p.minecraftEnabled))
        .catch(() => setMinecraftEnabled(true));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  usePoll(load, 10000);

  const filtered = (services ?? []).filter((s) => !type || s.type === type);
  const createType = type === "minecraft" || type === "discord" || type === "web" ? type : null;
  const createHref = `/dashboard/new/${createType || "discord"}`;

  return (
    <div>
      <PageHeader
        title={type ? t(`nav.${type}`) : t("services.titleAll")}
        subtitle={t("services.subtitle")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link href="/dashboard/new/discord" className={createType === "discord" ? "btn btn-primary" : "btn"}>
              <Plus size={14} /> {t("services.newDiscord")}
            </Link>
            {minecraftEnabled !== false && (
              <Link href="/dashboard/new/minecraft" className={createType === "minecraft" ? "btn btn-primary" : "btn"}>
                <Plus size={14} /> {t("services.newMinecraft")}
              </Link>
            )}
            <Link href="/dashboard/new/web" className={createType === "web" ? "btn btn-primary" : "btn"}>
              <Plus size={14} /> {t("services.newWeb")}
            </Link>
          </div>
        }
      />

      <ErrorText error={error} />

      {!services && !error && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {services && filtered.length === 0 && (
        <EmptyState
          icon={Server}
          title={type ? t("services.empty") : t("services.emptyAll")}
          hint={t("services.emptyHint")}
          action={
            <Link href={createHref} className="btn btn-primary">
              <Plus size={14} /> {t("dashboard.createFirst")}
            </Link>
          }
        />
      )}

      {services && filtered.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((s) => (
            <Link
              key={s.id}
              href={`/dashboard/services/${s.id}`}
              className="panel panel-hover block p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2 font-semibold">
                  <TypeIcon type={s.type} />
                  <span className="truncate">{s.name}</span>
                </div>
                <StateBadge state={s.state} />
              </div>
              <div className="mt-2 truncate font-mono text-[10px] text-[var(--muted)]">
                {s.container?.name ?? `${s.type}-${s.slug}`} ·{" "}
                {s.container?.image ?? t("services.imagePending")}
              </div>
              <div className="mt-3 space-y-2">
                <div>
                  <div className="mb-1 flex justify-between text-[10px] text-[var(--muted)]">
                    <span>{t("dashboard.memory")}</span>
                    <span className="font-mono">
                      {s.stats
                        ? `${fmtBytesMb(s.stats.memoryMb)} / ${fmtBytesMb(s.memoryLimitMb)}`
                        : fmtBytesMb(s.memoryLimitMb)}
                    </span>
                  </div>
                  <Bar value={s.stats?.memoryMb ?? 0} max={s.memoryLimitMb} />
                </div>
                <div>
                  <div className="mb-1 flex justify-between text-[10px] text-[var(--muted)]">
                    <span>{t("dashboard.cpu")}</span>
                    <span className="font-mono">
                      {s.stats
                        ? `${s.stats.cpuPercent.toFixed(0)}%`
                        : `${(s.cpuLimit / 1000).toFixed(1)} ${t("services.cores")}`}
                    </span>
                  </div>
                  <Bar value={s.stats ? Math.min(100, s.stats.cpuPercent) : 0} max={100} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ServicesPage() {
  return (
    <Suspense>
      <List />
    </Suspense>
  );
}
