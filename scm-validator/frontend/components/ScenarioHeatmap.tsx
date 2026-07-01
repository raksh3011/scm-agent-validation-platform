"use client";

import { motion } from "framer-motion";
import { ScenarioStatus } from "../lib/types";
import { cn } from "../lib/utils";

const STATUS_ORDER: ScenarioStatus[] = ["pass", "partial", "fail", "error", "not_executed"];
const STATUS_BG: Record<ScenarioStatus, string> = {
  pass: "bg-success/15 text-success border-success/30",
  partial: "bg-warning/15 text-warning border-warning/30",
  fail: "bg-destructive/15 text-destructive border-destructive/30",
  error: "bg-muted text-muted-foreground border-border",
  not_executed: "bg-muted text-muted-foreground border-dashed border-border",
};

export interface HeatmapCell {
  category: string;
  status: ScenarioStatus;
}

export default function ScenarioHeatmap({ cells }: { cells: HeatmapCell[] }) {
  const categories = Array.from(new Set(cells.map((c) => c.category)));
  const grid: Record<string, Record<ScenarioStatus, number>> = {};
  for (const c of cells) {
    grid[c.category] ??= { pass: 0, partial: 0, fail: 0, error: 0, not_executed: 0 };
    grid[c.category][c.status] += 1;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Category</th>
            {STATUS_ORDER.map((s) => (
              <th key={s} className="px-3 py-2 text-center font-medium text-muted-foreground">
                {s.toUpperCase()}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((cat, i) => (
            <tr key={cat} className="border-b border-border last:border-0">
              <td className="px-3 py-2 font-medium">{cat === "evalgen_pairwise" ? "pairwise testing" : cat.replace(/_/g, " ")}</td>
              {STATUS_ORDER.map((s) => {
                const count = grid[cat]?.[s] ?? 0;
                return (
                  <td key={s} className="px-2 py-2 text-center">
                    {count > 0 ? (
                      <motion.span
                        initial={{ scale: 0.6, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ duration: 0.25, delay: i * 0.02 }}
                        className={cn("inline-flex h-7 min-w-7 items-center justify-center rounded-md border px-1.5 text-xs font-semibold tabular-nums", STATUS_BG[s])}
                      >
                        {count}
                      </motion.span>
                    ) : (
                      <span className="text-xs text-muted-foreground/40">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
