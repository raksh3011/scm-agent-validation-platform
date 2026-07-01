"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";
import { Skeleton } from "../../../../components/ui/skeleton";
import { useRunResults, useSubjectHistory } from "../../../../lib/queries";
import { cn } from "../../../../lib/utils";

function DiffCell({ a, b }: { a: number | null | undefined; b: number | null | undefined }) {
  if (a == null || b == null) return <span className="text-muted-foreground">—</span>;
  const delta = Number((b - a).toFixed(2));
  return (
    <span className={cn("text-xs font-medium", delta > 0 && "text-success", delta < 0 && "text-destructive")}>
      {delta > 0 ? "+" : ""}{delta}
    </span>
  );
}

export default function CompareRunsPage() {
  const params = useParams<{ subjectId: string }>();
  const { data: history } = useSubjectHistory(params.subjectId);
  const runs = history?.runs ?? [];
  const [runA, setRunA] = useState<string>("");
  const [runB, setRunB] = useState<string>("");

  const a = useRunResults(runA || "__none__");
  const b = useRunResults(runB || "__none__");

  if (!history) return <Skeleton className="h-64 w-full" />;

  const effectiveA = runA || runs[runs.length - 2]?.run_id || "";
  const effectiveB = runB || runs[runs.length - 1]?.run_id || "";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Compare Runs</h1>
      <div className="flex flex-wrap gap-4">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Run A (baseline)</p>
          <Select value={effectiveA} onValueChange={setRunA}>
            <SelectTrigger className="w-64"><SelectValue placeholder="Select run" /></SelectTrigger>
            <SelectContent>{runs.map((r) => <SelectItem key={r.run_id} value={r.run_id}>{r.run_id}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Run B (comparison)</p>
          <Select value={effectiveB} onValueChange={setRunB}>
            <SelectTrigger className="w-64"><SelectValue placeholder="Select run" /></SelectTrigger>
            <SelectContent>{runs.map((r) => <SelectItem key={r.run_id} value={r.run_id}>{r.run_id}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>

      {a.isLoading || b.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : a.data?.applicable && b.data?.applicable ? (
        <>
          <Card>
            <CardHeader><CardTitle className="text-base">Trust Score Breakdown</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="bg-muted/40">
                  <tr>
                    {["Dimension", "Run A", "Run B", "Delta"].map((h) => (
                      <th key={h} className="px-4 py-2 text-left font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(a.data.trust_scores ?? []).map((dimA) => {
                    const dimB = (b.data?.trust_scores ?? []).find((t) => t.dimension === dimA.dimension);
                    return (
                      <tr key={dimA.dimension} className="border-t border-border">
                        <td className="px-4 py-2 capitalize">{dimA.dimension.replace(/_/g, " ")}</td>
                        <td className="px-4 py-2 tabular-nums">{dimA.score}/{dimA.max_score}</td>
                        <td className="px-4 py-2 tabular-nums">{dimB ? `${dimB.score}/${dimB.max_score}` : "—"}</td>
                        <td className="px-4 py-2"><DiffCell a={dimA.score} b={dimB?.score} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Business KPIs</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="bg-muted/40">
                  <tr>
                    {["KPI", "Run A", "Run B", "Delta"].map((h) => (
                      <th key={h} className="px-4 py-2 text-left font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(a.data.kpis ?? []).map((kA) => {
                    const kB = (b.data?.kpis ?? []).find((k) => k.name === kA.name);
                    return (
                      <tr key={kA.name} className="border-t border-border">
                        <td className="px-4 py-2 capitalize">{kA.name.replace(/_/g, " ")}</td>
                        <td className="px-4 py-2 tabular-nums">{kA.value} {kA.unit}</td>
                        <td className="px-4 py-2 tabular-nums">{kB ? `${kB.value} ${kB.unit}` : "—"}</td>
                        <td className="px-4 py-2"><DiffCell a={kA.value} b={kB?.value} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Select two completed, applicable runs to compare.</p>
      )}
    </div>
  );
}
