import { slugify } from "@/lib/crypto";

export const PLACEHOLDER_PUBLIC_DOMAIN = "example.com";
export const DNS_TTL_HINT = 300;

export type DnsRecord = {
  type: "CNAME" | "A" | "AAAA";
  host: string;
  value: string;
  ttl: number;
  recommended: boolean;
  placeholder: boolean;
};

export function publicBaseDomain(): { domain: string; configured: boolean } {
  const raw = (process.env.SYNKRONE_PUBLIC_DOMAIN || process.env.ORBITAL_PUBLIC_DOMAIN)
    ?.trim()
    .toLowerCase()
    .replace(/^\.+|\.+$/g, "");
  if (!raw || raw === PLACEHOLDER_PUBLIC_DOMAIN) {
    return { domain: PLACEHOLDER_PUBLIC_DOMAIN, configured: false };
  }
  return { domain: raw, configured: true };
}

export function suggestedHostname(slugOrName: string): string {
  const slug = slugify(slugOrName);
  return `${slug}.${publicBaseDomain().domain}`;
}

export function normalizeHostname(input: string | null | undefined): string | null {
  if (!input) return null;
  const host = input.trim().toLowerCase().replace(/\.$/, "");
  if (!/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/.test(host)) {
    return null;
  }
  return host;
}

export function isApexHostname(hostname: string): boolean {
  return hostname.split(".").length === 2;
}

export function publicDnsTargets() {
  const cname = (process.env.SYNKRONE_PUBLIC_HOST || process.env.ORBITAL_PUBLIC_HOST)?.trim() || null;
  const ipv4 = (process.env.SYNKRONE_PUBLIC_IP || process.env.ORBITAL_PUBLIC_IP)?.trim() || null;
  const ipv6 = (process.env.SYNKRONE_PUBLIC_IPV6 || process.env.ORBITAL_PUBLIC_IPV6)?.trim() || null;
  return { cname, ipv4, ipv6 };
}

export function dnsRecordsFor(hostname: string): DnsRecord[] {
  const host = normalizeHostname(hostname) ?? hostname;
  const targets = publicDnsTargets();
  const apex = isApexHostname(host);
  const records: DnsRecord[] = [];

  records.push({
    type: "CNAME",
    host,
    value: targets.cname ?? "ORBITAL_PUBLIC_HOST",
    ttl: DNS_TTL_HINT,
    recommended: !apex,
    placeholder: !targets.cname,
  });
  records.push({
    type: "A",
    host,
    value: targets.ipv4 ?? "ORBITAL_PUBLIC_IP",
    ttl: DNS_TTL_HINT,
    recommended: apex || !targets.cname,
    placeholder: !targets.ipv4,
  });
  if (targets.ipv6 || apex) {
    records.push({
      type: "AAAA",
      host,
      value: targets.ipv6 ?? "ORBITAL_PUBLIC_IPV6",
      ttl: DNS_TTL_HINT,
      recommended: apex && !targets.ipv4,
      placeholder: !targets.ipv6,
    });
  }
  return records;
}

export function domainHints(slug: string) {
  const base = publicBaseDomain();
  const suggested = suggestedHostname(slug);
  return {
    suggestedHostname: suggested,
    publicBaseDomain: base.domain,
    domainPendingPurchase: !base.configured,
    targets: publicDnsTargets(),
    records: dnsRecordsFor(suggested),
    ttlHint: DNS_TTL_HINT,
  };
}
