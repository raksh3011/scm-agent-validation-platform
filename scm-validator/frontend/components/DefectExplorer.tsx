"use client";

import { useMemo, useState } from "react";
import { ChevronDown, FileCode2, Search } from "lucide-react";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { DefectRecord, Severity } from "../lib/types";
import { cn } from "../lib/utils";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];
const SEVERITY_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "bg-destructive text-destructive-foreground",
  high: "bg-orange-500 text-white",
  medium: "bg-warning text-foreground",
  low: "bg-muted text-muted-foreground",
};

export default function DefectExplorer({ defects }: { defects: DefectRecord[] }) {
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const categories = useMemo(() => Array.from(new Set(defects.map((d) => d.category))).sort(), [defects]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return defects
      .filter((d) =>
        (severityFilter === "all" || d.severity === severityFilter) &&
        (categoryFilter === "all" || d.category === categoryFilter) &&
        (q === "" ||
          d.title.toLowerCase().includes(q) ||
          d.defect_type.toLowerCase().includes(q) ||
          (d.file_path ?? "").toLowerCase().includes(q) ||
          (d.function_name ?? "").toLowerCase().includes(q))
      )
      .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  }, [defects, search, severityFilter, categoryFilter]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  if (defects.length === 0) {
    return <p className="text-sm text-muted-foreground">No defects were identified that meet the evidence-backed reporting threshold.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input placeholder="Search title, type, file, function…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
        </div>
        <Select value={severityFilter} onValueChange={setSeverityFilter}>
          <SelectTrigger className="w-36"><SelectValue placeholder="Severity" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            {SEVERITY_ORDER.map((s) => <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((c) => <SelectItem key={c} value={c}>{c.replace(/_/g, " ")}</SelectItem>)}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">{filtered.length} / {defects.length} defects</span>
      </div>

      <div className="space-y-2">
        {filtered.map((d) => {
          const isOpen = expanded.has(d.id);
          const location = d.file_path
            ? `${d.file_path}${d.line_number ? `:${d.line_number}` : ""}${d.function_name ? ` (${d.function_name})` : ""}`
            : null;
          return (
            <div key={d.id} className="rounded-lg border border-border bg-card transition-shadow hover:shadow-sm">
              <button
                type="button"
                onClick={() => toggle(d.id)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
              >
                <Badge className={cn(SEVERITY_COLOR[d.severity], "shrink-0")}>{d.severity.toUpperCase()}</Badge>
                <span className="flex-1 truncate font-medium">{d.title}</span>
                {location && (
                  <span className="hidden shrink-0 items-center gap-1 text-xs text-muted-foreground sm:flex">
                    <FileCode2 className="h-3 w-3" /> {d.file_path}
                  </span>
                )}
                <span className="shrink-0 text-xs text-muted-foreground">{d.category}</span>
                <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
              </button>
              {isOpen && (
                <div className="space-y-2 border-t border-border px-4 py-3 text-sm">
                  <Row label="Location">
                    {location ? <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{location}</code> :
                      <span className="text-muted-foreground">Repository-wide finding — no single line of origin</span>}
                  </Row>
                  {d.violated_requirement && d.violated_requirement.length > 0 && (
                    <Row label="Violated requirement">{d.violated_requirement.join(", ")}</Row>
                  )}
                  <Row label="Business impact">{d.business_impact}</Row>
                  {d.root_cause && <Row label="Root cause">{d.root_cause}</Row>}
                  <Row label="Technical explanation">{d.technical_explanation}</Row>
                  <Row label="Recommendation">{d.recommendation}</Row>
                  <Row label="Affected scenarios">
                    {d.scenario_refs.length > 0 ? d.scenario_refs.slice(0, 10).join(", ") : "None (static finding)"}
                    {d.scenario_refs.length > 10 ? ` +${d.scenario_refs.length - 10} more` : ""}
                  </Row>
                  {d.evidence_refs.length > 0 && (
                    <Row label="Evidence">
                      <div className="flex flex-wrap gap-1.5">
                        {d.evidence_refs.slice(0, 12).map((e) => (
                          <span
                            key={e}
                            className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                          >
                            {e}
                          </span>
                        ))}
                      </div>
                    </Row>
                  )}
                  <p className="text-xs text-muted-foreground">Confidence: {Math.round(d.confidence * 100)}%</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="font-medium">{label}:</span>{" "}
      <span className="text-muted-foreground">{children}</span>
    </div>
  );
}
