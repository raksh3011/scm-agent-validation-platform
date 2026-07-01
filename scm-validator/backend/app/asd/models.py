from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class AsdRequirement:
    id: str
    category: str
    text: str
    required: bool = True
    source_section: str | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class AgentSpecification:
    source_name: str
    format: str
    agent_name: str | None = None
    scm_domain: str | None = None
    business_objective: str | None = None
    scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    decision_policies: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    kpis: list[str] = field(default_factory=list)
    requirements: list[AsdRequirement] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RequirementConformance:
    requirement_id: str
    status: Literal["pass", "fail", "warning", "observation", "not_tested"]
    confidence: float
    rationale: str
    repository_evidence: list[str] = field(default_factory=list)
    scenario_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class AsdConformanceReport:
    conformance_score: float | None
    requirement_coverage: float
    functional_coverage: float
    input_coverage: float
    output_coverage: float
    constraint_coverage: float
    integration_coverage: float
    kpi_coverage: float
    decision_coverage: float
    requirements: list[RequirementConformance] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
