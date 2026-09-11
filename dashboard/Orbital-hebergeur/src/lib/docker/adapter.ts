import path from "node:path";
import { dataRoot } from "@/lib/paths";
import { docker, engineCapabilities } from "./engine";
import { NETWORKS } from "./networks";

export { NETWORKS };

/**
 * DockerAdapter — the security boundary in front of the Docker Engine API.
 *
 * Container specs are BUILT here from a small, validated description.
 * User-controlled values can never reach the daemon as arbitrary HostConfig
 * fields: privileged, host networking, arbitrary binds, /dev mappings, the
 * docker socket and capability additions are structurally impossible.
 */

export type PortBinding = { containerPort: number; hostPort: number; protocol?: "tcp" | "udp" };

export type ContainerSpec = {
  name: string;
  image: string;
  cmd?: string[];
  entrypoint?: string[];
  env: Record<string, string>;
  workdir?: string;
  /** Host directory must live under the platform data root. */
  volumeHostPath: string;
  volumeMountPath: string;
  networks: string[];
  cpuMillicores: number;
  memoryMb: number;
  storageMb?: number;
  ports?: PortBinding[];
  restartPolicy: "no" | "on-failure" | "always";
  maxRestarts?: number;
  user?: string;
  labels?: Record<string, string>;
  readOnlyRootfs?: boolean;
  /** Resolved from the engine flavour; never user supplied. */
  usernsMode?: string;
};

const FORBIDDEN_ENV_KEYS = [
  "DOCKER_HOST",
  "DOCKER_SOCKET",
  "LD_PRELOAD",
  "PATH",
];

export class DockerPolicyError extends Error {}

function assertSafeVolume(hostPath: string) {
  const root = path.resolve(dataRoot());
  const resolved = path.resolve(hostPath);
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    throw new DockerPolicyError(
      `Refused bind mount outside of the platform data root: ${hostPath}`,
    );
  }
  if (resolved === "/" || resolved.startsWith("/var/run") || resolved.startsWith("/dev")) {
    throw new DockerPolicyError(`Refused dangerous bind mount: ${hostPath}`);
  }
}

function sanitizeEnv(env: Record<string, string>): string[] {
  return Object.entries(env)
    .filter(([k]) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(k))
    .filter(([k]) => !FORBIDDEN_ENV_KEYS.includes(k.toUpperCase()))
    .map(([k, v]) => `${k}=${v}`);
}

export function buildContainerSpec(spec: ContainerSpec): Record<string, unknown> {
  assertSafeVolume(spec.volumeHostPath);
  if (!spec.volumeMountPath.startsWith("/") || spec.volumeMountPath === "/") {
    throw new DockerPolicyError("Invalid container mount path");
  }
  if (spec.cpuMillicores < 100 || spec.cpuMillicores > 16_000) {
    throw new DockerPolicyError("CPU limit out of allowed range (0.1 - 16 cores)");
  }
  if (spec.memoryMb < 64 || spec.memoryMb > 65_536) {
    throw new DockerPolicyError("Memory limit out of allowed range (64MB - 64GB)");
  }

  const exposedPorts: Record<string, Record<string, never>> = {};
  const portBindings: Record<string, Array<{ HostPort: string }>> = {};
  for (const p of spec.ports ?? []) {
    if (p.hostPort < 1024 || p.hostPort > 65535)
      throw new DockerPolicyError("Host port must be between 1024 and 65535");
    const key = `${p.containerPort}/${p.protocol ?? "tcp"}`;
    exposedPorts[key] = {};
    portBindings[key] = [{ HostPort: String(p.hostPort) }];
  }

  const [primaryNetwork, ...extraNetworks] = spec.networks;

  return {
    Image: spec.image,
    Cmd: spec.cmd,
    Entrypoint: spec.entrypoint,
    Env: sanitizeEnv(spec.env),
    WorkingDir: spec.workdir,
    User: spec.user ?? "1000:1000",
    Tty: false,
    OpenStdin: true,
    StdinOnce: false,
    AttachStdin: true,
    ExposedPorts: exposedPorts,
    Labels: {
      "orbital.managed": "true",
      ...(spec.labels ?? {}),
    },
    HostConfig: {
      // ":z" relabels the volume for SELinux hosts (Fedora/RHEL), where an
      // unlabelled bind mount is unreadable from inside the container. The flag
      // is ignored by engines running without SELinux.
      Binds: [`${spec.volumeHostPath}:${spec.volumeMountPath}:rw,z`],
      NetworkMode: primaryNetwork,
      PortBindings: portBindings,
      // Hard resource limits — really enforced by the kernel via cgroups.
      Memory: spec.memoryMb * 1024 * 1024,
      MemorySwap: spec.memoryMb * 1024 * 1024,
      NanoCpus: spec.cpuMillicores * 1_000_000,
      PidsLimit: 512,
      RestartPolicy: {
        Name: spec.restartPolicy,
        MaximumRetryCount:
          spec.restartPolicy === "on-failure" ? (spec.maxRestarts ?? 5) : 0,
      },
      // Hardening — non negotiable, never user configurable.
      Privileged: false,
      CapDrop: ["ALL"],
      CapAdd: [],
      SecurityOpt: ["no-new-privileges:true"],
      ReadonlyRootfs: spec.readOnlyRootfs ?? false,
      Devices: [],
      IpcMode: "private",
      UsernsMode: spec.usernsMode ?? "",
      Tmpfs: { "/tmp": "rw,noexec,nosuid,size=64m" },
      LogConfig: { Type: "json-file", Config: { "max-size": "10m", "max-file": "3" } },
    },
    NetworkingConfig: {
      EndpointsConfig: Object.fromEntries(
        [primaryNetwork, ...extraNetworks].filter(Boolean).map((n) => [n, {}]),
      ),
    },
  };
}

/**
 * Rootless Podman gives each container a private uid range, so uid 1000 inside
 * the container is not the uid owning the volume on the host and every write is
 * denied. "keep-id" maps them onto each other. Docker has no such mode and
 * rejects the value, hence the probe.
 */
async function resolveUsernsMode(): Promise<string> {
  const { podman, rootless } = await engineCapabilities();
  return podman && rootless ? "keep-id" : "";
}

/** ContainerManager — every Docker mutation in the platform funnels through this. */
export const ContainerManager = {
  async ensureNetworks(names: string[]): Promise<void> {
    for (const name of names) await docker.ensureNetwork(name);
  },
  async createContainer(spec: ContainerSpec): Promise<string> {
    const payload = buildContainerSpec({
      ...spec,
      usernsMode: spec.usernsMode ?? (await resolveUsernsMode()),
    });
    await this.ensureNetworks(spec.networks);
    const res = await docker.createContainer(spec.name, payload);
    return res.Id;
  },
  pullImage: (image: string) => docker.pullImage(image),
  startContainer: (id: string) => docker.start(id),
  stopContainer: (id: string, timeout?: number) => docker.stop(id, timeout ?? 20),
  restartContainer: (id: string, timeout?: number) => docker.restart(id, timeout ?? 20),
  killContainer: (id: string) => docker.kill(id),
  removeContainer: (id: string) => docker.remove(id),
  getContainerLogs: (id: string, tail = 200) => docker.logs(id, tail),
  followContainerLogs: (id: string, signal?: AbortSignal) => docker.followLogs(id, signal),
  getContainerStats: (id: string) => docker.statsOnce(id),
  inspect: (id: string) => docker.inspect(id),
  execCommand: (id: string, cmd: string[]) => docker.exec(id, cmd),
  writeStdin: (id: string, data: string) => docker.attachStdin(id, data),
};
