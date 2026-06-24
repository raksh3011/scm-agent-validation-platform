"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listRuns } from "../../lib/api";
import { RunListItem } from "../../lib/types";

export default function HistoryPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns().then(setRuns).catch((e) => setError(e instanceof Error ? e.message : "Failed to load history"));
  }, []);

  return (
    <div className="shell">
      <h1>Validation History</h1>
      {error && <div className="card" style={{ background: "#fef2f2", borderColor: "#fecaca" }}>{error}</div>}
      {!runs && !error && <p className="muted">Loading…</p>}
      {runs && runs.length === 0 && <p className="muted">No validation runs yet. Start one from “New Validation”.</p>}

      {runs && runs.length > 0 && (
        <table className="card">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Source</th>
              <th>Status</th>
              <th>Trust Score</th>
              <th>Demo</th>
              <th>Production</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td>
                  {r.status === "completed" ? (
                    <Link href={`/runs/${r.run_id}/results`}>{r.agent_name}</Link>
                  ) : (
                    <span>{r.agent_name}</span>
                  )}
                </td>
                <td className="small muted">{r.source_type}</td>
                <td className="small">{r.status}</td>
                <td>{r.overall_trust_score ?? "—"}</td>
                <td className="small">{r.demo_readiness ?? "—"}</td>
                <td className="small">{r.production_readiness ?? "—"}</td>
                <td className="small muted">{new Date(r.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
