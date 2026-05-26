"use client";

import { useTransition } from "react";
import { toggleActiveAction } from "./actions";

export function ToggleActive({ id, active }: { id: string; active: boolean }) {
  const [busy, start] = useTransition();
  return (
    <button
      onClick={() => start(() => toggleActiveAction(id, active))}
      disabled={busy}
      className={`chip ${active ? "border-low/40 text-low" : "border-line text-muted"}`}
    >
      {active ? "active" : "inactive"}
    </button>
  );
}
