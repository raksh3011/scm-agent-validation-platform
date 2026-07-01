"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, CircleDashed, MinusCircle } from "lucide-react";
import { Card, CardContent } from "./ui/card";
import { PipelineStageRecord } from "../lib/types";
import { cn } from "../lib/utils";

const ICON: Record<string, typeof CheckCircle2> = {
  ok: CheckCircle2,
  failed: AlertTriangle,
  skipped: MinusCircle,
  partial: CircleDashed,
};

const COLOR: Record<string, string> = {
  ok: "text-success",
  failed: "text-destructive",
  skipped: "text-muted-foreground",
  partial: "text-warning",
};

export default function PipelineStages({ stages }: { stages: PipelineStageRecord[] }) {
  if (stages.length === 0) {
    return <p className="text-sm text-muted-foreground">No staged pipeline data was recorded for this run.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Shows exactly which stage validation stopped at, if any — business metrics are never scored from a
        stage that never ran.
      </p>
      <div className="relative space-y-2 pl-2">
        {stages.map((s, i) => {
          const Icon = ICON[s.status] ?? CircleDashed;
          return (
            <motion.div
              key={s.stage}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: i * 0.04 }}
            >
              <Card className={cn(s.status === "failed" && "border-destructive/40")}>
                <CardContent className="flex items-start gap-3 py-3">
                  <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", COLOR[s.status])} />
                  <div className="flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{s.stage.replace(/_/g, " ")}</span>
                      <span className={cn("text-xs font-semibold uppercase tracking-wide", COLOR[s.status])}>
                        {s.status}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{s.detail}</p>
                    {s.recovery_suggestions.length > 0 && (
                      <ul className="mt-2 space-y-1 border-l-2 border-warning/50 pl-3 text-xs text-muted-foreground">
                        {s.recovery_suggestions.map((r, idx) => <li key={idx}>{r}</li>)}
                      </ul>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
