import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";

export const dynamic = "force-dynamic";

interface StatsResponse {
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_tower: { tower: string; count: number }[];
  mttr_seconds: number | null;
}

export default async function AnalyticsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const base = process.env.SKILLS_API_BASE_URL || "http://skills:8080";
  const tok = process.env.SKILLS_API_TOKEN || "dev-token";
  const res = await fetch(`${base}/stats`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${tok}` },
  });
  const s = (await res.json()) as StatsResponse;
  const total = Object.values(s.by_status).reduce((a, b) => a + b, 0);

  return (
    <>
      <h1 className="mb-4 text-xl font-semibold">Analytics</h1>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total complaints" value={total} />
        <Stat label="Open" value={s.by_status.open || 0} />
        <Stat label="In progress" value={s.by_status.in_progress || 0} />
        <Stat
          label="Resolved + closed"
          value={(s.by_status.resolved || 0) + (s.by_status.closed || 0)}
        />
        <Stat label="Mean time to resolve" value={fmtMttr(s.mttr_seconds)} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="By status" rows={Object.entries(s.by_status)} />
        <Panel title="By category" rows={Object.entries(s.by_category)} />
        <Panel title="Hot spots" rows={s.by_tower.map((r) => [r.tower, r.count])} />
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Panel({ title, rows }: { title: string; rows: [string, number][] }) {
  return (
    <div className="card">
      <h2 className="mb-3 text-sm text-muted">{title}</h2>
      <ul className="text-sm">
        {rows.map(([k, v]) => (
          <li key={k} className="flex justify-between border-b border-line py-1.5 last:border-0">
            <span>{k.replace("_", " ")}</span>
            <span className="text-muted">{v}</span>
          </li>
        ))}
        {rows.length === 0 && <li className="text-muted">No data yet.</li>}
      </ul>
    </div>
  );
}

function fmtMttr(s: number | null): string {
  if (s == null) return "—";
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}
