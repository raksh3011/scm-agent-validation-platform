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


class Summary(BaseModel):
    agent_name: str
    run_id: str
    timestamp: str
    overall_trust_score: float
    demo_readiness: DemoReadiness
    production_readiness: ProductionReadiness
    status: RunStatus


class ValidationResult(BaseModel):
    summary: Summary
    score_breakdown: list[ScoreBreakdownItem]
    positive_signals: list[str] = []
    findings: list[Finding]
    recommendations: list[Recommendation]
    evidence: list[Evidence]
    ai_insights: list[str] = []


class CreateRunRequest(BaseModel):
    agent_name: str
    repo_url: Optional[str] = None
    use_case: Optional[str] = None
    expected_io: Optional[str] = None
    description: Optional[str] = None
    enable_llm_insights: bool = False
