"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Skeleton } from "../../../components/ui/skeleton";
import { useRerunSubject, useSubjectHistory } from "../../../lib/queries";

export default function SubjectTrendPage() {
  const params = useParams<{ subjectId: string }>();
  const { data: history, error, isLoading } = useSubjectHistory(params.subjectId);
  const rerun = useRerunSubject();
  const [rerunMsg, setRerunMsg] = useState<string | null>(null);

  async function handleRerun() {
    try {
      const res = await rerun.mutateAsync(params.subjectId);
      setRerunMsg(`Re-validation queued: run ${res.run_id}`);
    } catch (e) {
      setRerunMsg(e instanceof Error ? e.message : "Failed to trigger re-run");
    }
  }

  if (error) {
    return <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-destructive">{(error as Error).message}</div>;
  }
  if (isLoading || !history) {
    return <Skeleton className="h-64 w-full" />;
  }

  const chartData = history.runs.map((r) => ({
    run: r.run_id.slice(0, 8),
    score: r.overall_trust_score ?? 0,
    created: new Date(r.created_at).toLocaleDateString(),
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Trust Score Trend</h1>
        <div className="flex items-center gap-2">
          {history.runs.length >= 2 && (
            <Button variant="outline" asChild>
              <Link href={`/history/${params.subjectId}/compare`}>Compare Runs</Link>
            </Button>
          )}
          <Button onClick={handleRerun} disabled={rerun.isPending}>
            {rerun.isPending ? "Queuing…" : "Trigger Continuous Re-validation"}
          </Button>
        </div>
      </div>
      {rerunMsg && <p className="text-sm text-muted-foreground">{rerunMsg}</p>}

      <Card>
        <CardContent className="h-72 pt-6">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="run" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="score" stroke="var(--color-primary)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr>
                {["Run", "Trust Score", "Readiness", "Created"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.runs.map((r) => (
                <tr key={r.run_id} className="border-t border-border">
                  <td className="px-4 py-3"><Link href={`/runs/${r.run_id}/results`} className="text-primary hover:underline">{r.run_id}</Link></td>
                  <td className="px-4 py-3 font-semibold tabular-nums">{r.overall_trust_score ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.production_readiness ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {history.deltas.length > 0 && (
        <div>
          <h3 className="mb-3 text-lg font-semibold">Run-over-run Changes</h3>
          <div className="space-y-3">
            {history.deltas.map((d) => (
              <Card key={d.run_id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{d.previous_run_id} → {d.run_id}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p className="text-muted-foreground">Score delta: <span className="font-medium text-foreground">{d.score_delta}</span></p>
                  {d.new_defects.length > 0 && <p className="text-destructive">New defect types: {d.new_defects.join(", ")}</p>}
                  {d.resolved_defects.length > 0 && <p className="text-success">Resolved defect types: {d.resolved_defects.join(", ")}</p>}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
