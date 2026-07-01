"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { useCompareRuns } from "../../lib/queries";
import {
  ComparisonVerdict, DefectDeltaRecord, KpiDeltaRecord, ScenarioFlipRecord, TrustDimensionDeltaRecord,
} from "../../lib/types";
import { cn } from "../../lib/utils";

const VERDICT_STYLE: Record<ComparisonVerdict, { label: string; className: string }> = {
  improved: { label: "Improved", className: "bg-success/15 text-success border-success/30" },
  regressed: { label: "Regressed", className: "bg-destructive/15 text-destructive border-destructive/30" },
  mixed: { label: "Mixed", className: "bg-warning/15 text-warning border-warning/30" },
  unchanged: { label: "Unchanged", className: "bg-muted text-muted-foreground border-border" },
  not_comparable: { label: "Not Comparable", className: "bg-muted text-muted-foreground border-dashed border-border" },
};

export default function ComparePage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <CompareContent />
    </Suspense>
  );
}

function CompareContent() {
  const params = useSearchParams();
  const a = params.get("a");
  const b = params.get("b");
  const { data, error, isLoading } = useCompareRuns(a, b);

  if (!a || !b) {
    return <p className="text-sm text-muted-foreground">Select two completed runs from the History page to compare.</p>;
  }
  if (error) {
    return <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-destructive">{(error as Error).message}</div>;
  }
  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const verdict = VERDICT_STYLE[data.verdict];
  const newDefects = data.defect_deltas.filter((d) => d.status === "new");
  const resolvedDefects = data.defect_deltas.filter((d) => d.status === "resolved");
  const persistingDefects = data.defect_deltas.filter((d) => d.status === "persisting");
  const regressions = data.scenario_flips.filter((f) => f.direction === "regression");
  const improvements = data.scenario_flips.filter((f) => f.direction === "improvement");

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }} className="space-y-6">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium">{data.run_a.agent_name}</span>
            <span className="text-xs text-muted-foreground font-mono">{data.run_a.run_id}</span>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{data.run_b.agent_name}</span>
            <span className="text-xs text-muted-foreground font-mono">{data.run_b.run_id}</span>
          </div>
          <Badge className={cn("border", verdict.className)}>{verdict.label}</Badge>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 pt-6">
          <div className="flex items-center gap-4">
            <ScoreCell label="Before" value={data.run_a.overall_trust_score} />
            <ArrowRight className="h-5 w-5 text-muted-foreground" />
            <ScoreCell label="After" value={data.run_b.overall_trust_score} />
            <DeltaBadge delta={data.score_delta} suffix=" pts" />
          </div>
          <p className="text-sm text-muted-foreground">{data.summary}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Trust Dimension Changes</CardTitle></CardHeader>
        <CardContent className="p-0">
          <TrustDeltaTable rows={data.trust_deltas} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <DefectColumn title="New Defects" tone="destructive" defects={newDefects} />
        <DefectColumn title="Resolved Defects" tone="success" defects={resolvedDefects} />
        <DefectColumn title="Persisting Defects" tone="muted" defects={persistingDefects} />
      </div>

      {data.kpi_deltas.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Business KPI Evolution</CardTitle></CardHeader>
          <CardContent className="p-0">
            <KpiDeltaTable rows={data.kpi_deltas} />
          </CardContent>
        </Card>
      )}

      {data.conformance_deltas.some((c) => c.before !== null || c.after !== null) && (
        <Card>
          <CardHeader><CardTitle>Specification Conformance Evolution</CardTitle></CardHeader>
          <CardContent className="space-y-2 pt-2">
            {data.conformance_deltas.map((c) => (
              <div key={c.metric} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{c.metric.replace(/_/g, " ")}</span>
                <div className="flex items-center gap-2">
                  <span className="tabular-nums">{c.before ?? "—"}</span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="tabular-nums">{c.after ?? "—"}</span>
                  <DeltaBadge delta={c.delta} suffix="%" />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <ScenarioFlipColumn title="Scenario Regressions" tone="destructive" flips={regressions} />
        <ScenarioFlipColumn title="Scenario Improvements" tone="success" flips={improvements} />
      </div>
    </motion.div>
  );
}

function ScoreCell({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold tabular-nums">{value ?? "—"}</p>
    </div>
  );
}

function DeltaBadge({ delta, suffix = "" }: { delta: number | null; suffix?: string }) {
  if (delta === null) return <span className="text-xs text-muted-foreground">not comparable</span>;
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  const tone = delta > 0 ? "text-success" : delta < 0 ? "text-destructive" : "text-muted-foreground";
  return (
    <span className={cn("flex items-center gap-1 text-sm font-semibold tabular-nums", tone)}>
      <Icon className="h-3.5 w-3.5" />
      {delta > 0 ? "+" : ""}{delta}{suffix}
    </span>
  );
}

function TrustDeltaTable({ rows }: { rows: TrustDimensionDeltaRecord[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr>
            {["Dimension", "Category", "Before", "After", "Δ"].map((h) => (
              <th key={h} className="px-4 py-2 text-left font-medium text-muted-foreground">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.dimension} className="border-t border-border">
              <td className="px-4 py-2 font-medium capitalize">{r.dimension.replace(/_/g, " ")}</td>
              <td className="px-4 py-2 text-xs text-muted-foreground">{r.category.replace(/_/g, " ")}</td>
              <td className="px-4 py-2 tabular-nums">{r.score_before ?? "—"}{r.score_before !== null ? `/${r.max_score}` : ""}</td>
              <td className="px-4 py-2 tabular-nums">{r.score_after ?? "—"}{r.score_after !== null ? `/${r.max_score}` : ""}</td>
              <td className="px-4 py-2"><DeltaBadge delta={r.delta} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KpiDeltaTable({ rows }: { rows: KpiDeltaRecord[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr>
            {["KPI", "Before", "After", "Δ"].map((h) => (
              <th key={h} className="px-4 py-2 text-left font-medium text-muted-foreground">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className="border-t border-border">
              <td className="px-4 py-2 font-medium capitalize">{r.name.replace(/_/g, " ")}</td>
              <td className="px-4 py-2 tabular-nums">{r.value_before ?? "—"} {r.unit}</td>
              <td className="px-4 py-2 tabular-nums">{r.value_after ?? "—"} {r.unit}</td>
              <td className="px-4 py-2"><DeltaBadge delta={r.delta} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TONE_BORDER: Record<string, string> = {
  destructive: "border-destructive/30",
  success: "border-success/30",
  muted: "border-border",
};
const TONE_BADGE: Record<string, string> = {
  destructive: "bg-destructive/15 text-destructive",
  success: "bg-success/15 text-success",
  muted: "bg-muted text-muted-foreground",
};

function DefectColumn({ title, tone, defects }: { title: string; tone: string; defects: DefectDeltaRecord[] }) {
  return (
    <Card className={cn("border", TONE_BORDER[tone])}>
      <CardHeader><CardTitle className="text-sm">{title} ({defects.length})</CardTitle></CardHeader>
      <CardContent className="space-y-2 pt-0">
        {defects.length === 0 && <p className="text-xs text-muted-foreground">None</p>}
        {defects.map((d) => (
          <div key={d.defect_type} className="rounded-md border border-border p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{d.title}</span>
              {d.severity_change && d.severity_change !== "unchanged" && (
                <Badge className={cn(TONE_BADGE[d.severity_change === "worse" ? "destructive" : "success"], "text-[10px]")}>
                  {d.severity_change}
                </Badge>
              )}
            </div>
            <p className="mt-1 text-muted-foreground">
              {d.severity_before ?? "—"} → {d.severity_after ?? "—"} · {d.category}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ScenarioFlipColumn({ title, tone, flips }: { title: string; tone: string; flips: ScenarioFlipRecord[] }) {
  return (
    <Card className={cn("border", TONE_BORDER[tone])}>
      <CardHeader><CardTitle className="text-sm">{title} ({flips.length})</CardTitle></CardHeader>
      <CardContent className="max-h-72 space-y-1.5 overflow-auto pt-0">
        {flips.length === 0 && <p className="text-xs text-muted-foreground">None</p>}
        {flips.map((f) => (
          <div key={f.name} className="flex items-center justify-between rounded-md border border-border px-2 py-1.5 text-xs">
            <span className="truncate font-mono">{f.name}</span>
            <span className="flex items-center gap-1 text-muted-foreground">
              {f.status_before} <ArrowRight className="h-3 w-3" /> {f.status_after}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
