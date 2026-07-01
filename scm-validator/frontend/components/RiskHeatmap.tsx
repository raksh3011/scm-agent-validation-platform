"use client";

import { motion } from "framer-motion";
import { DefectRecord, Severity } from "../lib/types";
import { cn } from "../lib/utils";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];
const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-destructive/20 text-destructive border-destructive/40",
  high: "bg-orange-500/15 text-orange-600 border-orange-500/30 dark:text-orange-400",
  medium: "bg-warning/15 text-warning border-warning/30",
  low: "bg-muted text-muted-foreground border-border",
};

export default function RiskHeatmap({ defects }: { defects: DefectRecord[] }) {
  if (defects.length === 0) {
    return <p className="text-sm text-muted-foreground">No defects to plot on the risk matrix.</p>;
  }
  const categories = Array.from(new Set(defects.map((d) => d.category))).sort();
  const grid: Record<string, Record<Severity, number>> = {};
  for (const d of defects) {
    grid[d.category] ??= { critical: 0, high: 0, medium: 0, low: 0 };
    grid[d.category][d.severity] += 1;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Category</th>
            {SEVERITY_ORDER.map((s) => (
              <th key={s} className="px-3 py-2 text-center font-medium text-muted-foreground">{s.toUpperCase()}</th>
            ))}
            <th className="px-3 py-2 text-center font-medium text-muted-foreground">Total</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((cat, i) => {
            const row = grid[cat];
            const total = SEVERITY_ORDER.reduce((sum, s) => sum + row[s], 0);
            return (
              <tr key={cat} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-medium capitalize">{cat.replace(/_/g, " ")}</td>
                {SEVERITY_ORDER.map((s) => {
                  const count = row[s];
                  return (
                    <td key={s} className="px-2 py-2 text-center">
                      {count > 0 ? (
                        <motion.span
                          initial={{ scale: 0.6, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ duration: 0.25, delay: i * 0.03 }}
                          className={cn(
                            "inline-flex h-7 min-w-7 items-center justify-center rounded-md border px-1.5 text-xs font-semibold tabular-nums",
                            SEVERITY_BG[s]
                          )}
                        >
                          {count}
                        </motion.span>
                      ) : (
                        <span className="text-xs text-muted-foreground/40">—</span>
                      )}
                    </td>
                  );
                })}
                <td className="px-3 py-2 text-center text-xs font-semibold tabular-nums text-muted-foreground">{total}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
