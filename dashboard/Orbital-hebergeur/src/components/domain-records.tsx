"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import type { DnsRecord } from "@/lib/domains/public";

export function DomainRecords({ records }: { records: DnsRecord[] }) {
  const t = useT();
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      setTimeout(() => setCopied(null), 1200);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="text-[var(--muted)]">
          <tr>
            <th className="px-3 py-1.5 font-semibold">{t("service.dnsType")}</th>
            <th className="px-3 py-1.5 font-semibold">{t("service.dnsHost")}</th>
            <th className="px-3 py-1.5 font-semibold">{t("service.dnsValue")}</th>
            <th className="px-3 py-1.5 font-semibold">{t("service.dnsTtl")}</th>
            <th className="px-3 py-1.5 font-semibold" />
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const key = `${r.type}-${r.host}-${r.value}`;
            return (
              <tr key={key} className="border-t border-[var(--line)]">
                <td className="px-3 py-1.5 font-mono">
                  {r.type}
                  {r.recommended && (
                    <span className="ml-1 text-[10px] text-[var(--accent)]">{t("service.dnsRecommended")}</span>
                  )}
                </td>
                <td className="px-3 py-1.5 font-mono">{r.host}</td>
                <td className="px-3 py-1.5 font-mono">
                  {r.value}
                  {r.placeholder && (
                    <div className="mt-0.5 text-[10px] text-[var(--muted)]">{t("service.dnsPlaceholder")}</div>
                  )}
                </td>
                <td className="px-3 py-1.5">{r.ttl}</td>
                <td className="px-3 py-1.5">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={r.placeholder}
                    onClick={() => void copy(r.value, key)}
                  >
                    {copied === key ? t("common.copied") : t("common.copy")}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
