import { createHash, randomBytes } from "node:crypto";

/**
 * glibc SHA-512 crypt (`$6$`), used by atmoz/sftp when the users.conf
 * password field is marked encrypted (`:e`).
 *
 * Spec: https://www.akkadia.org/drepper/SHA-crypt.txt
 */
const ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const DEFAULT_ROUNDS = 5000;

function digest(chunks: Buffer[]): Buffer {
  const hash = createHash("sha512");
  for (const chunk of chunks) hash.update(chunk);
  return hash.digest();
}

function to64(value: number, count: number): string {
  let out = "";
  let v = value >>> 0;
  for (let i = 0; i < count; i += 1) {
    out += ITOA64[v & 63];
    v >>>= 6;
  }
  return out;
}

function b64From24bit(b2: number, b1: number, b0: number, n: number): string {
  return to64((b2 << 16) | (b1 << 8) | b0, n);
}

function randomSalt(length = 16): string {
  const buf = randomBytes(length);
  let out = "";
  for (const byte of buf) out += ITOA64[byte & 63];
  return out;
}

function parseSalt(salt: string): { rounds: number; salt: string } {
  const full = salt.match(/^\$6\$(?:rounds=(\d+)\$)?([^$]+)/);
  if (full) {
    const rounds = full[1] ? Number(full[1]) : DEFAULT_ROUNDS;
    return { rounds: clampRounds(rounds), salt: full[2].slice(0, 16) };
  }
  return { rounds: DEFAULT_ROUNDS, salt: salt.replace(/[^./0-9A-Za-z]/g, "").slice(0, 16) };
}

function clampRounds(rounds: number): number {
  if (!Number.isFinite(rounds)) return DEFAULT_ROUNDS;
  return Math.min(999_999_999, Math.max(1000, Math.floor(rounds)));
}

function fillFromDigest(digestBuf: Buffer, length: number): Buffer {
  const out = Buffer.alloc(length);
  for (let offset = 0; offset < length; offset += 64) {
    digestBuf.copy(out, offset, 0, Math.min(64, length - offset));
  }
  return out;
}

export function sha512Crypt(password: string, salt?: string, rounds = DEFAULT_ROUNDS): string {
  const key = Buffer.from(password, "utf8");
  const parsed = salt ? parseSalt(salt) : { rounds: clampRounds(rounds), salt: randomSalt() };
  const usedRounds = salt?.startsWith("$6$") ? parsed.rounds : clampRounds(rounds);
  const saltBuf = Buffer.from(parsed.salt, "utf8");

  const digestB = digest([key, saltBuf, key]);

  const digestAChunks: Buffer[] = [key, saltBuf];
  let remaining = key.length;
  while (remaining > 64) {
    digestAChunks.push(digestB);
    remaining -= 64;
  }
  digestAChunks.push(digestB.subarray(0, remaining));
  for (let bits = key.length; bits > 0; bits >>= 1) {
    digestAChunks.push(bits & 1 ? digestB : key);
  }
  let alt = digest(digestAChunks);

  const pCtx = createHash("sha512");
  for (let i = 0; i < key.length; i += 1) pCtx.update(key);
  const pBytes = fillFromDigest(pCtx.digest(), key.length);

  const sCtx = createHash("sha512");
  for (let i = 0; i < 16 + alt[0]; i += 1) sCtx.update(saltBuf);
  const sBytes = fillFromDigest(sCtx.digest(), saltBuf.length);

  for (let i = 0; i < usedRounds; i += 1) {
    const round: Buffer[] = [];
    if (i & 1) round.push(pBytes);
    else round.push(alt);
    if (i % 3) round.push(sBytes);
    if (i % 7) round.push(pBytes);
    if (i & 1) round.push(alt);
    else round.push(pBytes);
    alt = digest(round);
  }

  const encoded =
    b64From24bit(alt[0], alt[21], alt[42], 4) +
    b64From24bit(alt[22], alt[43], alt[1], 4) +
    b64From24bit(alt[44], alt[2], alt[23], 4) +
    b64From24bit(alt[3], alt[24], alt[45], 4) +
    b64From24bit(alt[25], alt[46], alt[4], 4) +
    b64From24bit(alt[47], alt[5], alt[26], 4) +
    b64From24bit(alt[6], alt[27], alt[48], 4) +
    b64From24bit(alt[28], alt[49], alt[7], 4) +
    b64From24bit(alt[50], alt[8], alt[29], 4) +
    b64From24bit(alt[9], alt[30], alt[51], 4) +
    b64From24bit(alt[31], alt[52], alt[10], 4) +
    b64From24bit(alt[53], alt[11], alt[32], 4) +
    b64From24bit(alt[12], alt[33], alt[54], 4) +
    b64From24bit(alt[34], alt[55], alt[13], 4) +
    b64From24bit(alt[56], alt[14], alt[35], 4) +
    b64From24bit(alt[15], alt[36], alt[57], 4) +
    b64From24bit(alt[37], alt[58], alt[16], 4) +
    b64From24bit(alt[59], alt[17], alt[38], 4) +
    b64From24bit(alt[18], alt[39], alt[60], 4) +
    b64From24bit(alt[40], alt[61], alt[19], 4) +
    b64From24bit(alt[62], alt[20], alt[41], 4) +
    b64From24bit(0, 0, alt[63], 2);

  const roundsPrefix = usedRounds === DEFAULT_ROUNDS ? "" : `rounds=${usedRounds}$`;
  return `$6$${roundsPrefix}${parsed.salt}$${encoded}`;
}
