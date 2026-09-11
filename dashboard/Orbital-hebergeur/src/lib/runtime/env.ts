/** Later layers win. Empty strings are ignored so a blank user env cannot wipe tokens. */
export function mergeContainerEnv(
  ...layers: Array<Record<string, string | undefined>>
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const layer of layers) {
    for (const [key, value] of Object.entries(layer)) {
      if (value == null || value === "") continue;
      out[key] = value;
    }
  }
  return out;
}
