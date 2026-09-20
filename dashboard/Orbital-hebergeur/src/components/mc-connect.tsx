"use client";

import { useState } from "react";
import { Copy, Globe } from "lucide-react";
import { useT } from "@/lib/i18n";
import type { DnsRecord } from "@/lib/domains/public";
import { DomainRecords } from "@/components/domain-records";

export type McConnection = {
  host: string | null;
  javaPort: number;
  bedrockPort: number | null;
  javaAddress: string | null;
  dnsHost: string;
  records: DnsRecord[];
};

function CopyField({ label, value }: { label: string; value: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <div className="label mb-1">{label}</div>
      <div className="flex gap-2">
        <input className="input font-mono" readOnly value={value} spellCheck={false} />
        <button
          type="button"
          className="btn shrink-0"
          onClick={async () => {
            await navigator.clipboard.writeText(value).catch(() => undefined);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          }}
        >
          <Copy size={13} /> {copied ? t("common.copied") : t("common.copy")}
        </button>
      </div>
    </div>
  );
}

export function MinecraftConnect({ connection }: { connection: McConnection }) {
  const t = useT();
  return (
    <div className="panel mt-4 p-4">
      <div className="label">{t("service.connectTitle")}</div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {connection.javaAddress ? (
          <CopyField label={t("service.connectJava")} value={connection.javaAddress} />
        ) : (
          <p className="text-[11px] leading-relaxed text-[var(--muted)]">{t("service.connectNoHost")}</p>
        )}
        {connection.host && connection.bedrockPort != null && (
          <CopyField
            label={t("service.connectBedrock")}
            value={`${connection.host}:${connection.bedrockPort}`}
          />
        )}
      </div>
      <div className="mt-4 rounded-lg border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
        <div className="mb-1 flex items-center gap-1.5 font-semibold text-[var(--text)]">
          <Globe size={12} /> {t("service.connectDnsTitle")}
        </div>
        <p className="mb-1.5">{t("service.connectDnsIntro")}</p>
        <ol className="mb-2 ml-4 list-decimal space-y-0.5">
          <li>{t("service.connectDnsStep1")}</li>
          <li>{t("service.connectDnsStep2")}</li>
          <li>{t("service.connectDnsStep3")}</li>
        </ol>
        <DomainRecords records={connection.records} />
        <p className="mt-1.5">{t("service.connectDnsNote", { host: connection.dnsHost })}</p>
      </div>
    </div>
  );
}
