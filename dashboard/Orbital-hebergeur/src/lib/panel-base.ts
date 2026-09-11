export const PANEL_BASE_PATH = "/hebergement";

export function withPanelBase(path: string): string {
  if (!path.startsWith("/")) return path;
  if (path === PANEL_BASE_PATH || path.startsWith(`${PANEL_BASE_PATH}/`)) return path;
  return `${PANEL_BASE_PATH}${path}`;
}
