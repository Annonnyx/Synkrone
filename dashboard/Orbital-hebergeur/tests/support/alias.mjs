// Resolves the "@/..." alias and extensionless TS imports for the Node test runner.
import { registerHooks } from "node:module";
import { existsSync, statSync } from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const src = path.resolve(import.meta.dirname, "..", "..", "src");

function resolveFile(base) {
  const candidates = [`${base}.ts`, `${base}.tsx`, path.join(base, "index.ts")];
  if (existsSync(base) && statSync(base).isFile()) candidates.unshift(base);
  for (const candidate of candidates) {
    if (existsSync(candidate) && statSync(candidate).isFile()) {
      return { url: pathToFileURL(candidate).href, shortCircuit: true };
    }
  }
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const hit = resolveFile(path.join(src, specifier.slice(2)));
      if (hit) return hit;
    }
    if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
      const base = path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier);
      const hit = resolveFile(base);
      if (hit) return hit;
    }
    return nextResolve(specifier, context);
  },
});
