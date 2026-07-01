"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CapabilityGraphRecord } from "../lib/types";
import { cn } from "../lib/utils";

const WIDTH = 640;
const HEIGHT = 420;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };
const RADIUS = 150;

function confidenceColor(confidence: number): string {
  if (confidence >= 0.75) return "var(--color-success)";
  if (confidence >= 0.5) return "var(--color-warning)";
  return "var(--color-destructive)";
}

export default function CapabilityGraph({ graph }: { graph: CapabilityGraphRecord | null }) {
  const [hovered, setHovered] = useState<string | null>(null);

  const nodes = useMemo(() => {
    const caps = graph?.supported_capabilities ?? [];
    return caps.map((c, i) => {
      const angle = (i / Math.max(1, caps.length)) * 2 * Math.PI - Math.PI / 2;
      return {
        ...c,
        x: CENTER.x + RADIUS * Math.cos(angle),
        y: CENTER.y + RADIUS * Math.sin(angle),
      };
    });
  }, [graph]);

  if (!graph) {
    return (
      <p className="text-sm text-muted-foreground">
        No business capability graph was captured for this run — this run did not reach repository understanding.
      </p>
    );
  }

  const active = hovered ? nodes.find((n) => n.name === hovered) : null;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full">
          {nodes.map((n) => (
            <motion.line
              key={`edge-${n.name}`}
              x1={CENTER.x} y1={CENTER.y} x2={n.x} y2={n.y}
              stroke={hovered === n.name ? confidenceColor(n.confidence) : "var(--color-border)"}
              strokeWidth={hovered === n.name ? 2 : 1}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.5 }}
            />
          ))}

          <motion.circle
            cx={CENTER.x} cy={CENTER.y} r={42}
            fill="var(--color-primary)"
            initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.3 }}
          />
          <text x={CENTER.x} y={CENTER.y - 4} textAnchor="middle" className="fill-primary-foreground text-[11px] font-semibold">
            Agent
          </text>
          <text x={CENTER.x} y={CENTER.y + 10} textAnchor="middle" className="fill-primary-foreground text-[8px]">
            {graph.primary_policy.replace(/_/g, " ").slice(0, 16)}
          </text>

          {nodes.map((n, i) => (
            <motion.g
              key={n.name}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, delay: 0.1 + i * 0.04 }}
              onMouseEnter={() => setHovered(n.name)}
              onMouseLeave={() => setHovered(null)}
              className="cursor-pointer"
            >
              <circle cx={n.x} cy={n.y} r={hovered === n.name ? 30 : 26} fill={confidenceColor(n.confidence)} fillOpacity={0.85} />
              <text x={n.x} y={n.y - 2} textAnchor="middle" className="fill-white text-[9px] font-medium" style={{ pointerEvents: "none" }}>
                {n.name.replace(/_/g, " ").slice(0, 14)}
              </text>
              <text x={n.x} y={n.y + 10} textAnchor="middle" className="fill-white text-[8px]" style={{ pointerEvents: "none" }}>
                {Math.round(n.confidence * 100)}%
              </text>
            </motion.g>
          ))}
        </svg>
      </div>

      <div className="space-y-3 text-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Business Objective</p>
          <p className="mt-1">{graph.business_objective || "Not detected"}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {active ? `Capability: ${active.name.replace(/_/g, " ")}` : "Hover a node"}
          </p>
          {active ? (
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
              {active.evidence.slice(0, 6).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">
              {graph.decision_variables.length} decision variable(s), {graph.business_entities.length} business entit(y/ies) detected.
            </p>
          )}
        </div>
        {graph.unsupported_capabilities.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Not Implemented</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {graph.unsupported_capabilities.slice(0, 8).map((c) => (
                <span key={c} className={cn("rounded border border-dashed border-border px-1.5 py-0.5 text-[10px] text-muted-foreground")}>
                  {c.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
