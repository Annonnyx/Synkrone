import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { MOUNT_POINT, serviceVolume, type ServiceType } from "@/lib/paths";

const exec = promisify(execFile);

export class FilesystemError extends Error {
  status: number;
  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

export type FileEntry = {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number;
  modifiedAt: string;
  mode: string;
};

const MAX_TEXT_BYTES = 2 * 1024 * 1024;

/**
 * FilesystemManager — every path is resolved from the service root that the
 * control API derived from the *authenticated* serviceId (§43, §44, §73).
 * Path traversal, absolute escapes and symlink escapes are all rejected.
 */
export class FilesystemManager {
  readonly root: string;
  readonly mountPoint: string;

  constructor(type: ServiceType, serviceId: string) {
    this.root = serviceVolume(type, serviceId);
    this.mountPoint = MOUNT_POINT[type];
  }

  private async resolve(relative: string, mustExist = false): Promise<string> {
    const clean = (relative ?? "").replace(/^\/+/, "");
    if (clean.split("/").some((seg) => seg === "..")) {
      throw new FilesystemError("Path traversal is not allowed", 403);
    }
    const target = path.resolve(this.root, clean);
    if (target !== this.root && !target.startsWith(`${this.root}${path.sep}`)) {
      throw new FilesystemError("Path escapes the service volume", 403);
    }
    // Symlink escape protection: the real path must stay inside the volume.
    try {
      const real = await fs.realpath(target);
      const realRoot = await fs.realpath(this.root);
      if (real !== realRoot && !real.startsWith(`${realRoot}${path.sep}`)) {
        throw new FilesystemError("Symlink escapes the service volume", 403);
      }
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
      if (mustExist) throw new FilesystemError("File not found", 404);
    }
    return target;
  }

  rel(abs: string): string {
    const r = path.relative(this.root, abs);
    return r === "" ? "/" : `/${r}`;
  }

  async list(dir = "/"): Promise<FileEntry[]> {
    const target = await this.resolve(dir, true);
    const entries = await fs.readdir(target, { withFileTypes: true });
    const out: FileEntry[] = [];
    for (const e of entries) {
      const full = path.join(target, e.name);
      const stat = await fs.lstat(full);
      out.push({
        name: e.name,
        path: this.rel(full),
        type: e.isDirectory() ? "directory" : "file",
        size: stat.size,
        modifiedAt: stat.mtime.toISOString(),
        mode: (stat.mode & 0o777).toString(8),
      });
    }
    return out.sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name) : a.type === "directory" ? -1 : 1,
    );
  }

  async read(file: string): Promise<string> {
    const target = await this.resolve(file, true);
    const stat = await fs.stat(target);
    if (stat.isDirectory()) throw new FilesystemError("Target is a directory");
    if (stat.size > MAX_TEXT_BYTES)
      throw new FilesystemError("File too large for the editor (2MB max)", 413);
    return fs.readFile(target, "utf8");
  }

  async readBuffer(file: string): Promise<Buffer> {
    const target = await this.resolve(file, true);
    return fs.readFile(target);
  }

  async write(file: string, content: string | Buffer): Promise<void> {
    const target = await this.resolve(file);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content);
  }

  async mkdir(dir: string): Promise<void> {
    const target = await this.resolve(dir);
    await fs.mkdir(target, { recursive: true });
  }

  async remove(target: string): Promise<void> {
    const abs = await this.resolve(target, true);
    if (abs === this.root) throw new FilesystemError("Cannot delete the volume root", 403);
    await fs.rm(abs, { recursive: true, force: true });
  }

  async rename(from: string, to: string): Promise<void> {
    const src = await this.resolve(from, true);
    const dst = await this.resolve(to);
    await fs.mkdir(path.dirname(dst), { recursive: true });
    await fs.rename(src, dst);
  }

  async copy(from: string, to: string): Promise<void> {
    const src = await this.resolve(from, true);
    const dst = await this.resolve(to);
    await fs.cp(src, dst, { recursive: true });
  }

  async exists(target: string): Promise<boolean> {
    try {
      await fs.access(await this.resolve(target));
      return true;
    } catch {
      return false;
    }
  }

  /** tar.gz an inner directory into an absolute destination outside the volume. */
  async archiveTo(destAbsolute: string): Promise<number> {
    await exec("tar", ["-czf", destAbsolute, "-C", this.root, "."]);
    const stat = await fs.stat(destAbsolute);
    return stat.size;
  }

  async restoreFrom(srcAbsolute: string): Promise<void> {
    await fs.rm(this.root, { recursive: true, force: true });
    await fs.mkdir(this.root, { recursive: true });
    await exec("tar", ["-xzf", srcAbsolute, "-C", this.root]);
  }

  async zip(target: string): Promise<{ name: string; buffer: Buffer }> {
    const abs = await this.resolve(target, true);
    const name = `${path.basename(abs) || "volume"}.tar.gz`;
    const tmp = path.join("/tmp", `orbital-${Date.now()}-${name}`);
    await exec("tar", ["-czf", tmp, "-C", path.dirname(abs), path.basename(abs)]);
    const buffer = await fs.readFile(tmp);
    await fs.rm(tmp, { force: true });
    return { name, buffer };
  }

  async unzip(archive: string, destination = "/"): Promise<void> {
    const abs = await this.resolve(archive, true);
    const dest = await this.resolve(destination);
    await fs.mkdir(dest, { recursive: true });
    if (abs.endsWith(".zip")) {
      await exec("unzip", ["-o", abs, "-d", dest]);
    } else {
      await exec("tar", ["-xzf", abs, "-C", dest]);
    }
  }

  async diskUsageMb(): Promise<number> {
    let total = 0;
    const walk = async (dir: string) => {
      const entries = await fs.readdir(dir, { withFileTypes: true });
      for (const e of entries) {
        const full = path.join(dir, e.name);
        try {
          if (e.isDirectory()) await walk(full);
          else {
            const st = await fs.lstat(full);
            total += st.size;
          }
        } catch {
          /* ignore transient files */
        }
      }
    };
    try {
      await walk(this.root);
    } catch {
      return 0;
    }
    return Math.round((total / (1024 * 1024)) * 10) / 10;
  }
}
