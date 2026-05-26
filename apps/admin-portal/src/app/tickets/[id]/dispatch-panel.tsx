"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import type { Worker } from "@/lib/api";
import { dispatchAction } from "./actions";

export function DispatchPanel({
  complaintId,
  category,
  workers,
  adminId,
}: {
  complaintId: string;
  category: string;
  workers: Worker[];
  adminId?: string;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState<Worker | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, start] = useTransition();

  const ranked = useMemo(() => {
    return [...workers]
      .filter((w) => w.is_active)
      .sort((a, b) => {
        const aMatch = a.categories.includes(category) ? 0 : 1;
        const bMatch = b.categories.includes(category) ? 0 : 1;
        return aMatch - bMatch;
      });
  }, [workers, category]);

  function approve() {
    if (!confirming) return;
    setError(null);
    start(async () => {
      const res = await dispatchAction(complaintId, confirming.id, adminId);
      if (res?.error) {
        setError(res.error);
        return;
      }
      setConfirming(null);
      router.refresh();
    });
  }

  return (
    <section className="card">
      <h2 className="mb-3 text-sm font-medium">Dispatch worker</h2>

      {ranked.length === 0 ? (
        <p className="text-xs text-muted">No active workers configured.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {ranked.map((w) => {
            const matches = w.categories.includes(category);
            const ready = Boolean(w.wa_jid);
            return (
              <li
                key={w.id}
                className="flex items-center justify-between rounded border border-line bg-bg px-2 py-1.5"
              >
                <div>
                  <div className="font-medium">{w.name}</div>
                  <div className="text-xs text-muted">
                    {w.categories.join(", ") || "no categories"} · +{w.phone}
                  </div>
                </div>
                <button
                  onClick={() => setConfirming(w)}
                  disabled={!ready}
                  title={ready ? "" : "Worker must DM the bot once before dispatch is possible"}
                  className={`btn ${matches ? "border-accent text-accent" : ""} disabled:opacity-40`}
                >
                  Assign
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {confirming && (
        <Modal onClose={() => setConfirming(null)}>
          <h3 className="mb-2 text-base font-medium">Confirm dispatch</h3>
          <p className="mb-3 text-sm text-muted">
            This will send a WhatsApp message to <b>{confirming.name}</b> and create an
            assignment. Worker can reply ACCEPT, DONE, or HELP.
          </p>
          {error && <p className="mb-2 text-xs text-crit">{error}</p>}
          <div className="flex justify-end gap-2">
            <button className="btn" onClick={() => setConfirming(null)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={approve} disabled={busy}>
              {busy ? "Sending…" : "Approve & Dispatch"}
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-line bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
