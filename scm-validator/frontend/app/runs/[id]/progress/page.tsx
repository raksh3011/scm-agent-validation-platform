"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";
import { useRunStatus } from "../../../../lib/queries";
import { cn } from "../../../../lib/utils";

const STAGES = [
  "repository_analysis", "dependency_resolution", "runtime_environment_build",
  "agent_initialization", "entry_point_discovery", "sandbox_validation",
  "business_scenario_execution", "business_decision_validation", "trust_score_calculation",
];

export default function ProgressPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error } = useRunStatus(params.id);
  const status = data?.status ?? "queued";
  const progress = data?.progress ?? null;

  useEffect(() => {
    if (status === "completed") router.push(`/runs/${params.id}/results`);
  }, [status, params.id, router]);

  const failed = status === "failed";
  const stagesDone = progress?.stages_done ?? 0;
  const currentStage = progress?.current_stage;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mx-auto max-w-xl">
      <h1 className="text-2xl font-semibold tracking-tight">Running Validation</h1>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Run {params.id}</CardTitle>
        </CardHeader>
        <CardContent>
          {failed || error ? (
            <div className="flex items-start gap-2 text-destructive">
              <XCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="font-medium">Validation failed</p>
                <p className="text-sm text-muted-foreground">{data?.error || (error instanceof Error ? error.message : "")}</p>
              </div>
            </div>
          ) : status === "queued" && !currentStage ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Queued — waiting to start…</span>
            </div>
          ) : (
            <>
              <ol className="space-y-3">
                {STAGES.map((stage, i) => {
                  const done = i < stagesDone;
                  const active = stage === currentStage;
                  return (
                    <li key={stage} className="flex items-start gap-3">
                      {done ? (
                        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
                      ) : active ? (
                        <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-primary" />
                      ) : (
                        <span className="mt-0.5 h-5 w-5 shrink-0 rounded-full border-2 border-border" />
                      )}
                      <span className={cn("text-sm", active ? "font-medium text-foreground" : done ? "text-foreground" : "text-muted-foreground")}>
                        {stage.replace(/_/g, " ")}
                        {active && stage === "business_scenario_execution" && progress?.scenarios_total
                          ? ` — ${progress.scenarios_done ?? 0}/${progress.scenarios_total} scenarios`
                          : ""}
                      </span>
                    </li>
                  );
                })}
              </ol>
              {currentStage === "business_scenario_execution" && progress?.scenarios_total ? (
                <p className="mt-4 text-xs text-muted-foreground">
                  Each scenario runs in its own sandboxed subprocess — this stage is the slowest part of a run,
                  especially on Windows. It is actively progressing, not stuck.
                </p>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
