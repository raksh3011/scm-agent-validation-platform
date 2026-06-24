export type Severity = "Critical" | "High" | "Medium" | "Low";
export type DemoReadiness = "Demo Ready" | "Conditionally Ready" | "Not Ready";
export type ProductionReadiness = "Production Ready" | "Requires Hardening" | "Not Ready";
export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface ScoreBreakdownItem {
  dimension: string;
  score: number;
  max_score: number;
  remarks: string;
}

export interface Finding {
  id: string;
  severity: Severity;
  category: string;
  title: string;
  description: string;
  why_it_matters: string;
  score_impact: number;
  evidence_refs: string[];
}

export interface Recommendation {
  id: string;
  finding_id: string;
  title: string;
  recommendation: string;
  priority: string;
  expected_impact: string;
}

export interface Evidence {
  id: string;
  file_path: string;
  line_start: number;
  line_end: number;
  snippet: string;
  reason: string;
}

export interface Summary {
  agent_name: string;
  run_id: string;
  timestamp: string;
  overall_trust_score: number;
  demo_readiness: DemoReadiness;
  production_readiness: ProductionReadiness;
  status: RunStatus;
}

export interface ValidationResult {
  summary: Summary;
  score_breakdown: ScoreBreakdownItem[];
  positive_signals: string[];
  findings: Finding[];
  recommendations: Recommendation[];
  evidence: Evidence[];
  ai_insights: string[];
}

export interface RunListItem {
  run_id: string;
  agent_name: string;
  source_type: string;
  status: RunStatus;
  overall_trust_score: number | null;
  demo_readiness: DemoReadiness | null;
  production_readiness: ProductionReadiness | null;
  created_at: string;
}
