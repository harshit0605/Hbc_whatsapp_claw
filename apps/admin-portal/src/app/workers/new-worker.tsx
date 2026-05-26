"use client";

import { useState, useTransition } from "react";
import { createWorkerAction } from "./actions";

export function NewWorkerForm() {
  const [error, setError] = useState<string | null>(null);
  const [busy, start] = useTransition();
  return (
    <section className="card">
      <h2 className="mb-3 text-sm font-medium">Add worker</h2>
      <form
        action={(fd) =>
          start(async () => {
            const res = await createWorkerAction(fd);
            if (res?.error) setError(res.error);
            else setError(null);
          })
        }
        className="space-y-2"
      >
        <label className="block">
          <span className="text-xs text-muted">Name</span>
          <input name="name" required className="input mt-1" />
        </label>
        <label className="block">
          <span className="text-xs text-muted">Phone (with country code, no +)</span>
          <input name="phone" required placeholder="9198xxxxxxxx" className="input mt-1" />
        </label>
        <label className="block">
          <span className="text-xs text-muted">Categories (comma-separated)</span>
          <input
            name="categories"
            placeholder="plumbing, garbage"
            className="input mt-1"
          />
        </label>
        {error && <p className="text-xs text-crit">{error}</p>}
        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Adding…" : "Add worker"}
        </button>
        <p className="text-xs text-muted">
          The worker becomes dispatch-ready after they DM the bot once (so we can capture their
          WhatsApp JID).
        </p>
      </form>
    </section>
  );
}
