"use server";

import { getServerSession } from "next-auth";
import { revalidatePath } from "next/cache";
import { authOptions } from "@/lib/auth";

const BASE = process.env.SKILLS_API_BASE_URL || "http://skills:8080";
const TOKEN = process.env.SKILLS_API_TOKEN || "dev-token";

async function requireAdmin() {
  const session = await getServerSession(authOptions);
  if (!session) throw new Error("unauthorized");
}

export async function createAdminAction(formData: FormData) {
  await requireAdmin();
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  if (!email || password.length < 8) {
    return { error: "email and password (>=8 chars) required" };
  }
  const r = await fetch(`${BASE}/admins`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, role: "admin" }),
  });
  if (!r.ok) return { error: await r.text() };
  revalidatePath("/settings");
  return { ok: true };
}

export async function deleteAdminAction(id: string) {
  await requireAdmin();
  const r = await fetch(`${BASE}/admins/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  if (!r.ok) return { error: await r.text() };
  revalidatePath("/settings");
  return { ok: true };
}

export async function testAlertAction(body: string) {
  await requireAdmin();
  const r = await fetch(`${BASE}/admin/test-alert`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  if (!r.ok) return { error: await r.text() };
  return { ok: true };
}
