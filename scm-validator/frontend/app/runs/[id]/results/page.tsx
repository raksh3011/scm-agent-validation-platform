"use client";

import { Fragment, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { Download, FileText, GitFork } from "lucide-react";
import {
  PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer,
} from "recharts";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";
import { Input } from "../../../../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";
import { Skeleton } from "../../../../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../../../components/ui/tabs";
import TrustGauge from "../../../../components/TrustGauge";
import KpiCard from "../../../../components/KpiCard";
import ScenarioHeatmap, { HeatmapCell } from "../../../../components/ScenarioHeatmap";
import RiskHeatmap from "../../../../components/RiskHeatmap";
import CapabilityGraph from "../../../../components/CapabilityGraph";
import DefectExplorer from "../../../../components/DefectExplorer";
import DecisionTraceFlow, { DecisionTraceSummary } from "../../../../components/DecisionTraceFlow";
import RootCausePanel from "../../../../components/RootCausePanel";
import PipelineStages from "../../../../components/PipelineStages";
import { useRunResults } from "../../../../lib/queries";
import { downloadReport } from "../../../../lib/api";
import {
  AgentSpecificationRecord, ConformanceSummaryRecord, DefectRecord, EvalGenStatsRecord,
  RequirementStatus, ScenarioExecutionRecord, ScenarioRecord, Severity, TrustScoreRecord,
} from "../../../../lib/types";
import { cn } from "../../../../lib/utils";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];
const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "bg-destructive text-destructive-foreground",
  high: "bg-orange-500 text-white",
  medium: "bg-warning text-foreground",
  low: "bg-muted text-muted-foreground",
};
const STATUS_COLOR: Record<string, string> = {
  pass: "bg-success/15 text-success",
  fail: "bg-destructive/15 text-destructive",
  partial: "bg-warning/15 text-warning",
  error: "bg-muted text-muted-foreground",
};

export default function ResultsPage() {
  const params = useParams<{ id: string }>();
  const { data: result, error, isLoading } = useRunResults(params.id);
  const [activeTab, setActiveTab] = useState("overview");

  if (error) {
    return <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-destructive">{(error as Error).message}</div>;
  }
  if (isLoading || !result) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!result.applicable) {
    return (
      <Card className="border-warning/40 bg-warning/5">
        <CardHeader>
          <CardTitle>Not Applicable</CardTitle>
        </CardHeader>
        <CardContent>
          <p>This submission was not scored. {result.summary.not_applicable_reason}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {result.summary.primary_agent_type
              ? `Detected agent type: ${result.summary.primary_agent_type.replace(/_/g, " ")} (confidence ${Math.round((result.summary.classification_confidence ?? 0) * 100)}%).`
              : "No SCM decision logic could be identified."}
          </p>
        </CardContent>
      </Card>
    );
  }

  const scenarios = result.scenarios ?? [];
  const executions = result.executions ?? [];
  const defects = result.defects ?? [];
  const trustScores = result.trust_scores ?? [];
  const kpis = result.kpis ?? [];
  const decisionTraces = result.decision_traces ?? {};
  const rootCauses = result.root_causes ?? [];
  const scenarioById = new Map(scenarios.map((s) => [s.id, s]));

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }} className="space-y-6">
      <SummaryHeader result={result} />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="catalogue">Test Case Catalogue ({scenarios.length})</TabsTrigger>
          <TabsTrigger value="trace">Decision Trace</TabsTrigger>
          <TabsTrigger value="rootcause">Root Causes ({rootCauses.length})</TabsTrigger>
          <TabsTrigger value="defects">Defects ({defects.length})</TabsTrigger>
          <TabsTrigger value="trust">Trust Score</TabsTrigger>
          <TabsTrigger value="specification">Specification</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <Overview executions={executions} scenarios={scenarios} kpis={kpis} defects={defects} result={result} />
        </TabsContent>
        <TabsContent value="pipeline" className="mt-4">
          <PipelineStages stages={result.stages ?? []} />
        </TabsContent>
        <TabsContent value="catalogue" className="mt-4">
          <ScenarioMatrix scenarios={scenarios} executions={executions} />
        </TabsContent>
        <TabsContent value="trace" className="mt-4">
          <DecisionTraceTab scenarioById={scenarioById} decisionTraces={decisionTraces} executions={executions} />
        </TabsContent>
        <TabsContent value="rootcause" className="mt-4">
          <RootCausePanel rootCauses={rootCauses} />
        </TabsContent>
        <TabsContent value="defects" className="mt-4 space-y-6">
          <div>
            <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Risk Matrix (severity × category)</h3>
            <RiskHeatmap defects={defects} />
          </div>
          <div>
            <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Defect Explorer</h3>
            <DefectExplorer defects={defects} />
          </div>
        </TabsContent>
        <TabsContent value="trust" className="mt-4">
          <TrustRadar trustScores={trustScores} overall={result.summary.overall_trust_score} readiness={result.summary.production_readiness} />
        </TabsContent>
        <TabsContent value="specification" className="mt-4 space-y-6">
          <div>
            <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Business Capability Graph</h3>
            <CapabilityGraph graph={result.capability_graph ?? null} />
          </div>
          <SpecificationTab
            asdSpec={result.asd_spec ?? null}
            conformance={result.conformance ?? null}
            evalgenStats={result.evalgen_stats ?? null}
            scenarios={scenarios}
          />
        </TabsContent>
        <TabsContent value="history" className="mt-4">
          <HistoryDelta delta={result.historical_delta ?? null} />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

const READINESS_ACCENT: Record<string, string> = {
  "Production Ready": "before:bg-success",
  Conditional: "before:bg-warning",
  "Not Ready": "before:bg-destructive",
  "Insufficient Evidence": "before:bg-muted-foreground",
};

function SummaryHeader({ result }: { result: NonNullable<ReturnType<typeof useRunResults>["data"]> }) {
  const { summary } = result;
  const readiness = summary.production_readiness ?? "Insufficient Evidence";
  const defectCount = (result.defects ?? []).length;
  const scenarioCount = (result.scenarios ?? []).length;
  const conformance = result.conformance?.conformance_score;
  const asdSpec = result.asd_spec;

  return (
    <Card className={cn(
      "relative overflow-hidden before:absolute before:inset-y-0 before:left-0 before:w-1.5",
      READINESS_ACCENT[readiness] ?? "before:bg-border"
    )}>
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/[0.04] via-transparent to-transparent" />
      <CardContent className="relative flex flex-col gap-6 pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{summary.agent_name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Run <span className="font-mono">{summary.run_id}</span> · {new Date(summary.updated_at).toLocaleString()}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Classified as <span className="font-medium text-foreground">{(summary.primary_agent_type ?? "unknown").replace(/_/g, " ")}</span>{" "}
            ({Math.round((summary.classification_confidence ?? 0) * 100)}% confidence)
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge
              variant={readiness === "Insufficient Evidence" ? "secondary" : "outline"}
              className={cn(readiness === "Insufficient Evidence" && "border-warning/40 bg-warning/10 text-warning")}
            >
              {readiness}
            </Badge>
            <span className="text-xs text-muted-foreground">{scenarioCount} scenarios · {defectCount} defects</span>
            {conformance !== null && conformance !== undefined && (
              <span className="text-xs text-muted-foreground">· {conformance.toFixed(0)}% spec conformance</span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {summary.source_type === "repo_url" && summary.source_ref ? (
              <a href={summary.source_ref} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-primary hover:underline">
                <GitFork className="h-3.5 w-3.5" /> {summary.source_ref.replace(/^https?:\/\/(www\.)?github\.com\//, "")}
              </a>
            ) : summary.source_ref ? (
              <span className="flex items-center gap-1"><GitFork className="h-3.5 w-3.5" /> {summary.source_type}: {summary.source_ref}</span>
            ) : null}
            {asdSpec ? (
              <span className="flex items-center gap-1">
                <FileText className="h-3.5 w-3.5" /> Spec: {asdSpec.source_name}
                {asdSpec.business_objective ? ` — ${asdSpec.business_objective}` : ""}
              </span>
            ) : (
              <span className="flex items-center gap-1 italic"><FileText className="h-3.5 w-3.5" /> No Agent Specification uploaded</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-6">
          <TrustGauge score={summary.overall_trust_score} label="Trust Score / 100" />
          <Button onClick={() => downloadReport(summary.run_id)}>
            <Download className="mr-2 h-4 w-4" /> PDF Report
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Overview({ executions, scenarios, kpis, defects, result }: {
  executions: ScenarioExecutionRecord[]; scenarios: ScenarioRecord[]; kpis: any[]; defects: DefectRecord[];
  result: NonNullable<ReturnType<typeof useRunResults>["data"]>;
}) {
  const total = executions.length || 1;
  const passed = executions.filter((e) => e.status === "pass").length;
  const failed = executions.filter((e) => e.status === "fail").length;
  const partial = executions.filter((e) => e.status === "partial").length;
  const errored = executions.filter((e) => e.status === "error").length;
  const scenarioById = new Map(scenarios.map((s) => [s.id, s]));
  const cells: HeatmapCell[] = executions.map((e) => ({
    category: scenarioById.get(e.scenario_id)?.category ?? "uncategorized",
    status: e.status,
  }));
  const topDefects = [...defects].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)).slice(0, 4);

  const insufficientEvidence = result.summary.production_readiness === "Insufficient Evidence";

  return (
    <div className="space-y-6">
      {insufficientEvidence && (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="pt-5 text-sm">
            <p className="font-medium text-warning">Business validation did not run for this submission.</p>
            <p className="mt-1 text-muted-foreground">
              The agent&apos;s entrypoint never became reachable during sandbox validation — see the{" "}
              <span className="font-medium text-foreground">Pipeline</span> tab for exactly which stage failed,
              and <span className="font-medium text-foreground">Root Causes</span> for a recovery suggestion.
              Business, operational, and KPI metrics below are marked unknown rather than scored as zero.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatCard label="Total" value={total} />
        <StatCard label="Passed" value={passed} tone="success" />
        <StatCard label="Failed" value={failed} tone="destructive" />
        <StatCard label="Partial" value={partial} tone="warning" />
        <StatCard label="Errors" value={errored} />
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Business KPIs</h3>
        {kpis.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {kpis.map((k, i) => <KpiCard key={k.name} kpi={k} index={i} />)}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {insufficientEvidence
              ? "Not computable — business execution never ran."
              : "No business KPIs were computable for this run."}
          </p>
        )}
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Scenario Heatmap (category × status)</h3>
        <ScenarioHeatmap cells={cells} />
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Top Defects & Business Risks</h3>
        {topDefects.length === 0 && <p className="text-sm text-muted-foreground">No defects identified that meet the evidence threshold.</p>}
        <div className="space-y-2">
          {topDefects.map((d) => (
            <Card key={d.id}>
              <CardContent className="flex items-start gap-3 py-4">
                <Badge className={cn(SEVERITY_COLOR[d.severity])}>{d.severity.toUpperCase()}</Badge>
                <div>
                  <p className="font-medium">{d.title}</p>
                  <p className="text-sm text-muted-foreground">{d.business_impact}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "success" | "destructive" | "warning" }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className={cn("text-2xl font-bold tabular-nums", tone === "success" && "text-success", tone === "destructive" && "text-destructive", tone === "warning" && "text-warning")}>
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

function sourceLabel(tag: string): string {
  if (tag === "evalgen_pairwise") return "pairwise testing";
  return tag.replace(/_/g, " ");
}

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-destructive", high: "bg-orange-500", medium: "bg-warning", low: "bg-muted-foreground",
};

function ScenarioMatrix({ scenarios, executions }: { scenarios: ScenarioRecord[]; executions: ScenarioExecutionRecord[] }) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const execById = new Map(executions.map((e) => [e.scenario_id, e]));
  const categories = useMemo(() => Array.from(new Set(scenarios.map((s) => s.category))).sort(), [scenarios]);
  const sources = useMemo(
    () => Array.from(new Set(scenarios.flatMap((s) => s.traceability?.generated_by ?? []))).sort(),
    [scenarios]
  );

  const rows = scenarios
    .map((s) => ({ scenario: s, execution: execById.get(s.id) }))
    .filter(({ scenario, execution }) =>
      (statusFilter === "all" || execution?.status === statusFilter) &&
      (categoryFilter === "all" || scenario.category === categoryFilter) &&
      (sourceFilter === "all" || (scenario.traceability?.generated_by ?? []).includes(sourceFilter)) &&
      (search === "" || scenario.name.toLowerCase().includes(search.toLowerCase()) || scenario.id.toLowerCase().includes(search.toLowerCase()))
    );

  const counts = { pass: 0, partial: 0, fail: 0, error: 0, not_executed: 0 };
  for (const e of executions) counts[e.status] = (counts[e.status] ?? 0) + 1;

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-muted-foreground">Every generated scenario is listed — no hidden test cases.</p>
        <div className="ml-auto flex flex-wrap gap-1.5">
          {(["pass", "partial", "fail", "error"] as const).map((s) => (
            counts[s] > 0 && <Badge key={s} className={cn(STATUS_COLOR[s], "text-[10px]")}>{counts[s]} {s}</Badge>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        <Input placeholder="Search scenarios…" value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-36"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pass">Pass</SelectItem>
            <SelectItem value="fail">Fail</SelectItem>
            <SelectItem value="partial">Partial</SelectItem>
            <SelectItem value="error">Error</SelectItem>
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((c) => <SelectItem key={c} value={c}>{c.replace(/_/g, " ")}</SelectItem>)}
          </SelectContent>
        </Select>
        {sources.length > 0 && (
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Generated by" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {sources.map((s) => <SelectItem key={s} value={s}>{sourceLabel(s)}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <span className="self-center text-xs text-muted-foreground">{rows.length} / {scenarios.length} scenarios</span>
      </div>
      <div className="max-h-[600px] overflow-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-muted/60">
            <tr>
              {["", "ID", "Scenario", "Category", "Source", "Status", "Runtime (ms)", "Business Explanation"].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ scenario, execution }) => {
              const isOpen = expanded.has(scenario.id);
              const sourceTags = scenario.traceability?.generated_by ?? [];
              const reqIds = scenario.traceability?.requirement_ids ?? [];
              return (
                <Fragment key={scenario.id}>
                  <tr
                    onClick={() => toggle(scenario.id)}
                    className="cursor-pointer border-t border-border hover:bg-accent/40"
                  >
                    <td className="px-2 py-2">
                      <span className={cn("inline-block h-2 w-2 rounded-full", SEVERITY_DOT[scenario.severity_if_failed])}
                            title={`${scenario.severity_if_failed} severity if failed`} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{scenario.id}</td>
                    <td className="px-3 py-2">{scenario.name}</td>
                    <td className="px-3 py-2 text-muted-foreground">{sourceLabel(scenario.category)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {sourceTags.length > 0 ? sourceTags.map((t) => (
                          <span key={t} className="rounded border border-border bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground">
                            {sourceLabel(t)}
                          </span>
                        )) : <span className="text-xs text-muted-foreground">—</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {execution ? <Badge className={cn(STATUS_COLOR[execution.status])}>{execution.status.toUpperCase()}</Badge> : "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{execution ? execution.runtime_ms.toFixed(0) : "—"}</td>
                    <td className="max-w-md truncate px-3 py-2 text-muted-foreground">{execution?.business_explanation ?? "—"}</td>
                  </tr>
                  {isOpen && (
                    <tr className="border-t border-border bg-muted/20">
                      <td colSpan={8} className="space-y-1.5 px-4 py-3 text-xs">
                        <p><span className="font-medium">Business objective:</span> <span className="text-muted-foreground">{scenario.business_objective}</span></p>
                        <p><span className="font-medium">Expected behaviour:</span> <span className="text-muted-foreground">{scenario.expected_behaviour}</span></p>
                        <p><span className="font-medium">Full explanation:</span> <span className="text-muted-foreground">{execution?.business_explanation ?? "Not executed."}</span></p>
                        {reqIds.length > 0 && (
                          <p><span className="font-medium">Traced ASD requirements:</span> <span className="text-muted-foreground">{reqIds.join(", ")}</span></p>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DecisionTraceTab({ scenarioById, decisionTraces, executions }: {
  scenarioById: Map<string, ScenarioRecord>;
  decisionTraces: Record<string, { step: string; value: unknown }[]>;
  executions: ScenarioExecutionRecord[];
}) {
  const ids = Object.keys(decisionTraces);
  const [selected, setSelected] = useState(ids[0] ?? "");
  const [search, setSearch] = useState("");
  const execByScenario = new Map(executions.map((e) => [e.scenario_id, e]));

  if (ids.length === 0) {
    return <p className="text-sm text-muted-foreground">No decision traces were captured for this run.</p>;
  }

  const filteredIds = ids.filter((id) => {
    if (search === "") return true;
    const q = search.toLowerCase();
    return id.toLowerCase().includes(q) || (scenarioById.get(id)?.name ?? "").toLowerCase().includes(q);
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <div className="space-y-2">
        <Input placeholder="Search scenarios…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="max-h-[560px] space-y-1 overflow-auto rounded-lg border border-border p-1.5">
          {filteredIds.map((id) => {
            const exec = execByScenario.get(id);
            return (
              <button
                key={id}
                type="button"
                onClick={() => setSelected(id)}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-xs transition-colors hover:bg-accent",
                  selected === id && "bg-accent"
                )}
              >
                <span className="truncate">
                  <span className="font-mono text-muted-foreground">{id}</span>{" "}
                  <span className="font-medium">{scenarioById.get(id)?.name ?? ""}</span>
                </span>
                {exec && <Badge className={cn(STATUS_COLOR[exec.status], "shrink-0 text-[10px]")}>{exec.status}</Badge>}
              </button>
            );
          })}
        </div>
      </div>
      <div className="space-y-4">
        <DecisionTraceSummary steps={decisionTraces[selected] ?? []} />
        <DecisionTraceFlow steps={decisionTraces[selected] ?? []} />
      </div>
    </div>
  );
}

function TrustRadar({ trustScores, overall, readiness }: {
  trustScores: TrustScoreRecord[];
  overall: number | null; readiness: string | null;
}) {
  const computed = trustScores.filter((t) => t.state === "computed");
  const data = computed.map((t) => ({ dimension: t.dimension.replace(/_/g, " "), value: Math.round((t.score / t.max_score) * 100) }));
  return (
    <div className="space-y-6">
      <p className="text-lg font-semibold">
        Overall Trust Score: {overall ?? "—"}{overall !== null ? " / 100" : ""} — {readiness ?? "—"}
      </p>
      {data.length > 0 ? (
        <div className="h-96 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data}>
              <PolarGrid stroke="var(--color-border)" />
              <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }} />
              <Radar dataKey="value" stroke="var(--color-primary)" fill="var(--color-primary)" fillOpacity={0.35} isAnimationActive />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No dimensions were computable for this run.</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {trustScores.map((t) => (
          <Card key={t.dimension} className={cn(t.state === "unknown" && "border-dashed opacity-70")}>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <span className="font-medium capitalize">{t.dimension.replace(/_/g, " ")}</span>
                {t.state === "unknown" ? (
                  <Badge variant="secondary" className="text-xs">Not Computable</Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{t.score}/{t.max_score}</span>
                )}
              </div>
              <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">{t.category.replace(/_/g, " ")}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t.state === "unknown" ? t.reason : t.rationale}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

const REQUIREMENT_STATUS_COLOR: Record<RequirementStatus, string> = {
  pass: "bg-success/15 text-success",
  fail: "bg-destructive/15 text-destructive",
  warning: "bg-warning/15 text-warning",
  observation: "bg-muted text-muted-foreground",
  not_tested: "bg-muted text-muted-foreground",
};

function CoverageBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{Math.round(value)}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full", value >= 70 ? "bg-success" : value >= 40 ? "bg-warning" : "bg-destructive")}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

function SpecificationTab({ asdSpec, conformance, evalgenStats, scenarios }: {
  asdSpec: AgentSpecificationRecord | null;
  conformance: ConformanceSummaryRecord | null;
  evalgenStats: EvalGenStatsRecord | null;
  scenarios: ScenarioRecord[];
}) {
  if (!asdSpec) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-6 text-sm text-muted-foreground">
          No Agent Specification Document was uploaded for this run. Re-run validation with a spec (.md, .docx, .pdf,
          .yaml, or .json) to enable requirement traceability and specification conformance scoring.
        </CardContent>
      </Card>
    );
  }

  const scenarioById = new Map(scenarios.map((s) => [s.id, s]));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Agent Specification</CardTitle></CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
          <p><span className="font-medium">Source:</span> {asdSpec.source_name} ({asdSpec.format})</p>
          <p><span className="font-medium">Agent Name:</span> {asdSpec.agent_name ?? "Not specified"}</p>
          <p><span className="font-medium">SCM Domain:</span> {asdSpec.scm_domain ?? "Not specified"}</p>
          <p><span className="font-medium">Business Objective:</span> {asdSpec.business_objective ?? "Not specified"}</p>
          <p><span className="font-medium">Inputs:</span> {asdSpec.inputs.join(", ") || "Not specified"}</p>
          <p><span className="font-medium">Outputs:</span> {asdSpec.outputs.join(", ") || "Not specified"}</p>
          <p><span className="font-medium">Integrations:</span> {asdSpec.integrations.join(", ") || "Not specified"}</p>
          <p><span className="font-medium">KPIs:</span> {asdSpec.kpis.join(", ") || "Not specified"}</p>
        </CardContent>
      </Card>

      {conformance && (
        <Card>
          <CardHeader>
            <CardTitle>
              Specification Conformance{conformance.conformance_score !== null ? ` — ${conformance.conformance_score}/100` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <CoverageBar label="Requirement Coverage" value={conformance.requirement_coverage} />
            <CoverageBar label="Functional Coverage" value={conformance.functional_coverage} />
            <CoverageBar label="Input Coverage" value={conformance.input_coverage} />
            <CoverageBar label="Output Coverage" value={conformance.output_coverage} />
            <CoverageBar label="Constraint Coverage" value={conformance.constraint_coverage} />
            <CoverageBar label="Integration Coverage" value={conformance.integration_coverage} />
            <CoverageBar label="KPI Coverage" value={conformance.kpi_coverage} />
            <CoverageBar label="Decision Coverage" value={conformance.decision_coverage} />
          </CardContent>
        </Card>
      )}

      {evalgenStats && (
        <Card>
          <CardHeader><CardTitle>Pairwise Testing Coverage</CardTitle></CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <p><span className="font-medium">Business Variables:</span> {evalgenStats.parameters.join(", ") || "None"}</p>
            <p><span className="font-medium">Total Candidate Scenarios:</span> {evalgenStats.total_candidate_scenarios}</p>
            <p><span className="font-medium">Optimized Scenario Count:</span> {evalgenStats.optimized_scenario_count}</p>
            <p><span className="font-medium">Redundant Scenario Reduction:</span> {Math.round(evalgenStats.redundant_scenario_reduction)}%</p>
            <p><span className="font-medium">Pairwise Coverage:</span> {Math.round(evalgenStats.pairwise_coverage)}%</p>
            <p><span className="font-medium">Interaction Coverage:</span> {Math.round(evalgenStats.interaction_coverage)}%</p>
          </CardContent>
        </Card>
      )}

      {conformance && conformance.requirements.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Requirement Traceability Matrix</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[500px] overflow-auto rounded-b-lg border-t border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted/60">
                  <tr>
                    {["Req. ID", "Status", "Rationale", "Scenarios", "Evidence"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {conformance.requirements.map((rc) => (
                    <tr key={rc.requirement_id} className="border-t border-border">
                      <td className="px-3 py-2 font-mono text-xs">{rc.requirement_id}</td>
                      <td className="px-3 py-2"><Badge className={cn(REQUIREMENT_STATUS_COLOR[rc.status])}>{rc.status.toUpperCase()}</Badge></td>
                      <td className="max-w-md px-3 py-2 text-muted-foreground">{rc.rationale}</td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {rc.scenario_refs.slice(0, 6).map((sid) => scenarioById.get(sid)?.id ?? sid).join(", ")}
                        {rc.scenario_refs.length > 6 ? ` +${rc.scenario_refs.length - 6} more` : ""}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{rc.evidence_refs.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function HistoryDelta({ delta }: { delta: import("../../../../lib/types").HistoricalDelta | null }) {
  if (!delta) return <p className="text-sm text-muted-foreground">This is the first recorded run for this agent.</p>;
  return (
    <Card>
      <CardContent className="space-y-2 pt-6 text-sm">
        <p><span className="font-medium">Previous run:</span> {delta.previous_run_id}</p>
        <p><span className="font-medium">Score delta:</span> {delta.score_delta}</p>
        <p><span className="font-medium">New defect types:</span> {delta.new_defects.join(", ") || "None"}</p>
        <p><span className="font-medium">Resolved defect types:</span> {delta.resolved_defects.join(", ") || "None"}</p>
      </CardContent>
    </Card>
  );
}
