/**
 * Skills service HTTP client (server-side only — uses a bearer token that
 * must not be exposed to the browser).
 */
import "server-only";

const BASE = process.env.SKILLS_API_BASE_URL || "http://skills:8080";
const TOKEN = process.env.SKILLS_API_TOKEN || "dev-token";

async function req<T>(
  path: string,
  init: RequestInit = {},
  searchParams?: Record<string, string | number | undefined>,
): Promise<T> {
  const url = new URL(path, BASE);
  if (searchParams) {
    for (const [k, v] of Object.entries(searchParams)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type":
        init.body instanceof FormData
          ? (init.headers as any)?.["Content-Type"] ?? undefined
          : "application/json",
    } as HeadersInit,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Skills API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export type Severity = "low" | "medium" | "high" | "critical";
export type ComplaintStatus =
  | "open"
  | "triaging"
  | "assigned"
  | "in_progress"
  | "resolved"
  | "closed"
  | "rejected";

export interface ComplaintMedia {
  id: string;
  kind: "image" | "audio" | "video" | "document";
  storage_key: string;
  mime: string | null;
  bytes: number | null;
  presigned_url: string | null;
}

export interface Complaint {
  id: string;
  ticket_no: number;
  resident_id: string;
  tower_id: number | null;
  flat_id: number | null;
  tower_name: string | null;
  flat_number: string | null;
  resident_name: string | null;
  resident_phone: string | null;
  category: string;
  severity: Severity;
  status: ComplaintStatus;
  title: string;
  description: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  media: ComplaintMedia[];
}

export interface Worker {
  id: string;
  wa_jid: string | null;
  phone: string;
  name: string;
  categories: string[];
  is_active: boolean;
  notes: string | null;
}

export interface Resident {
  id: string;
  wa_jid: string;
  phone: string | null;
  display_name: string | null;
  language: string;
  status: "pending" | "verified" | "blocked";
  tower_name: string | null;
  flat_number: string | null;
  created_at: string;
  updated_at: string;
}

export interface Assignment {
  id: string;
  complaint_id: string;
  worker_id: string;
  worker_name: string | null;
  worker_phone: string | null;
  status: "pending" | "accepted" | "done" | "cancelled";
  dispatched_at: string;
  closed_at: string | null;
  notes: string | null;
}

// ── Complaints ──────────────────────────────────────────────────────────────

export const api = {
  listComplaints: (params: { status?: string; severity?: string; limit?: number } = {}) =>
    req<Complaint[]>("/complaints", {}, params),
  getComplaint: (id: string) => req<Complaint>(`/complaints/${id}`),
  getComplaintAssignments: (id: string) =>
    req<Assignment[]>(`/complaints/${id}/assignments`),
  getProposedWorkers: (id: string) =>
    req<Worker[]>(`/complaints/${id}/proposed-workers`),
  setComplaintStatus: (id: string, status: ComplaintStatus) =>
    req<Complaint>(`/complaints/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  dispatch: (id: string, worker_id: string, approved_by?: string) =>
    req<Assignment>(`/complaints/${id}/dispatch`, {
      method: "POST",
      body: JSON.stringify({ worker_id, approved_by }),
    }),

  // Workers
  listWorkers: (category?: string) => req<Worker[]>("/workers", {}, { category }),
  createWorker: (w: {
    phone: string;
    name: string;
    categories: string[];
    wa_jid?: string;
    notes?: string;
  }) => req<Worker>("/workers", { method: "POST", body: JSON.stringify(w) }),
  updateWorker: (id: string, patch: Partial<Worker>) =>
    req<Worker>(`/workers/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),

  // Residents
  listResidents: (q?: string) => req<Resident[]>("/residents", {}, { q }),

  // Stats
  stats: () => req<{ by_status: Record<string, number> }>("/stats"),

  // Auth (called from NextAuth credentials provider)
  login: (email: string, password: string) =>
    req<{ id: string; email: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  // Test alert
  testAlert: (body: string) =>
    req<{ ok: boolean }>("/admin/test-alert", {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
};
