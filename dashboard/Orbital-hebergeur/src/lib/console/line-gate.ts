export type LineGate = {
  /** How many of `n` lines may be emitted in the current window. */
  allow(n: number): number;
  takeDropped(): number;
};

/** Token bucket that resets every `windowMs`. Extra lines are counted as dropped. */
export function createLineGate(maxPerWindow: number, windowMs: number): LineGate {
  let allowed = maxPerWindow;
  let dropped = 0;
  let resetAt = Date.now() + windowMs;
  return {
    allow(n: number) {
      const now = Date.now();
      if (now >= resetAt) {
        allowed = maxPerWindow;
        resetAt = now + windowMs;
      }
      const take = Math.min(Math.max(0, n), allowed);
      allowed -= take;
      dropped += Math.max(0, n - take);
      return take;
    },
    takeDropped() {
      const n = dropped;
      dropped = 0;
      return n;
    },
  };
}

const NOISE = [
  /Dropped \d+ log lines \(rate limit\)/i,
  /WARNING: Running pip as the 'root' user/i,
  /Use the --root-user-action option/i,
  /It is recommended to use a virtual environment/i,
  /\[notice\] A new release of pip/i,
  /\[notice\] To update, run: pip install/i,
  /which is not on PATH/i,
  /Consider adding this directory to PATH/i,
  /The script (dotenv|idna) is installed/i,
  /PyNaCl is not installed/i,
  /davey is not installed/i,
  /voice will NOT be supported/i,
  /\[ANTISCAM\]\[DEBUG\]/i,
  /has successfully RESUMED session/i,
];

export function isConsoleNoise(line: string): boolean {
  const text = String(line || "").trim();
  if (!text) return true;
  if (/^[━─\-|=. ]+$/u.test(text)) return true;
  if (/\d+(?:\.\d+)?\s*MB\/s/i.test(text) && /[━─]/u.test(text)) return true;
  return NOISE.some((re) => re.test(text));
}

export function createLineSplitter(onLine: (stream: string, line: string) => void) {
  const tails = new Map<string, string>();
  return {
    push(stream: string, text: string) {
      const combined = `${tails.get(stream) ?? ""}${text}`;
      const parts = combined.split(/\r?\n/);
      tails.set(stream, parts.pop() ?? "");
      for (const line of parts) {
        if (line.trim()) onLine(stream, line);
      }
    },
    flush() {
      for (const [stream, tail] of tails) {
        if (tail.trim()) onLine(stream, tail);
      }
      tails.clear();
    },
  };
}
