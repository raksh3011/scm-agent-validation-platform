from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceType = Literal["stdout", "db_mutation", "file_write", "exception", "mock_call"]
ExecutionStatus = Literal["pass", "fail", "partial", "error", "not_executed"]
ExecutionState = Literal["executed", "crashed", "unreachable"]
StageStatus = Literal["ok", "failed", "skipped", "partial"]
TrustState = Literal["computed", "unknown"]

PIPELINE_STAGES = (
    "repository_analysis",
    "dependency_resolution",
    "runtime_environment_build",
    "agent_initialization",
    "entry_point_discovery",
    "sandbox_validation",
    "business_scenario_execution",
    "business_decision_validation",
    "trust_score_calculation",
)


@dataclass
class Evidence:
    id: str
    evidence_type: EvidenceType
    detail: dict[str, Any]
    scenario_id: str | None = None


@dataclass
class Scenario:
    id: str
    name: str
    category: str
    business_objective: str
    inputs: dict[str, Any]
    initial_state: dict[str, Any]
    expected_behaviour: str
    severity_if_failed: str = "medium"
    traceability: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioExecutionResult:
    scenario: Scenario
    status: ExecutionStatus
    actual_behaviour: dict[str, Any]
    business_explanation: str
    confidence: float
    runtime_ms: float
    execution_state: ExecutionState = "executed"
    evidence: list[Evidence] = field(default_factory=list)
    error: str | None = None


@dataclass
class AgentClassification:
    primary_type: str
    confidence: float
    secondary_capabilities: list[str]
    signals: dict[str, Any]


@dataclass
class Defect:
    id: str
    category: Literal["business", "operational", "technical", "architectural", "data_quality",
                      "security", "integration", "reliability", "scalability", "performance"]
    defect_type: str
    title: str
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float
    business_impact: str
    technical_explanation: str
    recommendation: str
    verification_steps: list[str]
    scenario_refs: list[str]
    evidence_refs: list[str]
    file_path: str | None = None
    line_number: int | None = None
    function_name: str | None = None
    violated_requirement: list[str] = field(default_factory=list)
    root_cause: str | None = None
    governance_refs: list[str] = field(default_factory=list)


@dataclass
class TrustDimensionScore:
    dimension: str
    category: str
    score: float
    max_score: float
    rationale: str
    state: TrustState = "computed"
    reason: str | None = None
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    stage: str
    status: StageStatus
    detail: str
    recovery_suggestions: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class RootCause:
    id: str
    exception_type: str
    normalized_message: str
    confidence: float
    recovery_suggestion: str
    affected_scenario_ids: list[str]
    affected_count: int
    representative_traceback: str


@dataclass
class RuntimeEnvironment:
    workspace: Any
    language: str
    framework: str | None
    entrypoint: Any
    sandbox_db_path: Any
    env_vars: dict[str, str]
    synthetic_data: dict[str, Any]
