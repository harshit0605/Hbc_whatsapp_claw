"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type { ComplaintStatus } from "@/lib/api";
import { setStatusAction } from "./actions";

const STATUSES: ComplaintStatus[] = [
  "open",
  "triaging",
  "assigned",
  "in_progress",
  "resolved",
  "closed",
  "rejected",
];

export function StatusPanel({
  complaintId,
  current,
}: {
  complaintId: string;
  current: ComplaintStatus;
}) {
  const router = useRouter();
  const [val, setVal] = useState<ComplaintStatus>(current);
  const [busy, start] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function save() {
    setError(null);
    start(async () => {
      const res = await setStatusAction(complaintId, val);
      if (res?.error) setError(res.error);
      else router.refresh();
    });
  }

  return (
    <section className="card">
      <h2 className="mb-3 text-sm font-medium">Status</h2>
      <select
        value={val}
        onChange={(e) => setVal(e.target.value as ComplaintStatus)}
        className="input mb-2"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
      {error && <p className="mb-2 text-xs text-crit">{error}</p>}
      <button onClick={save} disabled={busy || val === current} className="btn-primary w-full">
        {busy ? "Saving…" : "Update status"}
      </button>
    </section>
  );
}
