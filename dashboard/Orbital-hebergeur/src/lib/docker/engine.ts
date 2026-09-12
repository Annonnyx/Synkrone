import http from "node:http";
import net from "node:net";
import { existsSync } from "node:fs";
import { Readable } from "node:stream";
import { StringDecoder } from "node:string_decoder";

/**
 * Minimal, dependency-free Docker Engine API client.
 * It speaks HTTP over the unix socket (or a tcp endpoint through DOCKER_HOST).
 * This module is the ONLY place in the codebase that talks to the Docker daemon,
 * and it is server-only: nothing here is ever bundled for the browser.
 */

export const DOCKER_SOCKET = process.env.DOCKER_SOCKET ?? "/var/run/docker.sock";
const API_VERSION = "v1.43";

export class DockerUnavailableError extends Error {
  constructor(detail: string) {
    super(
      `Docker Engine is not reachable at ${DOCKER_SOCKET} (${detail}). ` +
        `Start the platform with docker-compose (see docker/README) so the control API can reach the daemon.`,
    );
    this.name = "DockerUnavailableError";
  }
}

export class DockerApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "DockerApiError";
  }
}

export function dockerSocketPresent(): boolean {
  try {
    return existsSync(DOCKER_SOCKET);
  } catch {
    return false;
  }
}

type RequestOptions = {
  method?: string;
  path: string;
  body?: unknown;
  raw?: boolean;
  timeoutMs?: number;
};

function request(opts: RequestOptions): Promise<{ status: number; body: Buffer }> {
  const payload = opts.body === undefined ? undefined : JSON.stringify(opts.body);
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        socketPath: DOCKER_SOCKET,
        path: `/${API_VERSION}${opts.path}`,
        method: opts.method ?? "GET",
        headers: {
          "Content-Type": "application/json",
          ...(payload ? { "Content-Length": Buffer.byteLength(payload) } : {}),
        },
        timeout: opts.timeoutMs ?? 30_000,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () =>
          resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks) }),
        );
      },
    );
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", (err) => reject(new DockerUnavailableError(err.message)));
    if (payload) req.write(payload);
    req.end();
  });
}

/** Docker-compatible daemons report failures as `{ "message": "..." }`. */
function apiMessage(text: string): string {
  try {
    return (JSON.parse(text) as { message?: string }).message ?? text;
  } catch {
    return text;
  }
}

async function json<T>(opts: RequestOptions): Promise<T> {
  const res = await request(opts);
  const text = res.body.toString("utf8");
  if (res.status >= 400) throw new DockerApiError(res.status, apiMessage(text));
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

/**
 * Progress endpoints answer with newline-delimited JSON instead of a single
 * document, and report failures in an `error` field while still returning 200.
 */
function streamError(text: string): string | null {
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const parsed = JSON.parse(trimmed) as { error?: string };
      if (parsed.error) return parsed.error;
    } catch {
      /* non-JSON progress output */
    }
  }
  return null;
}

/**
 * A frame header is a stream type (0-2), three zero bytes, then a big-endian
 * payload length. A TTY-enabled container emits no header at all, so the shape
 * of the first bytes is the only way to tell the two encodings apart. The probe
 * must happen once for the whole stream: deciding again on a later offset would
 * mistake payload text for a corrupt header.
 */
function framedStream(buf: Buffer): boolean {
  return buf.length >= 8 && buf[0] <= 2 && buf[1] === 0 && buf[2] === 0 && buf[3] === 0;
}

export type DemuxedOutput = { combined: string; stdout: string; stderr: string };

/** Splits a complete multiplexed payload, keeping stdout and stderr apart. */
export function demuxDockerFrames(buf: Buffer): DemuxedOutput {
  if (!framedStream(buf)) {
    const text = buf.toString("utf8");
    return { combined: text, stdout: text, stderr: "" };
  }
  const out: DemuxedOutput = { combined: "", stdout: "", stderr: "" };
  let offset = 0;
  while (offset + 8 <= buf.length) {
    const type = buf[offset];
    const end = offset + 8 + buf.readUInt32BE(offset + 4);
    const text = buf.subarray(offset + 8, Math.min(end, buf.length)).toString("utf8");
    out.combined += text;
    if (type === 2) out.stderr += text;
    else out.stdout += text;
    if (end > buf.length) break;
    offset = end;
  }
  return out;
}

/** Docker multiplexed stream de-framing (8 byte header per frame). */
export function demuxDockerStream(buf: Buffer): string {
  return demuxDockerFrames(buf).combined;
}

export type LogPiece = { stream: "stdout" | "stderr"; text: string };

/**
 * Frame-aware decoder for a live stream. The daemon cuts frames at arbitrary
 * transport boundaries, so a chunk routinely starts mid-payload or holds only
 * part of a header; decoding each chunk on its own would emit the header bytes
 * as text and split log lines. The incomplete tail is kept until it completes.
 */
export function createFramedLogDecoder(): (chunk: Buffer) => LogPiece[] {
  const stdoutDec = new StringDecoder("utf8");
  const stderrDec = new StringDecoder("utf8");
  let pending: Buffer = Buffer.alloc(0);
  let framed: boolean | null = null;
  return (chunk) => {
    pending = pending.length ? Buffer.concat([pending, chunk]) : Buffer.from(chunk);
    if (framed === null) {
      if (pending.length < 8) return [];
      framed = framedStream(pending);
    }
    if (!framed) {
      const text = stdoutDec.write(pending);
      pending = Buffer.alloc(0);
      return text ? [{ stream: "stdout", text }] : [];
    }
    const pieces: LogPiece[] = [];
    let offset = 0;
    while (offset + 8 <= pending.length) {
      const type = pending[offset] ?? 1;
      const end = offset + 8 + pending.readUInt32BE(offset + 4);
      if (end > pending.length) break;
      const decoder = type === 2 ? stderrDec : stdoutDec;
      const text = decoder.write(pending.subarray(offset + 8, end));
      if (text) pieces.push({ stream: type === 2 ? "stderr" : "stdout", text });
      offset = end;
    }
    if (offset) pending = pending.subarray(offset);
    return pieces;
  };
}

export function createFrameDecoder(): (chunk: Buffer) => string {
  const decode = createFramedLogDecoder();
  return (chunk) => decode(chunk).map((piece) => piece.text).join("");
}

export type ContainerInspect = {
  Id: string;
  Name: string;
  State: {
    Status: string;
    Running: boolean;
    Restarting: boolean;
    ExitCode: number;
    Error: string;
    StartedAt: string;
    FinishedAt: string;
    OOMKilled: boolean;
  };
  RestartCount: number;
  Config: { Image: string; Env?: string[] };
};

/**
 * Fields are optional because the very first sample of a container has no
 * previous CPU reading, and Docker-compatible engines omit blocks they cannot
 * report.
 */
export type DockerStats = {
  cpu_stats?: {
    cpu_usage?: { total_usage?: number; percpu_usage?: number[] };
    system_cpu_usage?: number;
    online_cpus?: number;
  };
  precpu_stats?: {
    cpu_usage?: { total_usage?: number };
    system_cpu_usage?: number;
  };
  memory_stats?: { usage?: number; limit?: number };
  networks?: Record<string, { rx_bytes?: number; tx_bytes?: number }>;
};

export type EngineCapabilities = { podman: boolean; rootless: boolean };

let capabilities: Promise<EngineCapabilities> | null = null;

/**
 * Podman and Docker expose the same API but not the same user-namespace
 * behaviour, and that difference decides whether a container may write to its
 * bind-mounted volume. Probed once and cached for the process lifetime.
 */
export function engineCapabilities(): Promise<EngineCapabilities> {
  capabilities ??= (async () => {
    try {
      const version = await json<{ Components?: Array<{ Name: string }> }>({
        path: "/version",
        timeoutMs: 4000,
      });
      const info = await json<{ SecurityOptions?: string[] }>({
        path: "/info",
        timeoutMs: 4000,
      });
      return {
        podman: (version.Components ?? []).some((c) => /podman/i.test(c.Name)),
        rootless: (info.SecurityOptions ?? []).some((o) => o.includes("rootless")),
      };
    } catch {
      return { podman: false, rootless: false };
    }
  })();
  return capabilities;
}

export type ExecResult = DemuxedOutput & { exitCode: number | null };

/**
 * Live attach connections, one per container.
 *
 * The engine sends EOF to the container's stdin as soon as the last attach
 * client detaches, so opening a connection per command would let the first
 * command through and silently drop every later one. The handshake is also
 * written by hand: the http client would frame the body with chunked transfer
 * encoding, and on a hijacked connection those chunk size lines are forwarded
 * straight into the container's stdin as if they were typed commands.
 */
const attachSockets = new Map<string, net.Socket>();
const attachPending = new Map<string, Promise<net.Socket>>();

function connectAttach(id: string): Promise<net.Socket> {
  return new Promise((resolve, reject) => {
    const socket = net.connect(DOCKER_SOCKET);
    let head = "";
    let settled = false;
    const failure = (err: Error) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      reject(err);
    };
    socket.on("connect", () => {
      socket.write(
        [
          `POST /${API_VERSION}/containers/${id}/attach?stream=true&stdin=true HTTP/1.1`,
          "Host: docker",
          "Content-Type: application/vnd.docker.raw-stream",
          "Connection: Upgrade",
          "Upgrade: tcp",
          "Content-Length: 0",
          "",
          "",
        ].join("\r\n"),
      );
    });
    socket.on("data", (chunk: Buffer) => {
      if (settled) return;
      head += chunk.toString("latin1");
      const end = head.indexOf("\r\n\r\n");
      if (end < 0) return;
      const status = Number(head.slice(9, 12));
      if (!status || status >= 400) {
        failure(
          new DockerApiError(
            status || 500,
            apiMessage(head.slice(end + 4)) || `attach refused with status ${status}`,
          ),
        );
        return;
      }
      settled = true;
      socket.setTimeout(0);
      resolve(socket);
    });
    socket.on("error", (err) => failure(new DockerUnavailableError(err.message)));
    socket.on("close", () => failure(new DockerUnavailableError("attach connection closed")));
    socket.setTimeout(15_000, () => failure(new DockerUnavailableError("attach handshake timed out")));
  });
}

function attachSession(id: string): Promise<net.Socket> {
  const live = attachSockets.get(id);
  if (live && !live.destroyed && !live.writableEnded) return Promise.resolve(live);
  attachSockets.delete(id);

  const inflight = attachPending.get(id);
  if (inflight) return inflight;

  const pending = connectAttach(id);
  attachPending.set(id, pending);
  void pending
    .then((socket) => {
      attachSockets.set(id, socket);
      const drop = () => {
        if (attachSockets.get(id) === socket) attachSockets.delete(id);
      };
      socket.on("close", drop);
      socket.on("error", drop);
    })
    .catch(() => undefined)
    .finally(() => {
      if (attachPending.get(id) === pending) attachPending.delete(id);
    });
  return pending;
}

export const docker = {
  async ping(): Promise<{ ok: boolean; version?: string; error?: string }> {
    if (!dockerSocketPresent()) {
      return { ok: false, error: `socket ${DOCKER_SOCKET} not found` };
    }
    try {
      const info = await json<{ Version: string }>({ path: "/version", timeoutMs: 4000 });
      return { ok: true, version: info.Version };
    } catch (err) {
      return { ok: false, error: (err as Error).message };
    }
  },

  info: () => json<Record<string, unknown>>({ path: "/info" }),

  listNetworks: () => json<Array<{ Name: string; Id: string }>>({ path: "/networks" }),

  async ensureNetwork(name: string, internal = false): Promise<void> {
    const nets = await this.listNetworks();
    if (nets.some((n) => n.Name === name)) return;
    await json({
      method: "POST",
      path: "/networks/create",
      body: {
        Name: name,
        Driver: "bridge",
        Internal: internal,
        Labels: { "orbital.managed": "true" },
      },
    });
  },

  async pullImage(image: string): Promise<void> {
    const res = await request({
      method: "POST",
      path: `/images/create?fromImage=${encodeURIComponent(image)}`,
      timeoutMs: 600_000,
    });
    const text = res.body.toString("utf8");
    const failure = streamError(text);
    if (res.status >= 400) throw new DockerApiError(res.status, failure ?? text);
    if (failure) throw new DockerApiError(500, failure);
  },

  createContainer: (name: string, spec: Record<string, unknown>) =>
    json<{ Id: string; Warnings?: string[] }>({
      method: "POST",
      path: `/containers/create?name=${encodeURIComponent(name)}`,
      body: spec,
    }),

  start: (id: string) =>
    json({ method: "POST", path: `/containers/${id}/start` }).catch((e) => {
      if (e instanceof DockerApiError && e.status === 304) return null;
      throw e;
    }),

  stop: (id: string, timeout = 20) =>
    json({ method: "POST", path: `/containers/${id}/stop?t=${timeout}`, timeoutMs: 60_000 }),

  restart: (id: string, timeout = 20) =>
    json({
      method: "POST",
      path: `/containers/${id}/restart?t=${timeout}`,
      timeoutMs: 60_000,
    }),

  kill: (id: string) => json({ method: "POST", path: `/containers/${id}/kill` }),

  remove: (id: string) =>
    json({ method: "DELETE", path: `/containers/${id}?force=true&v=true` }),

  inspect: (id: string) => json<ContainerInspect>({ path: `/containers/${id}/json` }),

  async statsOnce(id: string): Promise<DockerStats> {
    const first = await json<DockerStats>({
      path: `/containers/${id}/stats?stream=false`,
      timeoutMs: 15_000,
    });
    if (cpuSampleReady(first)) return first;
    await new Promise((resolve) => setTimeout(resolve, 350));
    const second = await json<DockerStats>({
      path: `/containers/${id}/stats?stream=false`,
      timeoutMs: 15_000,
    });
    return mergeCpuSamples(first, second);
  },

  async logs(id: string, tail = 200): Promise<string> {
    const res = await request({
      path: `/containers/${id}/logs?stdout=true&stderr=true&timestamps=true&tail=${tail}`,
      timeoutMs: 20_000,
    });
    if (res.status >= 400) throw new DockerApiError(res.status, res.body.toString("utf8"));
    return demuxDockerStream(res.body);
  },

  /**
   * Streams container logs as an async iterable of decoded chunks. The promise
   * settles on the daemon's response headers so that a missing or unreadable
   * container rejects here, instead of the error body being handed to the caller
   * as if the container had printed it.
   */
  followLogs(id: string, signal?: AbortSignal): Promise<AsyncIterable<LogPiece>> {
    return new Promise((resolve, reject) => {
      const req = http.request({
        socketPath: DOCKER_SOCKET,
        path: `/${API_VERSION}/containers/${id}/logs?stdout=true&stderr=true&follow=true&timestamps=true&tail=100`,
        method: "GET",
      });
      let stream: Readable | null = null;
      const abort = () => {
        req.destroy();
        stream?.push(null);
      };
      if (signal?.aborted) {
        req.destroy();
        reject(new DockerUnavailableError("log stream aborted before it started"));
        return;
      }
      signal?.addEventListener("abort", abort, { once: true });

      req.on("response", (res) => {
        const status = res.statusCode ?? 0;
        if (status >= 400) {
          const chunks: Buffer[] = [];
          res.on("data", (c: Buffer) => chunks.push(c));
          res.on("end", () =>
            reject(new DockerApiError(status, apiMessage(Buffer.concat(chunks).toString("utf8")))),
          );
          return;
        }
        const decode = createFramedLogDecoder();
        const out = new Readable({ objectMode: true, read() {} });
        stream = out;
        res.on("data", (chunk: Buffer) => {
          for (const piece of decode(chunk)) out.push(piece);
        });
        res.on("end", () => out.push(null));
        res.on("error", () => out.push(null));
        resolve(out as unknown as AsyncIterable<LogPiece>);
      });
      req.on("error", (err) => reject(new DockerUnavailableError(err.message)));
      req.end();
    });
  },

  async exec(id: string, cmd: string[]): Promise<ExecResult> {
    const created = await json<{ Id: string }>({
      method: "POST",
      path: `/containers/${id}/exec`,
      body: { AttachStdout: true, AttachStderr: true, Tty: false, Cmd: cmd },
    });
    const res = await request({
      method: "POST",
      path: `/exec/${created.Id}/start`,
      body: { Detach: false, Tty: false },
      timeoutMs: 60_000,
    });
    if (res.status >= 400) {
      throw new DockerApiError(res.status, apiMessage(res.body.toString("utf8")));
    }
    const output = demuxDockerFrames(res.body);
    const inspected = await json<{ ExitCode: number | null }>({
      path: `/exec/${created.Id}/json`,
    }).catch(() => ({ ExitCode: null }));
    return { ...output, exitCode: inspected.ExitCode };
  },

  /** Writes bytes to the container's stdin (used for Minecraft console commands). */
  async attachStdin(id: string, data: string): Promise<void> {
    const payload = Buffer.from(data.endsWith("\n") ? data : `${data}\n`, "utf8");
    // One retry: a pooled socket is sometimes found dead only when writing to it,
    // and attachSession() reconnects once the dead one has been evicted.
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const socket = await attachSession(id);
      if (socket.destroyed || socket.writableEnded) continue;
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new DockerUnavailableError("timed out writing to container stdin"));
        }, 8_000);
        socket.write(payload, (err) => {
          clearTimeout(timer);
          err ? reject(new DockerUnavailableError(err.message)) : resolve();
        });
      });
      return;
    }
    throw new DockerUnavailableError("the attach connection to the container keeps closing");
  },
};

export function cpuSampleReady(stats: DockerStats): boolean {
  const preSys = stats.precpu_stats?.system_cpu_usage ?? 0;
  if (preSys <= 0) return false;
  const cpuDelta =
    (stats.cpu_stats?.cpu_usage?.total_usage ?? 0) -
    (stats.precpu_stats?.cpu_usage?.total_usage ?? 0);
  const systemDelta = (stats.cpu_stats?.system_cpu_usage ?? 0) - preSys;
  return cpuDelta > 0 && systemDelta > 0;
}

/** Podman often answers stream=false with an empty precpu block. Reuse the previous sample. */
export function mergeCpuSamples(previous: DockerStats, next: DockerStats): DockerStats {
  if (cpuSampleReady(next)) return next;
  return {
    ...next,
    precpu_stats: {
      cpu_usage: { total_usage: previous.cpu_stats?.cpu_usage?.total_usage ?? 0 },
      system_cpu_usage: previous.cpu_stats?.system_cpu_usage ?? 0,
    },
  };
}

/** Docker's formula: 100 = one core fully used. */
export function computeCpuPercent(stats: DockerStats): number {
  const cpuDelta =
    (stats.cpu_stats?.cpu_usage?.total_usage ?? 0) -
    (stats.precpu_stats?.cpu_usage?.total_usage ?? 0);
  const systemDelta =
    (stats.cpu_stats?.system_cpu_usage ?? 0) - (stats.precpu_stats?.system_cpu_usage ?? 0);
  if (cpuDelta <= 0 || systemDelta <= 0) return 0;
  const cpus =
    stats.cpu_stats?.online_cpus ?? stats.cpu_stats?.cpu_usage?.percpu_usage?.length ?? 1;
  return (cpuDelta / systemDelta) * cpus * 100;
}

