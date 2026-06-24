"""Pydantic models = single source of truth shared by DB persistence, API responses, and frontend contract."""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel

Severity = Literal["Critical", "High", "Medium", "Low"]
DemoReadiness = Literal["Demo Ready", "Conditionally Ready", "Not Ready"]
ProductionReadiness = Literal["Production Ready", "Requires Hardening", "Not Ready"]
RunStatus = Literal["queued", "running", "completed", "failed"]
Priority = Literal["Immediate", "High", "Medium", "Low"]

DIMENSIONS = [
    "Specification Completeness",
    "Reliability & Error Handling",
    "AI/LLM Risk Controls",
    "SCM Logic Quality",
    "Observability / Traceability",
    "Demo Readiness",
    "Production Readiness",
]


class ScoreBreakdownItem(BaseModel):
    dimension: str
    score: float
    max_score: float
    remarks: str


class Finding(BaseModel):
    id: str
    severity: Severity
    category: str
    title: str
    description: str
    why_it_matters: str
    score_impact: float
    evidence_refs: list[str] = []


class Recommendation(BaseModel):
    id: str
    finding_id: str
    title: str
    recommendation: str
    priority: Priority
    expected_impact: str


class Evidence(BaseModel):
    id: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
    reason: str = ""


class InvariantResult(BaseModel):
    """One execution-based behavioral check (Phase 3 of the Trust Harness)."""
    test_id: str
    tier: Literal["required", "recommended"] = "required"
    passed: bool
    detail: str = ""


class ScenarioResult(BaseModel):
    """One golden-scenario grading (Phase 4 of the Trust Harness)."""
    scenario_id: str
    tier: Literal["required", "recommended"] = "required"
    passed: bool
    description: str = ""
    expected: dict = {}
    actual: dict = {}
    detail: str = ""


class Summary(BaseModel):
    agent_name: str
    run_id: str
    timestamp: str
    applicable: bool = True
    not_applicable_reason: str | None = None
    overall_trust_score: float | None = None
    hygiene_score: float | None = None       # static-rule "secondary" signal (0-100)
    behavior_score: float | None = None       # execution-based signal (0-100); dominant input
    demo_readiness: DemoReadiness | None = None
    production_readiness: ProductionReadiness | None = None
    status: RunStatus


class ValidationResult(BaseModel):
    summary: Summary
    score_breakdown: list[ScoreBreakdownItem] = []
    positive_signals: list[str] = []
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    evidence: list[Evidence] = []
    ai_insights: list[str] = []
    invariant_results: list[InvariantResult] = []
    scenario_results: list[ScenarioResult] = []
    adapter_status: str = "not_attempted"   # not_attempted | loaded | auto_generated | failed


class CreateRunRequest(BaseModel):
    agent_name: str
    repo_url: Optional[str] = None
    use_case: Optional[str] = None
    expected_io: Optional[str] = None
    description: Optional[str] = None
    enable_llm_insights: bool = False
