import type { ServiceType } from "@/lib/paths";

export type LifecycleState =
  | "CREATING"
  | "STARTING"
  | "RUNNING"
  | "STOPPING"
  | "STOPPED"
  | "RESTARTING"
  | "CRASHED"
  | "ERROR"
  | "DELETING"
  | "SUSPENDED";

export type ServiceStatus = {
  state: LifecycleState;
  dockerStatus?: string;
  exitCode?: number;
  restartCount?: number;
  startedAt?: string | null;
  message?: string;
};

export type ResourceStats = {
  cpuPercent: number;
  memoryMb: number;
  memoryLimitMb: number;
  networkRxKb: number;
  networkTxKb: number;
  diskMb: number;
  uptimeSeconds: number;
  restartCount: number;
  available: boolean;
  reason?: string;
};

export type VolumeDefinition = {
  hostPath: string;
  mountPath: string;
};

/** §70 — Docker image template descriptor. */
export type RuntimeTemplate = {
  id: string;
  type: ServiceType;
  label: string;
  image: string;
  defaultPort?: number;
  environment: Record<string, string>;
  mountPath: string;
  command?: string[];
  user?: string;
  networks: string[];
};

export type ServiceRecord = {
  id: string;
  type: ServiceType;
  name: string;
  slug: string;
  ownerId: string;
  projectId: string;
  cpuLimit: number;
  memoryLimitMb: number;
  storageLimitMb: number;
  restartPolicy: string;
  maxRestarts: number;
};

/** §41 — the contract every runtime family implements. */
export interface RuntimeProvider {
  readonly type: ServiceType;
  scaffold(service: ServiceRecord): Promise<void>;
  /** Write prefix / slash / env files without recopying the bot tree. */
  syncPlatformRuntime?(service: ServiceRecord): Promise<void>;
  create(service: ServiceRecord): Promise<{ containerId: string; image: string }>;
  start(serviceId: string): Promise<void>;
  stop(serviceId: string): Promise<void>;
  restart(serviceId: string): Promise<void>;
  kill(serviceId: string): Promise<void>;
  remove(serviceId: string): Promise<void>;
  status(serviceId: string): Promise<ServiceStatus>;
  logs(serviceId: string, tail?: number): Promise<string>;
  followLogs(
    serviceId: string,
    signal?: AbortSignal,
  ): Promise<AsyncIterable<{ stream: "stdout" | "stderr"; text: string }>>;
  stats(serviceId: string): Promise<ResourceStats>;
  sendCommand(serviceId: string, command: string): Promise<string>;
}
