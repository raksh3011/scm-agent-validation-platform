import { RunListItem, RunResults, SubjectHistory } from "./types";
import { ensureApiKey } from "./apiKey";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8008";

async function authHeaders(): Promise<HeadersInit> {
  const key = await ensureApiKey(API_BASE);
  return { "X-API-Key": key };
}

export async function createRun(form: FormData): Promise<{ run_id: string; status: string; error?: string }> {
  const res = await fetch(`${API_BASE}/api/runs`, { method: "POST", body: form, headers: await authHeaders() });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to create validation run");
  }
  return res.json();
}

export interface RunProgress {
  current_stage: string;
  stages_done: number;
  stages_total: number;
  last_stage_status?: string;
  scenarios_done?: number;
  scenarios_total?: number;
}

export async function getRunStatus(runId: string): Promise<{
  run_id: string; status: string; error: string | null; progress: RunProgress | null;
}> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/status`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch run status");
  return res.json();
}

export async function getRunResults(runId: string): Promise<RunResults> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/results`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch run results");
  return res.json();
}

export async function listRuns(): Promise<RunListItem[]> {
  const res = await fetch(`${API_BASE}/api/runs`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch run history");
  return res.json();
}

export async function getSubjectHistory(subjectId: string): Promise<SubjectHistory> {
  const res = await fetch(`${API_BASE}/api/history/${subjectId}`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch subject history");
  return res.json();
}

export async function compareRuns(runIdA: string, runIdB: string): Promise<import("./types").ComparisonReport> {
  const res = await fetch(`${API_BASE}/api/history/compare/${runIdA}/${runIdB}`, {
    cache: "no-store",
    headers: await authHeaders(),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to compare runs");
  }
  return res.json();
}

export async function downloadReport(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/reports/${runId}`, { headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to download report");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${runId}_assurance_report.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function rerunSubject(subjectId: string): Promise<{ run_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/runs/${subjectId}/rerun`, { method: "POST", headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to trigger re-run");
  return res.json();
}
