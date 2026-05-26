import type { Severity } from "@/lib/api";

export function timeAgo(iso: string): string {
  const d = new Date(iso);
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

export function sevColor(sev: Severity): string {
  return {
    low: "bg-low/15 text-low border-low/30",
    medium: "bg-med/15 text-med border-med/30",
    high: "bg-high/15 text-high border-high/30",
    critical: "bg-crit/15 text-crit border-crit/40",
  }[sev];
}
