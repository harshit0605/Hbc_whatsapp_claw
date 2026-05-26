"use server";

import { getServerSession } from "next-auth";
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { authOptions } from "@/lib/auth";

async function requireAdmin() {
  const session = await getServerSession(authOptions);
  if (!session) throw new Error("unauthorized");
}

export async function createWorkerAction(formData: FormData) {
  await requireAdmin();
  const phone = String(formData.get("phone") || "").trim();
  const name = String(formData.get("name") || "").trim();
  const cats = String(formData.get("categories") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!phone || !name) return { error: "name and phone required" };
  try {
    await api.createWorker({ phone, name, categories: cats });
    revalidatePath("/workers");
    return { ok: true };
  } catch (e: any) {
    return { error: e?.message || "failed" };
  }
}

export async function toggleActiveAction(id: string, active: boolean) {
  await requireAdmin();
  await api.updateWorker(id, { is_active: !active });
  revalidatePath("/workers");
}
