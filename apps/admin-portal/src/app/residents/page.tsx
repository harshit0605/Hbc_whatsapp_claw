import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";
import { timeAgo } from "@/lib/fmt";

export const dynamic = "force-dynamic";

export default async function ResidentsPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  const residents = await api.listResidents(searchParams.q);
  return (
    <>
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Residents</h1>
        <form className="flex gap-2">
          <input
            name="q"
            defaultValue={searchParams.q || ""}
            placeholder="Search name, phone, tower"
            className="input"
          />
          <button className="btn" type="submit">Search</button>
        </form>
      </header>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2">Name</th>
            <th>Tower / Flat</th>
            <th>Phone</th>
            <th>Lang</th>
            <th>Status</th>
            <th>Joined</th>
          </tr>
        </thead>
        <tbody>
          {residents.map((r) => (
            <tr key={r.id} className="border-t border-line">
              <td className="py-2">{r.display_name || "—"}</td>
              <td>{r.tower_name ? `${r.tower_name} · ${r.flat_number}` : "—"}</td>
              <td className="text-muted">+{r.phone || "—"}</td>
              <td className="text-muted">{r.language}</td>
              <td>
                <span className={`chip ${
                  r.status === "verified" ? "border-low/40 text-low"
                  : r.status === "blocked" ? "border-crit/40 text-crit"
                  : "border-line text-muted"
                }`}>{r.status}</span>
              </td>
              <td className="text-xs text-muted">{timeAgo(r.created_at)}</td>
            </tr>
          ))}
          {residents.length === 0 && (
            <tr>
              <td colSpan={6} className="py-6 text-center text-muted">No residents.</td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
