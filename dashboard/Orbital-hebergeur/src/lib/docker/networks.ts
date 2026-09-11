/** Dedicated, isolated networks per runtime family (§39). Server-agnostic: safe to import from client code. */
export const NETWORKS = {
  dashboard: "orbital-dashboard",
  discord: "orbital-discord",
  minecraft: "orbital-minecraft",
  web: "orbital-web",
  database: "orbital-database",
  proxy: "orbital-proxy",
} as const;
