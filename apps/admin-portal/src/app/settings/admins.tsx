"use client";

import { useState, useTransition } from "react";
import { createAdminAction, deleteAdminAction } from "./actions";

export function AdminUserList({
  admins,
  currentEmail,
}: {
  admins: { id: string; email: string; role: string; created_at: string }[];
  currentEmail: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, start] = useTransition();
  return (
    <div className="space-y-4">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2">Email</th>
            <th>Role</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {admins.map((a) => (
            <tr key={a.id} className="border-t border-line">
              <td className="py-2">
                {a.email}
                {a.email === currentEmail && (
                  <span className="ml-2 chip border-line text-muted">you</span>
                )}
              </td>
              <td className="text-muted">{a.role}</td>
              <td className="text-right">
                {a.email !== currentEmail && (
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() =>
                      start(async () => {
                        const res = await deleteAdminAction(a.id);
                        if (res?.error) setError(res.error);
                      })
                    }
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form
        className="card space-y-2"
        action={(fd) =>
          start(async () => {
            const res = await createAdminAction(fd);
            if (res?.error) setError(res.error);
            else setError(null);
          })
        }
      >
        <h2 className="text-sm font-medium">Add admin</h2>
        <input name="email" type="email" required placeholder="admin@example.com" className="input" />
        <input
          name="password"
          type="password"
          required
          minLength={8}
          placeholder="password (>= 8 chars)"
          className="input"
        />
        {error && <p className="text-xs text-crit">{error}</p>}
        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Adding…" : "Add admin"}
        </button>
      </form>
    </div>
  );
}
