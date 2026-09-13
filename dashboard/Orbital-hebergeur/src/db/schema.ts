import { randomUUID } from "node:crypto";
import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

const id = () =>
  text("id")
    .primaryKey()
    .$defaultFn(() => randomUUID());

const createdAt = () =>
  timestamp("created_at", { withTimezone: true }).notNull().defaultNow();

/* ------------------------------------------------------------------ */
/* Identity                                                            */
/* ------------------------------------------------------------------ */

export const users = pgTable(
  "users",
  {
    id: id(),
    email: text("email").notNull(),
    name: text("name").notNull(),
    avatarUrl: text("avatar_url"),
    passwordHash: text("password_hash"),
    role: text("role").notNull().default("user"), // user | admin
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("users_email_uq").on(t.email)],
);

export const oauthAccounts = pgTable(
  "oauth_accounts",
  {
    id: id(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    provider: text("provider").notNull(), // discord | google | github
    providerAccountId: text("provider_account_id").notNull(),
    providerLogin: text("provider_login"),
    email: text("email"),
    avatarUrl: text("avatar_url"),
    accessTokenEnc: text("access_token_enc"),
    refreshTokenEnc: text("refresh_token_enc"),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    scope: text("scope"),
    createdAt: createdAt(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    uniqueIndex("oauth_provider_account_uq").on(t.provider, t.providerAccountId),
    uniqueIndex("oauth_user_provider_uq").on(t.userId, t.provider),
  ],
);

export const sessions = pgTable(
  "sessions",
  {
    id: id(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    tokenHash: text("token_hash").notNull(),
    ip: text("ip"),
    userAgent: text("user_agent"),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("sessions_token_uq").on(t.tokenHash)],
);

/* ------------------------------------------------------------------ */
/* Compute nodes (multi-node ready)                                    */
/* ------------------------------------------------------------------ */

export const nodes = pgTable("nodes", {
  id: id(),
  name: text("name").notNull(),
  hostname: text("hostname").notNull(),
  dockerEndpoint: text("docker_endpoint").notNull().default("/var/run/docker.sock"),
  cpuCapacity: integer("cpu_capacity").notNull().default(8),
  memoryCapacityMb: integer("memory_capacity_mb").notNull().default(16384),
  storageCapacityMb: integer("storage_capacity_mb").notNull().default(512000),
  status: text("status").notNull().default("unknown"), // online | offline | unknown
  lastSeenAt: timestamp("last_seen_at", { withTimezone: true }),
  createdAt: createdAt(),
});

/* ------------------------------------------------------------------ */
/* Projects & services                                                 */
/* ------------------------------------------------------------------ */

export const projects = pgTable("projects", {
  id: id(),
  ownerId: text("owner_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  description: text("description"),
  createdAt: createdAt(),
});

export const projectMembers = pgTable(
  "project_members",
  {
    id: id(),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    role: text("role").notNull().default("member"), // owner | admin | member | viewer
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("project_member_uq").on(t.projectId, t.userId)],
);

export const services = pgTable(
  "services",
  {
    id: id(),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    ownerId: text("owner_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    nodeId: text("node_id").references(() => nodes.id, { onDelete: "set null" }),
    type: text("type").notNull(), // discord | minecraft | web
    name: text("name").notNull(),
    slug: text("slug").notNull(),
    description: text("description"),
    iconUrl: text("icon_url"),
    state: text("state").notNull().default("CREATING"),
    lastError: text("last_error"),
    cpuLimit: integer("cpu_limit_millicores").notNull().default(1000),
    memoryLimitMb: integer("memory_limit_mb").notNull().default(512),
    storageLimitMb: integer("storage_limit_mb").notNull().default(5120),
    restartPolicy: text("restart_policy").notNull().default("on-failure"),
    maxRestarts: integer("max_restarts").notNull().default(5),
    createdAt: createdAt(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [
    index("services_owner_idx").on(t.ownerId),
    uniqueIndex("services_slug_uq").on(t.slug),
  ],
);

export const discordBots = pgTable("discord_bots", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  tokenEnc: text("token_enc"),
  tokenFingerprint: text("token_fingerprint"),
  applicationId: text("application_id"),
  flavor: text("flavor").notNull().default("custom"),
  prefix: text("prefix").notNull().default("!"),
  slashCommands: boolean("slash_commands").notNull().default(true),
  intents: jsonb("intents").$type<string[]>().notNull().default([]),
  modules: jsonb("modules").$type<string[]>().notNull().default([]),
  commands: jsonb("commands")
    .$type<
      Array<{
        name: string;
        module: string;
        enabled: boolean;
        description: string;
        permission: string;
        cooldown: number;
        response?: string;
        logging: boolean;
      }>
    >()
    .notNull()
    .default([]),
  createdAt: createdAt(),
});

export const minecraftServers = pgTable("minecraft_servers", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  software: text("software").notNull(), // vanilla | paper | purpur | spigot | fabric | forge | neoforge | quilt
  version: text("version").notNull(),
  javaPort: integer("java_port").notNull().default(25565),
  bedrockEnabled: boolean("bedrock_enabled").notNull().default(false),
  bedrockPort: integer("bedrock_port").notNull().default(19132),
  eulaAccepted: boolean("eula_accepted").notNull().default(false),
  properties: jsonb("properties").$type<Record<string, string>>().notNull().default({}),
  createdAt: createdAt(),
});

export const minecraftAddons = pgTable("minecraft_addons", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  kind: text("kind").notNull(), // plugin | mod
  name: text("name").notNull(),
  version: text("version"),
  fileName: text("file_name").notNull(),
  enabled: boolean("enabled").notNull().default(true),
  sourceUrl: text("source_url"),
  sizeBytes: integer("size_bytes").notNull().default(0),
  provider: text("provider").notNull().default("manual"), // manual | modrinth
  projectId: text("project_id"),
  versionId: text("version_id"),
  iconUrl: text("icon_url"),
  summary: text("summary"),
  dependency: boolean("dependency").notNull().default(false),
  createdAt: createdAt(),
});

export const webProjects = pgTable("web_projects", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  template: text("template").notNull(), // static | node | react | next | typescript | javascript
  source: text("source").notNull().default("empty"), // empty | github
  repoUrl: text("repo_url"),
  branch: text("branch").notNull().default("main"),
  installCommand: text("install_command"),
  buildCommand: text("build_command"),
  startCommand: text("start_command"),
  autoDeploy: boolean("auto_deploy").notNull().default(false),
  webhookSecretEnc: text("webhook_secret_enc"),
  port: integer("port").notNull().default(3000),
  createdAt: createdAt(),
});

/* ------------------------------------------------------------------ */
/* Containers, deployments                                             */
/* ------------------------------------------------------------------ */

export const containers = pgTable(
  "containers",
  {
    id: id(),
    serviceId: text("service_id")
      .notNull()
      .references(() => services.id, { onDelete: "cascade" }),
    dockerContainerId: text("docker_container_id"),
    containerName: text("container_name").notNull(),
    image: text("image").notNull(),
    network: text("network").notNull(),
    status: text("status").notNull().default("CREATING"),
    cpuLimit: integer("cpu_limit_millicores").notNull().default(1000),
    memoryLimitMb: integer("memory_limit_mb").notNull().default(512),
    restartPolicy: text("restart_policy").notNull().default("on-failure"),
    restartCount: integer("restart_count").notNull().default(0),
    lastError: text("last_error"),
    startedAt: timestamp("started_at", { withTimezone: true }),
    createdAt: createdAt(),
  },
  (t) => [index("containers_service_idx").on(t.serviceId)],
);

export const deployments = pgTable("deployments", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  number: integer("number").notNull().default(1),
  status: text("status").notNull().default("PENDING"), // PENDING RUNNING SUCCESS FAILED ROLLED_BACK
  trigger: text("trigger").notNull().default("manual"), // manual | github | rollback
  commitSha: text("commit_sha"),
  image: text("image"),
  isCurrent: boolean("is_current").notNull().default(false),
  logs: text("logs").notNull().default(""),
  startedAt: createdAt(),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
});

export const envVars = pgTable(
  "environment_variables",
  {
    id: id(),
    serviceId: text("service_id")
      .notNull()
      .references(() => services.id, { onDelete: "cascade" }),
    key: text("key").notNull(),
    valueEnc: text("value_enc").notNull(),
    secret: boolean("secret").notNull().default(false),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("env_service_key_uq").on(t.serviceId, t.key)],
);

/* ------------------------------------------------------------------ */
/* Infrastructure add-ons                                              */
/* ------------------------------------------------------------------ */

export const serviceDatabases = pgTable("service_databases", {
  id: id(),
  ownerId: text("owner_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  serviceId: text("service_id").references(() => services.id, {
    onDelete: "set null",
  }),
  engine: text("engine").notNull().default("postgres"),
  dbName: text("db_name").notNull(),
  dbUser: text("db_user").notNull(),
  passwordEnc: text("password_enc").notNull(),
  host: text("host").notNull(),
  port: integer("port").notNull(),
  status: text("status").notNull().default("READY"),
  createdAt: createdAt(),
});

export const backups = pgTable("backups", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  fileName: text("file_name").notNull(),
  sizeBytes: integer("size_bytes").notNull().default(0),
  status: text("status").notNull().default("PENDING"),
  note: text("note"),
  createdAt: createdAt(),
});

export const sftpCredentials = pgTable("sftp_credentials", {
  id: id(),
  serviceId: text("service_id")
    .notNull()
    .references(() => services.id, { onDelete: "cascade" }),
  username: text("username").notNull(),
  passwordEnc: text("password_enc").notNull(),
  host: text("host").notNull(),
  port: integer("port").notNull().default(2022),
  chroot: text("chroot").notNull(),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: createdAt(),
});

export const domains = pgTable(
  "domains",
  {
    id: id(),
    serviceId: text("service_id")
      .notNull()
      .references(() => services.id, { onDelete: "cascade" }),
    hostname: text("hostname").notNull(),
    kind: text("kind").notNull().default("custom"), // default | custom
    https: boolean("https").notNull().default(true),
    certResolver: text("cert_resolver").notNull().default("letsencrypt"),
    status: text("status").notNull().default("PENDING"),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("domain_hostname_uq").on(t.hostname)],
);

export const apiKeys = pgTable("api_keys", {
  id: id(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  prefix: text("prefix").notNull(),
  keyHash: text("key_hash").notNull(),
  lastUsedAt: timestamp("last_used_at", { withTimezone: true }),
  revokedAt: timestamp("revoked_at", { withTimezone: true }),
  createdAt: createdAt(),
});

export const webhooks = pgTable("webhooks", {
  id: id(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  serviceId: text("service_id").references(() => services.id, {
    onDelete: "cascade",
  }),
  url: text("url").notNull(),
  events: jsonb("events").$type<string[]>().notNull().default([]),
  secretEnc: text("secret_enc"),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: createdAt(),
});

export const auditLogs = pgTable(
  "audit_logs",
  {
    id: id(),
    userId: text("user_id").references(() => users.id, { onDelete: "set null" }),
    projectId: text("project_id"),
    serviceId: text("service_id"),
    action: text("action").notNull(),
    result: text("result").notNull().default("success"),
    detail: text("detail"),
    ip: text("ip"),
    createdAt: createdAt(),
  },
  (t) => [index("audit_user_idx").on(t.userId)],
);

/* ------------------------------------------------------------------ */
/* Job queue (workers)                                                 */
/* ------------------------------------------------------------------ */

export const jobs = pgTable(
  "jobs",
  {
    id: id(),
    type: text("type").notNull(),
    serviceId: text("service_id"),
    userId: text("user_id"),
    status: text("status").notNull().default("QUEUED"), // QUEUED RUNNING SUCCESS FAILED
    progress: integer("progress").notNull().default(0),
    payload: jsonb("payload").$type<Record<string, unknown>>().notNull().default({}),
    error: text("error"),
    createdAt: createdAt(),
    finishedAt: timestamp("finished_at", { withTimezone: true }),
  },
  (t) => [index("jobs_service_idx").on(t.serviceId)],
);

export const jobSteps = pgTable("job_steps", {
  id: id(),
  jobId: text("job_id")
    .notNull()
    .references(() => jobs.id, { onDelete: "cascade" }),
  label: text("label").notNull(),
  status: text("status").notNull().default("PENDING"), // PENDING RUNNING DONE FAILED SKIPPED
  detail: text("detail"),
  position: integer("position").notNull().default(0),
  createdAt: createdAt(),
});

export const consoleLines = pgTable(
  "console_lines",
  {
    id: id(),
    serviceId: text("service_id")
      .notNull()
      .references(() => services.id, { onDelete: "cascade" }),
    stream: text("stream").notNull().default("system"), // system | stdout | stderr | command
    message: text("message").notNull(),
    createdAt: createdAt(),
  },
  (t) => [index("console_service_idx").on(t.serviceId)],
);

/* ------------------------------------------------------------------ */
/* Site profile + Krônes (one account with the panel)                  */
/* ------------------------------------------------------------------ */

export const siteProfiles = pgTable(
  "site_profiles",
  {
    userId: text("user_id")
      .primaryKey()
      .references(() => users.id, { onDelete: "cascade" }),
    publicId: text("public_id").notNull(),
    role: text("role").notNull().default("Krobi"),
    isTeamOwner: boolean("is_team_owner").notNull().default(false),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }),
    lastLoginAt: timestamp("last_login_at", { withTimezone: true }),
    createdAt: createdAt(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
    profile: jsonb("profile").$type<Record<string, unknown>>().notNull().default({}),
  },
  (t) => [uniqueIndex("site_profiles_public_id_uq").on(t.publicId)],
);

export const wallets = pgTable("wallets", {
  userId: text("user_id")
    .primaryKey()
    .references(() => users.id, { onDelete: "cascade" }),
  balance: integer("balance").notNull().default(0),
  plan: text("plan").notNull().default("Aucun"),
  joinBonusAt: timestamp("join_bonus_at", { withTimezone: true }),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const walletLedger = pgTable(
  "wallet_ledger",
  {
    id: id(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    type: text("type").notNull(), // credit | debit
    amount: integer("amount").notNull(),
    reason: text("reason").notNull().default(""),
    at: timestamp("at", { withTimezone: true }).notNull().defaultNow(),
    balanceAfter: integer("balance_after").notNull(),
  },
  (t) => [index("wallet_ledger_user_at_idx").on(t.userId, t.at)],
);

export const metricSamples = pgTable(
  "metric_samples",
  {
    id: id(),
    serviceId: text("service_id")
      .notNull()
      .references(() => services.id, { onDelete: "cascade" }),
    cpuPercent: integer("cpu_percent").notNull().default(0),
    memoryMb: integer("memory_mb").notNull().default(0),
    networkRxKb: integer("network_rx_kb").notNull().default(0),
    networkTxKb: integer("network_tx_kb").notNull().default(0),
    diskMb: integer("disk_mb").notNull().default(0),
    createdAt: createdAt(),
  },
  (t) => [index("metrics_service_idx").on(t.serviceId)],
);
