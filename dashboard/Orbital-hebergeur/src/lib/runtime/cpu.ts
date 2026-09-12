/** Docker reports % of one core (100 = one core fully used). The UI says "% of N cores". */
export function cpuPercentOfQuota(dockerCpuPercent: number, millicores: number): number {
  const cores = Number(millicores) / 1000;
  if (!Number.isFinite(dockerCpuPercent) || dockerCpuPercent < 0) return 0;
  if (!Number.isFinite(cores) || cores <= 0) return dockerCpuPercent;
  return dockerCpuPercent / cores;
}
