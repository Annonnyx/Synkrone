"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy, Eye, EyeOff, HardDrive } from "lucide-react";
import { useT } from "@/lib/i18n";

export const SFTP_PASSWORD_HREF = "/dashboard/account/profile#password";

function CopyField({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
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
      {hint && <div className="mt-1 text-[11px] text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

export function SftpHowTo() {
  const t = useT();
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
      <div className="mb-1 flex items-center gap-1.5 font-semibold text-[var(--text)]">
        <HardDrive size={12} /> {t("sftp.howTitle")}
      </div>
      <p className="mb-1.5">{t("sftp.howIntro")}</p>
      <ol className="ml-4 list-decimal space-y-0.5">
        <li>{t("sftp.step1")}</li>
        <li>{t("sftp.step2")}</li>
        <li>{t("sftp.step3")}</li>
        <li>{t("sftp.step4")}</li>
      </ol>
    </div>
  );
}

export function SftpPasswordHint() {
  const t = useT();
  const [value, setValue] = useState("");
  const [reveal, setReveal] = useState(false);
  return (
    <div>
      <div className="label mb-1">{t("sftp.password")}</div>
      <div className="flex gap-2">
        <input
          className="input font-mono"
          type={reveal ? "text" : "password"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("sftp.passwordPlaceholder")}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="button"
          className="btn shrink-0"
          onClick={() => setReveal(!reveal)}
          title={reveal ? t("common.close") : t("common.view")}
        >
          {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--muted)]">
        {t("sftp.passwordHelp")}{" "}
        <Link href={SFTP_PASSWORD_HREF} className="text-[var(--accent)] hover:underline">
          {t("sftp.changePassword")}
        </Link>
      </p>
    </div>
  );
}

export function SftpFields({
  host,
  port,
  username,
  chroot,
}: {
  host: string;
  port: number;
  username: string;
  chroot?: string;
}) {
  const t = useT();
  return (
    <div className="space-y-3">
      <CopyField label={t("sftp.protocol")} value={t("sftp.protocolValue")} />
      <CopyField label={t("sftp.host")} value={host} />
      <CopyField label={t("sftp.port")} value={String(port)} />
      <CopyField label={t("sftp.username")} value={username} hint={t("sftp.usernameHint")} />
      {chroot && (
        <CopyField label={t("sftp.chroot")} value={chroot} hint={t("sftp.chrootHint")} />
      )}
    </div>
  );
}
