"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Activity, CheckCircle2, GitCompare, ShieldAlert } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Skeleton } from "../../components/ui/skeleton";
import { useRunsList } from "../../lib/queries";
import { cn } from "../../lib/utils";

const READINESS_BADGE: Record<string, string> = {
  "Production Ready": "bg-success/15 text-success border-success/30",
  Conditional: "bg-warning/15 text-warning border-warning/30",
  "Not Ready": "bg-destructive/15 text-destructive border-destructive/30",
  "Insufficient Evidence": "bg-muted text-muted-foreground border-border",
};

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-success/15 text-success border-success/30",
  running: "bg-primary/15 text-primary border-primary/30",
  queued: "bg-muted text-muted-foreground border-border",
  failed: "bg-destructive/15 text-destructive border-destructive/30",
};

function scoreTone(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-destructive";
}

export default function HistoryPage() {
  const router = useRouter();
  const { data: runs, error, isLoading } = useRunsList();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const filtered = (runs ?? []).filter((r) =>
    search === "" || r.agent_name.toLowerCase().includes(search.toLowerCase()));

  const stats = useMemo(() => {
    const completed = (runs ?? []).filter((r) => r.status === "completed" && r.applicable);
    const scored = completed.filter((r) => r.overall_trust_score !== null);
    const avg = scored.length ? scored.reduce((s, r) => s + (r.overall_trust_score ?? 0), 0) / scored.length : null;
    const ready = completed.filter((r) => r.production_readiness === "Production Ready").length;
    return { total: runs?.length ?? 0, avg, ready, completed: completed.length };
  }, [runs]);

  function toggleSelect(runId: string) {
    setSelected((prev) => {
      if (prev.includes(runId)) return prev.filter((id) => id !== runId);
      if (prev.length >= 2) return [prev[1], runId];
      return [...prev, runId];
    });
  }

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Continuous Audit Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Every validation run, with side-by-side comparison across versions.</p>
        </div>
        <div className="flex items-center gap-3">
          <Input placeholder="Search agents…" value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
          <Button
            disabled={selected.length !== 2}
            onClick={() => router.push(`/compare?a=${selected[0]}&b=${selected[1]}`)}
          >
            <GitCompare className="mr-2 h-4 w-4" /> Compare Selected ({selected.length}/2)
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile icon={Activity} label="Total Runs" value={String(stats.total)} />
        <StatTile icon={ShieldAlert} label="Average Trust Score" value={stats.avg !== null ? stats.avg.toFixed(1) : "—"} tone={scoreTone(stats.avg)} />
        <StatTile icon={CheckCircle2} label="Production Ready" value={`${stats.ready} / ${stats.completed}`} />
      </div>

      {error && <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-destructive">{(error as Error).message}</div>}
      {isLoading && <Skeleton className="h-64 w-full" />}
      {runs && filtered.length === 0 && <p className="text-sm text-muted-foreground">No validation runs yet. Start one from "New Validation".</p>}

      {filtered.length > 0 && (
        <Card className="overflow-hidden">
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Compare</th>
                  {["Agent", "Agent Type", "Source", "Status", "Trust Score", "Readiness", "Created", "Trend"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.run_id} className={cn("border-t border-border transition-colors hover:bg-accent/30", selected.includes(r.run_id) && "bg-primary/5")}>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.includes(r.run_id)}
                        disabled={r.status !== "completed"}
                        onChange={() => toggleSelect(r.run_id)}
                        className="h-4 w-4 rounded border-border accent-primary disabled:opacity-30"
                      />
                    </td>
                    <td className="px-4 py-3">
                      {r.status === "completed" ? (
                        <Link href={`/runs/${r.run_id}/results`} className="font-medium text-primary hover:underline">{r.agent_name}</Link>
                      ) : (
                        <span>{r.agent_name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {r.applicable ? (r.primary_agent_type ?? "—").replace(/_/g, " ") : "not applicable"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{r.source_type}</td>
                    <td className="px-4 py-3">
                      <Badge className={cn("border", STATUS_BADGE[r.status] ?? "")}>{r.status}</Badge>
                    </td>
                    <td className={cn("px-4 py-3 font-semibold tabular-nums", scoreTone(r.overall_trust_score))}>
                      {r.overall_trust_score ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {r.production_readiness ? (
                        <Badge className={cn("border text-[11px]", READINESS_BADGE[r.production_readiness] ?? "")}>
                          {r.production_readiness}
                        </Badge>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <Link href={`/history/${r.subject_id}`} className="text-primary hover:underline">View trend</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function StatTile({ icon: Icon, label, value, tone }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: string; tone?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 pt-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className={cn("text-xl font-semibold tabular-nums", tone)}>{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
