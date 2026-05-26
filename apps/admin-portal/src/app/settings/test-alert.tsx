"use client";

import { useState, useTransition } from "react";
import { testAlertAction } from "./actions";

export function TestAlertForm() {
  const [body, setBody] = useState(
    "Test alert from society admin portal — please reply 👍 if received.",
  );
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, start] = useTransition();

  return (
    <form
      className="card space-y-2"
      action={() =>
        start(async () => {
          setMsg(null);
          const res = await testAlertAction(body);
          if (res?.error) setMsg(`error: ${res.error}`);
          else setMsg("dispatched");
        })
      }
    >
      <textarea
        rows={3}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        className="input"
      />
      {msg && (
        <p className={`text-xs ${msg.startsWith("error") ? "text-crit" : "text-low"}`}>{msg}</p>
      )}
      <button type="submit" disabled={busy} className="btn-primary w-full">
        {busy ? "Sending…" : "Send test alert"}
      </button>
    </form>
  );
}
