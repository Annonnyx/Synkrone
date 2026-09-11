/** atmoz/sftp users.conf line. `:e` marks a glibc SHA-512 crypt hash. */
export function sftpUserConfLine(
  username: string,
  chroot: string,
  crypt?: string | null,
): string {
  const dir = chroot.replace(/^\//, "");
  if (crypt && crypt.startsWith("$6$")) {
    return `${username}:${crypt}:e:1000:1000:${dir}`;
  }
  return `${username}::1000:1000:${dir}`;
}
