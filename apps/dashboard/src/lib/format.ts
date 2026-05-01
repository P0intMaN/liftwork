import { formatDistanceToNow, format } from "date-fns";

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

export function absTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return format(new Date(iso), "MMM d, yyyy HH:mm:ss");
}

export function shortSha(sha: string | null | undefined, n = 7): string {
  return sha ? sha.slice(0, n) : "—";
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0 || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  return `${m}m ${s}s`;
}

export function pct(numer: number, denom: number): string {
  if (!denom) return "—";
  return `${((numer / denom) * 100).toFixed(1)}%`;
}
