import assert from "node:assert/strict";
import test from "node:test";
import {
  dnsRecordsFor,
  isApexHostname,
  normalizeHostname,
  PLACEHOLDER_PUBLIC_DOMAIN,
  publicBaseDomain,
  suggestedHostname,
} from "../src/lib/domains/public";

test("normalizeHostname lowercases and rejects junk", () => {
  assert.equal(normalizeHostname("Www.Example.COM."), "www.example.com");
  assert.equal(normalizeHostname("not a host"), null);
  assert.equal(normalizeHostname("-bad.com"), null);
});

test("suggested hostname uses the public base domain", () => {
  const prev = process.env.ORBITAL_PUBLIC_DOMAIN;
  try {
    delete process.env.ORBITAL_PUBLIC_DOMAIN;
    assert.equal(publicBaseDomain().configured, false);
    assert.equal(publicBaseDomain().domain, PLACEHOLDER_PUBLIC_DOMAIN);
    assert.equal(suggestedHostname("Site Vitrine"), `site-vitrine.${PLACEHOLDER_PUBLIC_DOMAIN}`);
    process.env.ORBITAL_PUBLIC_DOMAIN = "apps.example.com";
    assert.equal(publicBaseDomain().configured, true);
    assert.equal(suggestedHostname("Site Vitrine"), "site-vitrine.apps.example.com");
  } finally {
    if (prev === undefined) delete process.env.ORBITAL_PUBLIC_DOMAIN;
    else process.env.ORBITAL_PUBLIC_DOMAIN = prev;
  }
});

test("DNS records prefer CNAME on subdomains and A on apex", () => {
  const prevHost = process.env.ORBITAL_PUBLIC_HOST;
  const prevIp = process.env.ORBITAL_PUBLIC_IP;
  try {
    process.env.ORBITAL_PUBLIC_HOST = "edge.example.com";
    process.env.ORBITAL_PUBLIC_IP = "203.0.113.10";
    const sub = dnsRecordsFor("blog.client.fr");
    assert.equal(isApexHostname("blog.client.fr"), false);
    assert.equal(sub.find((r) => r.type === "CNAME")?.recommended, true);
    assert.equal(sub.find((r) => r.type === "CNAME")?.value, "edge.example.com");
    const apex = dnsRecordsFor("client.fr");
    assert.equal(apex.find((r) => r.type === "A")?.recommended, true);
    assert.equal(apex.find((r) => r.type === "CNAME")?.recommended, false);
  } finally {
    if (prevHost === undefined) delete process.env.ORBITAL_PUBLIC_HOST;
    else process.env.ORBITAL_PUBLIC_HOST = prevHost;
    if (prevIp === undefined) delete process.env.ORBITAL_PUBLIC_IP;
    else process.env.ORBITAL_PUBLIC_IP = prevIp;
  }
});
