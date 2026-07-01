import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  compareRuns, createRun, getRunResults, getRunStatus, getSubjectHistory, listRuns, rerunSubject,
} from "./api";

export function useRunsList() {
  return useQuery({ queryKey: ["runs"], queryFn: listRuns, refetchInterval: 10000 });
}

export function useRunStatus(runId: string, enabled = true) {
  return useQuery({
    queryKey: ["run-status", runId],
    queryFn: () => getRunStatus(runId),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1200;
    },
  });
}

export function useRunResults(runId: string) {
  return useQuery({ queryKey: ["run-results", runId], queryFn: () => getRunResults(runId) });
}

export function useSubjectHistory(subjectId: string) {
  return useQuery({ queryKey: ["subject-history", subjectId], queryFn: () => getSubjectHistory(subjectId) });
}

export function useCompareRuns(runIdA: string | null, runIdB: string | null) {
  return useQuery({
    queryKey: ["compare-runs", runIdA, runIdB],
    queryFn: () => compareRuns(runIdA as string, runIdB as string),
    enabled: Boolean(runIdA && runIdB),
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => createRun(form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
}

export function useRerunSubject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (subjectId: string) => rerunSubject(subjectId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
}
