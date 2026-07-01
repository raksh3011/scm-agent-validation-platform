export type RunStatus = "queued" | "running" | "completed" | "failed";
export type ReadinessLabel = "Production Ready" | "Conditional" | "Not Ready" | "Insufficient Evidence";
export type Severity = "critical" | "high" | "medium" | "low";
export type ScenarioStatus = "pass" | "fail" | "partial" | "error" | "not_executed";
export type ExecutionState = "executed" | "crashed" | "unreachable";
export type StageStatus = "ok" | "failed" | "skipped" | "partial";
export type TrustState = "computed" | "unknown";

export interface RunSummary {
  run_id: string;
  subject_id: string;
  agent_name: string;
  source_type: string;
  source_ref: string | null;
  status: RunStatus;
  error: string | null;
  applicable: number;
  not_applicable_reason: string | null;
  primary_agent_type: string | null;
  classification_confidence: number | null;
  secondary_capabilities: string | null;
  suite_hash: string | null;
  overall_trust_score: number | null;
  production_readiness: ReadinessLabel | null;
  created_at: string;
  updated_at: string;
}

export interface ScenarioRecord {
  id: string;
  name: string;
  category: string;
  business_objective: string;
  inputs: Record<string, unknown>;
  initial_state: Record<string, unknown>;
  expected_behaviour: string;
  severity_if_failed: Severity;
  traceability?: { generated_by?: string[]; requirement_ids?: string[] };
}

export interface ScenarioExecutionRecord {
  scenario_id: string;
  status: ScenarioStatus;
  execution_state: ExecutionState;
  actual_behaviour: { return_value: unknown; candidate: string | null; exception?: Record<string, unknown> | null };
  business_explanation: string;
  confidence: number;
  runtime_ms: number;
  error: string | null;
}

export interface EvidenceRecord {
  id: string;
  scenario_id: string | null;
  evidence_type: "stdout" | "db_mutation" | "file_write" | "exception" | "mock_call";
  detail: Record<string, unknown>;
}

export type DefectCategory =
  | "business" | "operational" | "technical" | "architectural" | "data_quality"
  | "security" | "integration" | "reliability" | "scalability" | "performance";

export interface DefectRecord {
  id: string;
  category: DefectCategory;
  defect_type: string;
  title: string;
  severity: Severity;
  confidence: number;
  business_impact: string;
  technical_explanation: string;
  recommendation: string;
  verification_steps: string[];
  scenario_refs: string[];
  evidence_refs: string[];
  file_path?: string | null;
  line_number?: number | null;
  function_name?: string | null;
  violated_requirement?: string[];
  root_cause?: string | null;
}

export interface TrustScoreRecord {
  dimension: string;
  category: string;
  score: number;
  max_score: number;
  rationale: string;
  state: TrustState;
  reason: string | null;
  evidence_refs: string[];
}

export interface PipelineStageRecord {
  stage: string;
  status: StageStatus;
  detail: string;
  recovery_suggestions: string[];
  duration_ms: number;
  stage_order: number;
}

export interface RootCauseRecord {
  id: string;
  exception_type: string;
  normalized_message: string;
  confidence: number;
  recovery_suggestion: string;
  affected_scenario_ids: string[];
  affected_count: number;
  representative_traceback: string;
}

export interface HistoricalDelta {
  run_id: string;
  previous_run_id: string | null;
  subject_id: string;
  score_delta: number;
  new_defects: string[];
  resolved_defects: string[];
  regressions: string[];
}

export interface KpiRecord {
  run_id: string;
  name: string;
  value: number;
  unit: string;
  description: string;
}

export interface DecisionTraceStep {
  step: string;
  value: unknown;
}

export interface AgentSpecificationRecord {
  source_name: string;
  format: string;
  agent_name: string | null;
  scm_domain: string | null;
  business_objective: string | null;
  scope: string[];
  out_of_scope: string[];
  stakeholders: string[];
  responsibilities: string[];
  workflows: string[];
  decision_policies: string[];
  inputs: string[];
  outputs: string[];
  integrations: string[];
  constraints: string[];
  kpis: string[];
  requirements: { id: string; category: string; text: string; required: boolean; keywords: string[] }[];
}

export type RequirementStatus = "pass" | "fail" | "warning" | "observation" | "not_tested";

export interface RequirementConformanceRecord {
  requirement_id: string;
  status: RequirementStatus;
  confidence: number;
  rationale: string;
  repository_evidence: string[];
  scenario_refs: string[];
  evidence_refs: string[];
}

export interface ConformanceSummaryRecord {
  conformance_score: number | null;
  requirement_coverage: number;
  functional_coverage: number;
  input_coverage: number;
  output_coverage: number;
  constraint_coverage: number;
  integration_coverage: number;
  kpi_coverage: number;
  decision_coverage: number;
  requirements: RequirementConformanceRecord[];
}

export interface EvalGenStatsRecord {
  pairwise_coverage: number;
  parameter_coverage: number;
  interaction_coverage: number;
  constraint_coverage: number;
  redundant_scenario_reduction: number;
  total_candidate_scenarios: number;
  optimized_scenario_count: number;
  parameters: string[];
}

export interface CapabilityRecord {
  name: string;
  confidence: number;
  evidence: string[];
}

export interface CapabilityGraphRecord {
  business_objective: string;
  primary_policy: string;
  policy_confidence: number;
  supported_capabilities: CapabilityRecord[];
  decision_variables: string[];
  business_entities: string[];
  thresholds: Record<string, unknown>;
  optimization_objectives: string[];
  assumptions: string[];
  unsupported_capabilities: string[];
  evidence_summary: string[];
}

export interface RunResults {
  summary: RunSummary;
  applicable: boolean;
  scenarios?: ScenarioRecord[];
  executions?: ScenarioExecutionRecord[];
  evidence?: EvidenceRecord[];
  defects?: DefectRecord[];
  trust_scores?: TrustScoreRecord[];
  historical_delta?: HistoricalDelta | null;
  kpis?: KpiRecord[];
  decision_traces?: Record<string, DecisionTraceStep[]>;
  stages?: PipelineStageRecord[];
  root_causes?: RootCauseRecord[];
  asd_spec?: AgentSpecificationRecord | null;
  conformance?: ConformanceSummaryRecord | null;
  evalgen_stats?: EvalGenStatsRecord | null;
  capability_graph?: CapabilityGraphRecord | null;
}

export interface RunListItem {
  run_id: string;
  subject_id: string;
  agent_name: string;
  source_type: string;
  status: RunStatus;
  applicable: number;
  not_applicable_reason: string | null;
  primary_agent_type: string | null;
  overall_trust_score: number | null;
  production_readiness: ReadinessLabel | null;
  created_at: string;
}

export interface RunSnapshotRecord {
  run_id: string;
  agent_name: string;
  primary_agent_type: string | null;
  overall_trust_score: number | null;
  production_readiness: ReadinessLabel | null;
  created_at: string;
}

export type DefectDeltaStatus = "new" | "resolved" | "persisting";

export interface DefectDeltaRecord {
  defect_type: string;
  category: string;
  title: string;
  status: DefectDeltaStatus;
  severity_before: Severity | null;
  severity_after: Severity | null;
  severity_change: "worse" | "better" | "unchanged" | null;
}

export interface TrustDimensionDeltaRecord {
  dimension: string;
  category: string;
  score_before: number | null;
  score_after: number | null;
  max_score: number;
  delta: number | null;
  state_before: TrustState;
  state_after: TrustState;
}

export interface KpiDeltaRecord {
  name: string;
  value_before: number | null;
  value_after: number | null;
  delta: number | null;
  unit: string;
}

export interface ConformanceDeltaRecord {
  metric: string;
  before: number | null;
  after: number | null;
  delta: number | null;
}

export interface ScenarioFlipRecord {
  name: string;
  category: string;
  status_before: ScenarioStatus;
  status_after: ScenarioStatus;
  direction: "regression" | "improvement";
}

export type ComparisonVerdict = "improved" | "regressed" | "mixed" | "unchanged" | "not_comparable";

export interface ComparisonReport {
  run_a: RunSnapshotRecord;
  run_b: RunSnapshotRecord;
  verdict: ComparisonVerdict;
  score_delta: number | null;
  defect_deltas: DefectDeltaRecord[];
  trust_deltas: TrustDimensionDeltaRecord[];
  kpi_deltas: KpiDeltaRecord[];
  conformance_deltas: ConformanceDeltaRecord[];
  scenario_flips: ScenarioFlipRecord[];
  summary: string;
}

export interface SubjectHistory {
  subject_id: string;
  runs: {
    run_id: string;
    status: RunStatus;
    overall_trust_score: number | null;
    production_readiness: ReadinessLabel | null;
    created_at: string;
  }[];
  deltas: HistoricalDelta[];
}
