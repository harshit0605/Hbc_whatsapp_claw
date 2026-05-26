import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";
import { NewWorkerForm } from "./new-worker";
import { ToggleActive } from "./toggle";

export const dynamic = "force-dynamic";

export default async function WorkersPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  const workers = await api.listWorkers();
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
      <section>
        <h1 className="mb-4 text-xl font-semibold">Workers</h1>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2">Name</th>
              <th>Categories</th>
              <th>Phone</th>
              <th>WhatsApp linked?</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((w) => (
              <tr key={w.id} className="border-t border-line">
                <td className="py-2">{w.name}</td>
                <td className="text-muted">{w.categories.join(", ") || "—"}</td>
                <td className="text-muted">+{w.phone}</td>
                <td className={w.wa_jid ? "text-low" : "text-med"}>
                  {w.wa_jid ? "yes" : "pending — ask worker to message the bot once"}
                </td>
                <td>
                  <ToggleActive id={w.id} active={w.is_active} />
                </td>
              </tr>
            ))}
            {workers.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 text-center text-muted">No workers yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      <aside>
        <NewWorkerForm />
      </aside>
    </div>
  );
}
