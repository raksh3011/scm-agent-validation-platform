"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Node, Edge, Position } from "reactflow";
import "reactflow/dist/style.css";
import {
  ClipboardList, Calculator, Bot, FileCheck, Gauge, GitCompareArrows,
} from "lucide-react";
import { DecisionTraceStep } from "../lib/types";

type StepGroup = "context" | "reference" | "agent" | "evidence" | "result";

const STEP_GROUP: Record<string, StepGroup> = {
  repository_policy: "context",
  supported_capabilities: "context",
  inventory_position: "reference",
  avg_daily_demand: "reference",
  safety_stock: "reference",
  reorder_point: "reference",
  expected_decision: "reference",
  reference_order_quantity: "reference",
  supplier_considered: "reference",
  agent_decision: "agent",
  agent_quantity: "agent",
  evidence_basis: "evidence",
  confidence: "result",
  validation_result: "result",
};

const GROUP_STYLE: Record<StepGroup, { icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; border: string; bg: string }> = {
  context: { icon: ClipboardList, border: "var(--color-muted-foreground)", bg: "var(--color-muted)" },
  reference: { icon: Calculator, border: "var(--color-primary)", bg: "var(--color-card)" },
  agent: { icon: Bot, border: "var(--color-accent-foreground)", bg: "var(--color-accent)" },
  evidence: { icon: FileCheck, border: "var(--color-warning)", bg: "var(--color-card)" },
  result: { icon: Gauge, border: "var(--color-success)", bg: "var(--color-card)" },
};

function formatValue(step: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if (step === "confidence" && typeof value === "number") return `${Math.round(value * 100)}%`;
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export default function DecisionTraceFlow({ steps }: { steps: DecisionTraceStep[] }) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = steps.map((s, i) => {
      const group = STEP_GROUP[s.step] ?? "context";
      const style = GROUP_STYLE[group];
      const Icon = style.icon;
      const isResultStep = s.step === "validation_result";
      const resultTone = isResultStep
        ? String(s.value) === "pass" ? "var(--color-success)" : String(s.value) === "fail" ? "var(--color-destructive)" : "var(--color-warning)"
        : style.border;

      return {
        id: String(i),
        position: { x: 0, y: i * 92 },
        data: {
          label: (
            <div className="flex items-start gap-2 px-1">
              <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: resultTone }} />
              <div className="flex flex-col gap-0.5 overflow-hidden">
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {s.step.replace(/_/g, " ")}
                </span>
                <span className="truncate text-sm font-semibold" title={formatValue(s.step, s.value)}>
                  {formatValue(s.step, s.value)}
                </span>
              </div>
            </div>
          ),
        },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        style: {
          background: style.bg,
          border: `1.5px solid ${resultTone}`,
          borderRadius: 10,
          width: 240,
          padding: 8,
        },
      };
    });
    const edges: Edge[] = steps.slice(1).map((_, i) => ({
      id: `e${i}`,
      source: String(i),
      target: String(i + 1),
      animated: true,
      style: { stroke: "var(--color-primary)" },
    }));
    return { nodes, edges };
  }, [steps]);

  if (steps.length === 0) {
    return <p className="text-sm text-muted-foreground">No decision trace available for this scenario.</p>;
  }

  return (
    <div style={{ height: Math.max(320, steps.length * 92 + 40) }} className="rounded-lg border border-border">
      <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }}>
        <Background gap={16} size={1} />
      </ReactFlow>
    </div>
  );
}

export function DecisionTraceSummary({ steps }: { steps: DecisionTraceStep[] }) {
  const byStep = Object.fromEntries(steps.map((s) => [s.step, s.value]));
  const expected = byStep.expected_decision;
  const actual = byStep.agent_decision;
  const result = byStep.validation_result;
  const confidence = byStep.confidence;
  if (expected === undefined && actual === undefined) return null;

  const match = expected !== undefined && actual !== undefined && expected === actual;
  const resultTone = result === "pass" ? "text-success" : result === "fail" ? "text-destructive" : "text-warning";

  return (
    <div className="grid gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-4">
      <div>
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Expected</p>
        <p className="text-lg font-semibold capitalize">{formatValue("expected_decision", expected)}</p>
      </div>
      <div className="flex items-center gap-2">
        <GitCompareArrows className={match ? "h-4 w-4 text-success" : "h-4 w-4 text-destructive"} />
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Agent decided</p>
          <p className="text-lg font-semibold capitalize">{formatValue("agent_decision", actual)}</p>
        </div>
      </div>
      <div>
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Confidence</p>
        <div className="mt-1.5 flex items-center gap-2">
          <div className="h-2 w-20 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(Number(confidence ?? 0) * 100)}%` }} />
          </div>
          <span className="text-xs font-medium tabular-nums">{formatValue("confidence", confidence)}</span>
        </div>
      </div>
      <div>
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Validation result</p>
        <p className={`text-lg font-semibold uppercase ${resultTone}`}>{String(result ?? "—")}</p>
      </div>
    </div>
  );
}
