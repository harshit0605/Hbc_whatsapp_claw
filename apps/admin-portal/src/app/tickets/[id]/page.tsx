import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";
import { sevColor, timeAgo } from "@/lib/fmt";
import { DispatchPanel } from "./dispatch-panel";
import { StatusPanel } from "./status-panel";

export const dynamic = "force-dynamic";

export default async function TicketPage({ params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const [complaint, assignments, proposed] = await Promise.all([
    api.getComplaint(params.id),
    api.getComplaintAssignments(params.id),
    api.getProposedWorkers(params.id),
  ]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
      <article className="card">
        <header className="mb-3 flex items-center gap-3">
          <span className="text-muted">#{complaint.ticket_no}</span>
          <span className={`chip ${sevColor(complaint.severity)}`}>{complaint.severity}</span>
          <span className="chip border-line text-muted">{complaint.category}</span>
          <span className="ml-auto text-xs text-muted">{timeAgo(complaint.created_at)}</span>
        </header>

        <h1 className="mb-1 text-xl font-semibold">{complaint.title}</h1>
        <p className="mb-4 text-sm text-muted">
          {complaint.tower_name
            ? `${complaint.tower_name} · Flat ${complaint.flat_number}`
            : "Location unknown"}{" "}
          · Reported by {complaint.resident_name || "—"} (+{complaint.resident_phone || "—"})
        </p>

        <p className="whitespace-pre-wrap text-sm">{complaint.description}</p>

        {complaint.media.length > 0 && (
          <section className="mt-4">
            <h2 className="mb-2 text-sm text-muted">Attachments</h2>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {complaint.media.map((m) => (
                <a
                  key={m.id}
                  href={m.presigned_url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="block overflow-hidden rounded-md border border-line bg-bg"
                >
                  {m.kind === "image" && m.presigned_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.presigned_url} alt="" className="aspect-square w-full object-cover" />
                  ) : (
                    <div className="flex aspect-square items-center justify-center text-xs text-muted">
                      {m.kind} · open
                    </div>
                  )}
                </a>
              ))}
            </div>
          </section>
        )}

        {assignments.length > 0 && (
          <section className="mt-6">
            <h2 className="mb-2 text-sm text-muted">Assignment history</h2>
            <ul className="space-y-2 text-sm">
              {assignments.map((a) => (
                <li key={a.id} className="rounded border border-line bg-bg p-2">
                  <span className="font-medium">{a.worker_name}</span>
                  <span className="text-muted"> (+{a.worker_phone})</span>
                  <span className="ml-2 chip border-line text-muted">{a.status}</span>
                  <span className="ml-2 text-xs text-muted">{timeAgo(a.dispatched_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </article>

      <aside className="space-y-4">
        <StatusPanel complaintId={complaint.id} current={complaint.status} />
        <DispatchPanel
          complaintId={complaint.id}
          category={complaint.category}
          workers={proposed}
          adminId={(session.user as any)?.id}
        />
      </aside>
    </div>
  );
}
