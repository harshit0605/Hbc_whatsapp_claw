import Link from "next/link";
import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";
import { sevColor, timeAgo } from "@/lib/fmt";

export const dynamic = "force-dynamic";

export default async function QueuePage({
  searchParams,
}: {
  searchParams: { status?: string; severity?: string };
}) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const complaints = await api.listComplaints({
    status: searchParams.status,
    severity: searchParams.severity,
    limit: 200,
  });

  return (
    <>
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Queue</h1>
        <div className="flex flex-wrap gap-2 text-xs">
          <FilterLink param="status" value={undefined} active={!searchParams.status} label="All" />
          {(["open", "triaging", "assigned", "in_progress", "resolved"] as const).map((s) => (
            <FilterLink
              key={s}
              param="status"
              value={s}
              active={searchParams.status === s}
              label={s.replace("_", " ")}
            />
          ))}
          <span className="mx-2 text-muted">·</span>
          {(["critical", "high", "medium", "low"] as const).map((s) => (
            <FilterLink
              key={s}
              param="severity"
              value={s}
              active={searchParams.severity === s}
              label={s}
            />
          ))}
        </div>
      </header>

      {complaints.length === 0 ? (
        <div className="card text-center text-muted">No complaints match this filter.</div>
      ) : (
        <ul className="space-y-2">
          {complaints.map((c) => (
            <li key={c.id}>
              <Link
                href={`/tickets/${c.id}`}
                className="card flex items-center gap-4 hover:border-accent/50"
              >
                <span className="text-muted">#{c.ticket_no}</span>
                <span className={`chip ${sevColor(c.severity)}`}>{c.severity}</span>
                <span className="chip border-line text-muted">{c.category}</span>
                <span className="flex-1 truncate font-medium">{c.title}</span>
                <span className="text-xs text-muted">
                  {c.tower_name ? `${c.tower_name} · ${c.flat_number}` : "—"}
                </span>
                <span className="w-20 text-right text-xs text-muted">{c.status}</span>
                <span className="w-20 text-right text-xs text-muted">{timeAgo(c.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function FilterLink({
  param,
  value,
  active,
  label,
}: {
  param: string;
  value: string | undefined;
  active: boolean;
  label: string;
}) {
  const href = value ? `/queue?${param}=${value}` : "/queue";
  return (
    <Link
      href={href}
      className={`chip ${active ? "border-accent text-accent" : "border-line text-muted"}`}
    >
      {label}
    </Link>
  );
}
