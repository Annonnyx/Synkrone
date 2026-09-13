import { randomPassword } from "@/lib/crypto";
import { sha512Crypt } from "@/lib/sha512crypt";

/** Legacy marker stored when SFTP used the Synkrone account password. */
export const LEGACY_SFTP_ACCOUNT_MARKER = "account";

export function generateSftpSecret(length = 28): { password: string; crypt: string } {
  const password = randomPassword(length);
  return { password, crypt: sha512Crypt(password) };
}

export function isPerServiceSftpSecret(plain: string | null | undefined): boolean {
  return Boolean(plain) && plain !== LEGACY_SFTP_ACCOUNT_MARKER;
}

export function sftpPasswordMatches(storedPlain: string | null | undefined, offered: string): boolean {
  if (!isPerServiceSftpSecret(storedPlain) || !offered) return false;
  const a = Buffer.from(storedPlain as string);
  const b = Buffer.from(offered);
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i += 1) mismatch |= a[i] ^ b[i];
  return mismatch === 0;
}
