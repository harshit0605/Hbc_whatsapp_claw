import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  const { by_status } = await api.stats();
  const total = Object.values(by_status).reduce((a, b) => a + b, 0);
  return (
    <>
      <h1 className="mb-4 text-xl font-semibold">Analytics</h1>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total complaints" value={total} />
        <Stat label="Open" value={by_status.open || 0} />
        <Stat label="In progress" value={by_status.in_progress || 0} />
        <Stat label="Resolved" value={(by_status.resolved || 0) + (by_status.closed || 0)} />
      </div>
      <div className="mt-6 card">
        <h2 className="mb-3 text-sm text-muted">By status</h2>
        <ul className="text-sm">
          {Object.entries(by_status).map(([k, v]) => (
            <li key={k} className="flex justify-between border-b border-line py-1.5 last:border-0">
              <span>{k.replace("_", " ")}</span>
              <span className="text-muted">{v}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}
