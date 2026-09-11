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
import { useCreationFlags } from "@/lib/use-creation-flags";
import { firstCreateHref, isCreationEnabled } from "@/lib/services/creation-flags";

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

const TYPE_FILTERS = new Set(["discord", "minecraft", "web"]);

function createHrefFor(type: string | null) {
  if (type === "minecraft" || type === "web" || type === "discord") return `/dashboard/new/${type}`;
  return "/dashboard/new/discord";
}

function ServiceCard({ s }: { s: Service }) {
  const t = useT();
  return (
    <Link href={`/dashboard/services/${s.id}`} className="panel panel-hover block p-4">
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
  );
}

function List() {
  const params = useSearchParams();
  const rawType = params.get("type");
  const type = rawType && TYPE_FILTERS.has(rawType) ? rawType : null;
  const t = useT();
  const [services, setServices] = useState<Service[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const flags = useCreationFlags();

  const load = useCallback(async () => {
    try {
      const d = await api<{ services: Service[] }>("/api/dashboard", { silent: true });
      setServices(d.services);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  usePoll(load, 10000);

  const filtered = (services ?? []).filter((s) => !type || s.type === type);
  const canCreateType = !type || isCreationEnabled(flags, type);
  const createHref = canCreateType ? (type ? createHrefFor(type) : firstCreateHref(flags)) : null;
  const createLabel = type ? t("services.createInstance") : t("dashboard.createFirst");

  return (
    <div>
      <PageHeader
        title={type ? t(`nav.${type}`) : t("services.titleAll")}
        subtitle={type ? undefined : t("services.subtitle")}
        actions={
          type ? undefined : (
            <div className="flex flex-wrap gap-2">
              {isCreationEnabled(flags, "discord") && (
                <Link href="/dashboard/new/discord" className="btn">
                  <Plus size={14} /> {t("services.newDiscord")}
                </Link>
              )}
              {isCreationEnabled(flags, "minecraft") && (
                <Link href="/dashboard/new/minecraft" className="btn">
                  <Plus size={14} /> {t("services.newMinecraft")}
                </Link>
              )}
              {isCreationEnabled(flags, "web") && (
                <Link href="/dashboard/new/web" className="btn">
                  <Plus size={14} /> {t("services.newWeb")}
                </Link>
              )}
            </div>
          )
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
        <div className="flex flex-col items-start gap-4">
          {type ? (
            <>
              <p className="text-sm text-[var(--muted)]">
                {canCreateType ? t("services.emptyTypeHint") : t("services.creationClosed")}
              </p>
              {createHref && (
                <Link href={createHref} className="btn btn-primary">
                  <Plus size={14} /> {createLabel}
                </Link>
              )}
            </>
          ) : (
            <EmptyState
              icon={Server}
              title={t("services.emptyAll")}
              hint={createHref ? t("services.emptyHint") : t("services.creationClosed")}
              action={
                createHref ? (
                  <Link href={createHref} className="btn btn-primary">
                    <Plus size={14} /> {createLabel}
                  </Link>
                ) : undefined
              }
            />
          )}
        </div>
      )}

      {services && filtered.length > 0 && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((s) => (
              <ServiceCard key={s.id} s={s} />
            ))}
          </div>
          {createHref && (
            <div className="mt-6">
              <Link href={createHref} className="btn btn-primary">
                <Plus size={14} /> {createLabel}
              </Link>
            </div>
          )}
        </>
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
