import { RunListItem, ValidationResult } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function createRun(form: FormData): Promise<{ run_id: string; status: string; error?: string }> {
  const res = await fetch(`${API_BASE}/api/runs`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to create validation run");
  }
  return res.json();
}

export async function getRunStatus(runId: string): Promise<{ run_id: string; status: string; error: string | null }> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch run status");
  return res.json();
}

export async function getRunResults(runId: string): Promise<ValidationResult> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/results`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch run results");
  return res.json();
}

export async function listRuns(): Promise<RunListItem[]> {
  const res = await fetch(`${API_BASE}/api/runs`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch run history");
  return res.json();
}
