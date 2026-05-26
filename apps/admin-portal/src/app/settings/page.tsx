import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { AdminUserList } from "./admins";
import { TestAlertForm } from "./test-alert";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  // Fetch admin list (uses the same bearer the rest of the portal uses).
  const admins = await fetchAdmins();
  const currentEmail = session.user?.email ?? "";

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section>
        <h1 className="mb-4 text-xl font-semibold">Admin users</h1>
        <AdminUserList admins={admins} currentEmail={currentEmail} />
      </section>
      <section className="space-y-4">
        <h1 className="text-xl font-semibold">Critical alert test</h1>
        <TestAlertForm />
        <div className="card">
          <h2 className="mb-2 text-sm font-medium">Tips</h2>
          <ul className="space-y-1 text-xs text-muted">
            <li>• Critical alerts go to JIDs listed in <code>ADMIN_ALERT_JIDS</code>.</li>
            <li>• Use a WhatsApp group JID (<code>...@g.us</code>) for fan-out without listing every admin.</li>
            <li>• Workers become dispatch-ready only after they DM the bot once.</li>
            <li>• The agent never dispatches on its own — only this portal can.</li>
          </ul>
        </div>
      </section>
    </div>
  );
}

async function fetchAdmins(): Promise<any[]> {
  // The admins endpoint is server-only and uses the bearer.
  // We inline a tiny fetch instead of extending the api.ts type surface.
  const base = process.env.SKILLS_API_BASE_URL || "http://skills:8080";
  const tok = process.env.SKILLS_API_TOKEN || "dev-token";
  const r = await fetch(`${base}/admins`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${tok}` },
  });
  if (!r.ok) return [];
  return r.json();
}

