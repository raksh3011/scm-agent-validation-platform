"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CapabilityGraphRecord } from "../lib/types";
import { cn } from "../lib/utils";

const WIDTH = 720;
const HEIGHT = 480;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };
const RADIUS = 175;
const NODE_R = 38;

function confidenceColor(confidence: number): string {
  if (confidence >= 0.75) return "var(--color-success)";
  if (confidence >= 0.5) return "var(--color-warning)";
  return "var(--color-destructive)";
}

/** Splits a label into up to two lines of roughly `maxChars` each on word
 * boundaries, rather than mid-word truncation that used to clip names like
 * "purchase order" or "reorder timing" down to unreadable fragments. */
function wrapLabel(label: string, maxChars: number): string[] {
  const words = label.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  if (lines.length > 2) {
    return [lines[0], `${lines[1].slice(0, Math.max(1, maxChars - 1))}…`];
  }
  return lines;
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
            cx={CENTER.x} cy={CENTER.y} r={48}
            fill="var(--color-primary)"
            initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.3 }}
          />
          <text x={CENTER.x} y={CENTER.y - 6} textAnchor="middle" className="fill-primary-foreground text-[12px] font-semibold">
            Agent
          </text>
          {wrapLabel(graph.primary_policy.replace(/_/g, " "), 14).map((line, i, arr) => (
            <text
              key={i}
              x={CENTER.x}
              y={CENTER.y + 10 + i * 11 - ((arr.length - 1) * 5.5)}
              textAnchor="middle"
              className="fill-primary-foreground text-[9px]"
              opacity={0.9}
            >
              {line}
            </text>
          ))}

          {nodes.map((n, i) => {
            const isHovered = hovered === n.name;
            const label = wrapLabel(n.name.replace(/_/g, " "), 12);
            return (
              <motion.g
                key={n.name}
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, delay: 0.1 + i * 0.04 }}
                onMouseEnter={() => setHovered(n.name)}
                onMouseLeave={() => setHovered(null)}
                className="cursor-pointer"
              >
                <circle
                  cx={n.x} cy={n.y} r={isHovered ? NODE_R + 3 : NODE_R}
                  fill={confidenceColor(n.confidence)}
                  fillOpacity={isHovered ? 1 : 0.85}
                  stroke={isHovered ? "var(--color-foreground)" : "transparent"}
                  strokeWidth={1.5}
                />
                {label.map((line, li) => (
                  <text
                    key={li}
                    x={n.x}
                    y={n.y - 5 + li * 11 - ((label.length - 1) * 5.5)}
                    textAnchor="middle"
                    className="fill-white text-[9.5px] font-medium"
                    style={{ pointerEvents: "none" }}
                  >
                    {line}
                  </text>
                ))}
                <text x={n.x} y={n.y + (label.length > 1 ? 20 : 13)} textAnchor="middle" className="fill-white text-[9px]" style={{ pointerEvents: "none" }}>
                  {Math.round(n.confidence * 100)}%
                </text>
              </motion.g>
            );
          })}
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
