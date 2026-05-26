"use server";

import { getServerSession } from "next-auth";
import { api, type ComplaintStatus } from "@/lib/api";
import { authOptions } from "@/lib/auth";

async function requireAdmin() {
  const session = await getServerSession(authOptions);
  if (!session) throw new Error("unauthorized");
  return session;
}

export async function dispatchAction(
  complaintId: string,
  workerId: string,
  adminId?: string,
): Promise<{ ok: true } | { error: string }> {
  try {
    await requireAdmin();
    await api.dispatch(complaintId, workerId, adminId);
    return { ok: true };
  } catch (e: any) {
    return { error: e?.message || "dispatch failed" };
  }
}

export async function setStatusAction(
  complaintId: string,
  status: ComplaintStatus,
): Promise<{ ok: true } | { error: string }> {
  try {
    await requireAdmin();
    await api.setComplaintStatus(complaintId, status);
    return { ok: true };
  } catch (e: any) {
    return { error: e?.message || "status update failed" };
  }
}
