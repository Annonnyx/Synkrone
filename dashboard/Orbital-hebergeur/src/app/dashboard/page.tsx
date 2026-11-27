"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { AlertTriangle, Plus, RefreshCw } from "lucide-react";
import { api, fmtBytesMb } from "@/lib/client";
import { explainError } from "@/lib/errors";
import { useI18n, useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import {
  Bar,
  EmptyState,
  EngineBanner,
  ErrorText,
  Skeleton,
  Stat,
  StateBadge,
  TypeIcon,
} from "@/components/panel";
import { Server } from "lucide-react";
import { PageHeader } from "@/components/ui";
import { QuotaChart } from "@/components/charts";
import { useCreationFlags } from "@/lib/use-creation-flags";
import { auditActionLabel } from "@/lib/audit-label";
import { firstCreateHref } from "@/lib/services/creation-flags";
import { cpuPercentOfQuota } from "@/lib/runtime/cpu";

type DashboardData = {
  services: Array<{
    id: string;
    name: string;
    type: string;
    state: string;
    memoryLimitMb: number;
    cpuLimit: number;
    storageLimitMb: number;
    container: { id: string | null; image: string; name: string } | null;
    stats: { cpuPercent: number; memoryMb: number; diskMb: number } | null;
  }>;
  totals: {
    memoryLimitMb: number;
    memoryUsedMb: number;
    cpuMillicores: number;
    cpuPercent: number;
    storageLimitMb: number;
    diskMb: number;
    rxKb: number;
    txKb: number;
    running: number;
    failing: number;
  };
  activity: Array<{ id: string; action: string; detail: string | null; createdAt: string }>;
  databases: number;
  alerts: Array<{ serviceId: string; name: string; state: string; message: string }>;
};

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-40" />
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const t = useT();
  const { locale } = useI18n();
  const flags = useCreationFlags();
  const createHref = firstCreateHref(flags);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<DashboardData>("/api/dashboard", { silent: true }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  usePoll(load, 10000);

  return (
    <div>
      <PageHeader
        title={t("dashboard.title")}
        subtitle={t("dashboard.subtitle")}
        actions={
          <div className="flex gap-2">
            <button className="btn" onClick={() => void load()} disabled={loading}>
              {loading ? <span className="spinner" /> : <RefreshCw size={14} />} {t("common.refresh")}
            </button>
            {createHref && (
              <Link href={createHref} className="btn btn-primary">
                <Plus size={14} /> {t("dashboard.newService")}
              </Link>
            )}
          </div>
        }
      />

      <EngineBanner />
      <ErrorText error={error} />

      {!data && !error && <DashboardSkeleton />}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Stat
              label={t("dashboard.services")}
              value={String(data.services.length)}
              sub={`${data.totals.running} ${t("dashboard.running")}`}
            />
            <Stat
              label={t("dashboard.cpuAllocated")}
              value={`${(data.totals.cpuMillicores / 1000).toFixed(1)} ${t("dashboard.cores")}`}
              sub={t("dashboard.inUse", { pct: data.totals.cpuPercent.toFixed(1) })}
            />
            <Stat
              label={t("dashboard.memory")}
              value={`${fmtBytesMb(data.totals.memoryUsedMb)} / ${fmtBytesMb(data.totals.memoryLimitMb)}`}
            />
            <Stat
              label={t("dashboard.storage")}
              value={fmtBytesMb(data.totals.diskMb)}
              sub={t("dashboard.storageLimit", { limit: fmtBytesMb(data.totals.storageLimitMb) })}
            />
            <Stat
              label={t("dashboard.network")}
              value={`${(data.totals.rxKb / 1024).toFixed(1)} MB rx`}
              sub={`${(data.totals.txKb / 1024).toFixed(1)} MB tx`}
            />
          </div>
          <QuotaChart
            cpu={data.totals.cpuPercent}
            memory={
              data.totals.memoryLimitMb > 0
                ? (data.totals.memoryUsedMb / data.totals.memoryLimitMb) * 100
                : 0
            }
            disk={
              data.totals.storageLimitMb > 0
                ? (data.totals.diskMb / data.totals.storageLimitMb) * 100
                : 0
            }
            labels={{
              cpu: t("dashboard.cpuAllocated"),
              memory: t("dashboard.memory"),
              disk: t("dashboard.storage"),
            }}
          />

          {data.alerts.length > 0 && (
            <div className="mt-4 space-y-2">
              {data.alerts.map((a) => {
                const explained = explainError(a.message, locale);
                return (
                  <div
                    key={a.serviceId}
                    className="flex items-center justify-between border px-4 py-3 text-xs"
                    style={{
                      borderRadius: 4,
                      borderColor: "var(--sk-danger)",
                      background: "var(--brique-clair)",
                      color: "var(--text)",
                    }}
                    role="alert"
                  >
                    <span className="flex items-center gap-2">
                      <AlertTriangle size={14} className="shrink-0" />
                      <span>
                        <b>{a.name}</b> — {explained.title}
                        {explained.action ? `. ${explained.action}` : `. ${explained.explanation}`}
                      </span>
                    </span>
                    <Link href={`/dashboard/services/${a.serviceId}?tab=console`} className="btn">
                      {t("dashboard.viewLogs")}
                    </Link>
                  </div>
                );
              })}
            </div>
          )}

          <h2 className="mb-3 mt-7 font-serif text-xl font-bold tracking-tight">
            {t("dashboard.projects")}
          </h2>
          {data.services.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
              {data.services.map((s) => (
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
                  <div className="mt-3 space-y-2 text-[11px] text-[var(--muted)]">
                    <div className="flex justify-between">
                      <span>
                        {t("dashboard.memory")} {fmtBytesMb(s.stats?.memoryMb ?? 0)} /{" "}
                        {fmtBytesMb(s.memoryLimitMb)}
                      </span>
                      <span>CPU {cpuPercentOfQuota(s.stats?.cpuPercent ?? 0, s.cpuLimit).toFixed(1)}%</span>
                    </div>
                    <Bar value={s.stats?.memoryMb ?? 0} max={s.memoryLimitMb} />
                    <div className="truncate font-mono text-[10px]">
                      {s.container
                        ? `${s.container.name} · ${s.container.image}`
                        : t("dashboard.noContainer")}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Server}
              title={t("dashboard.noServices")}
              hint={createHref ? t("dashboard.noServicesHint") : t("services.creationClosed")}
            />
          )}

          <h2 className="mb-3 mt-7 font-serif text-xl font-bold tracking-tight">
            {t("dashboard.activity")}
          </h2>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {data.activity.map((a) => (
              <div key={a.id} className="flex justify-between gap-4 px-4 py-2">
                <span className="min-w-0 truncate">
                  <span className="font-medium text-[var(--text)]" title={a.action}>
                    {auditActionLabel(a.action, locale)}
                  </span>{" "}
                  <span className="text-[var(--muted)]">{a.detail}</span>
                </span>
                <span className="shrink-0 text-[var(--muted)]">
                  {new Date(a.createdAt).toLocaleString(locale === "fr" ? "fr-FR" : "en-US")}
                </span>
              </div>
            ))}
            {data.activity.length === 0 && (
              <div className="px-4 py-3 text-[var(--muted)]">{t("dashboard.noActivityRecorded")}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
