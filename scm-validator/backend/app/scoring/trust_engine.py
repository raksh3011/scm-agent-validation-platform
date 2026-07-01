"""Deterministic, evidence-backed trust scoring, organized into independent categories
so that a runtime failure in one area (e.g. the agent's entrypoint never became
reachable) cannot silently zero out unrelated dimensions like Business Trust. A
dimension's score is only ever `unknown` (not 0) when there genuinely isn't evidence to
compute it from — re-scoring the same execution results always yields the same numbers."""
from ..core.models import Defect, ScenarioExecutionResult, TrustDimensionScore

# dimension -> (category, max_score). Seven categories, weights sum to 100.
WEIGHTS: dict[str, tuple[str, float]] = {
    "pipeline_health": ("runtime_trust", 5),
    "runtime_robustness": ("runtime_trust", 5),
    "reproducibility": ("runtime_trust", 5),
    "business_logic_correctness": ("business_trust", 15),
    "decision_reliability": ("business_trust", 10),
    "business_kpi_impact": ("business_trust", 5),
    "operational_action_reliability": ("operational_trust", 8),
    "auditability": ("operational_trust", 7),
    "production_readiness": ("production_readiness", 10),
    "data_fault_handling": ("data_quality", 10),
    "security_resilience": ("security", 10),
    "performance_scalability": ("scalability", 10),
    "specification_conformance": ("specification_trust", 8),
    "requirement_coverage": ("specification_trust", 5),
    "decision_coverage": ("specification_trust", 4),
    "pairwise_interaction_coverage": ("specification_trust", 4),
    "constraint_validation": ("specification_trust", 4),
    "functional_completeness": ("specification_trust", 5),
    "architectural_maturity": ("architecture_trust", 12),
}

_ARCH_SEVERITY_PENALTY = {"critical": 0.22, "high": 0.10, "medium": 0.05, "low": 0.02}

_UNREACHABLE_REASON = "Business decision validation did not run because an earlier pipeline stage failed."

_POSITIVE_PERCENT_KPIS = {
    "service_level_proxy", "working_capital_efficiency", "emergency_order_handling",
    "forecast_accuracy", "forecast_direction_accuracy",
}
_NEGATIVE_PERCENT_KPIS = {"stockout_risk_rate"}

_SLOW_SCENARIO_THRESHOLD_MS = 3000.0


def _ratio(n: float, d: float) -> float:
    return n / d if d else 0.0


def _add(scores: list[TrustDimensionScore], dim: str, fraction: float | None, rationale: str,
         reason: str | None = None, refs: list[str] | None = None):
    category, max_score = WEIGHTS[dim]
    if fraction is None:
        scores.append(TrustDimensionScore(dimension=dim, category=category, score=0.0, max_score=max_score,
                                           rationale=rationale, state="unknown", reason=reason, evidence_refs=refs or []))
        return
    fraction = max(0.0, min(1.0, fraction))
    scores.append(TrustDimensionScore(dimension=dim, category=category, score=round(fraction * max_score, 2),
                                       max_score=max_score, rationale=rationale, state="computed",
                                       evidence_refs=refs or []))


def _architectural_maturity_fraction(arch_defects: list[Defect]) -> float:
    penalty = sum(_ARCH_SEVERITY_PENALTY.get(d.severity, 0.05) for d in arch_defects)
    return max(0.0, 1.0 - penalty)


def compute_unreachable(pipeline_health_fraction: float, arch_defects: list | None = None
                         ) -> tuple[list[TrustDimensionScore], float | None, str]:
    """Used when sandbox_validation (or an earlier stage) failed and business decision
    validation never ran. Only Runtime Trust's pipeline_health is computable — every
    other dimension is explicitly `unknown`, and the overall score is left unset rather
    than implying a real (low) assessment was performed. Architectural maturity is a
    static-code fact independent of runtime, so it is still computable here."""
    arch_defects = arch_defects or []
    scores: list[TrustDimensionScore] = []
    _add(scores, "pipeline_health", pipeline_health_fraction,
         f"Pipeline reached {pipeline_health_fraction:.0%} of its stages successfully before stopping.")
    _add(scores, "architectural_maturity", _architectural_maturity_fraction(arch_defects),
         f"{len(arch_defects)} static architecture/production-readiness defect(s) found "
         f"(hardcoded predictions, missing persistence, missing SCM entities, etc.) independent of runtime.")
    for dim in WEIGHTS:
        if dim in ("pipeline_health", "architectural_maturity"):
            continue
        _add(scores, dim, None, "Not computable — no business execution occurred.", reason=_UNREACHABLE_REASON)
    return scores, None, "Insufficient Evidence"


def compute(results: list[ScenarioExecutionResult], defects: list[Defect], static_facts: dict,
            repro_pairs: list[tuple[str, str, str]], kpis: list | None = None,
            pipeline_health_fraction: float = 1.0, conformance=None,
            evalgen_stats=None, arch_defects: list[Defect] | None = None
            ) -> tuple[list[TrustDimensionScore], float, str]:
    total = len(results) or 1
    passed = [r for r in results if r.status == "pass"]
    partial = [r for r in results if r.status == "partial"]
    errored = [r for r in results if r.status == "error"]
    judged = [r for r in results if r.status != "error"]
    kpis = kpis or []
    graph = static_facts.get("business_capability_graph") or {}
    caps = {c.get("name") for c in graph.get("supported_capabilities", []) if isinstance(c, dict)}

    scores: list[TrustDimensionScore] = []

    _add(scores, "pipeline_health", pipeline_health_fraction,
         f"Pipeline reached {pipeline_health_fraction:.0%} of its stages successfully.")

    _add(scores, "runtime_robustness", 1.0 - _ratio(len(errored), total),
         f"{len(errored)}/{total} scenarios ended in an unhandled error.")

    if repro_pairs:
        stable = sum(1 for _, a, b in repro_pairs if a == b)
        _add(scores, "reproducibility", _ratio(stable, len(repro_pairs)),
             f"{stable}/{len(repro_pairs)} re-executed scenarios produced an identical outcome on a second run.")
    else:
        _add(scores, "reproducibility", 1.0, "No repeated-execution sample was taken.")

    if judged:
        weighted_business = sum(
            (1.0 if r.status == "pass" else 0.55 if r.status == "partial" else 0.0) * max(0.25, r.confidence)
            for r in judged
        )
        confidence_weight = sum(max(0.25, r.confidence) for r in judged) or 1.0
        _add(scores, "business_logic_correctness", weighted_business / confidence_weight,
             f"Evidence-weighted business validation across {len(judged)} scenario(s), using inferred repository policy "
             f"({graph.get('primary_policy', 'unknown')}) plus fallback SCM references.")
    else:
        _add(scores, "business_logic_correctness", None, "No business decisions were validated.",
             reason="All executions crashed or no decision output was recognized.")

    _add(scores, "decision_reliability", _ratio(len(passed) + 0.55 * len(partial), total),
         f"{len(passed)} pass + {len(partial)} partial out of {total} scenarios; partials represent low/medium-confidence "
         "issues rather than unsupported hard failures.")

    kpi_fractions = []
    for k in kpis:
        if k.name in _POSITIVE_PERCENT_KPIS:
            kpi_fractions.append(max(0.0, min(1.0, k.value / 100)))
        elif k.name in _NEGATIVE_PERCENT_KPIS:
            kpi_fractions.append(max(0.0, min(1.0, 1 - k.value / 100)))
    if kpi_fractions:
        _add(scores, "business_kpi_impact", sum(kpi_fractions) / len(kpi_fractions),
             f"Average of {len(kpi_fractions)} business-outcome KPI(s) computed for this run.")
    else:
        _add(scores, "business_kpi_impact", None, "No business KPIs were computable for this run.",
             reason="Agent output did not contain a recognizable decision/quantity field.")

    if "purchase_order" in caps:
        expected_action = [r for r in results if r.status in ("pass", "partial")]
        with_evidence = [r for r in expected_action if r.evidence]
        _add(scores, "operational_action_reliability", _ratio(len(with_evidence), len(expected_action) or 1),
             f"{len(with_evidence)}/{len(expected_action)} successful decisions left runtime evidence "
             "(persistence, mock calls) of an actual operational action.")
    else:
        _add(scores, "operational_action_reliability", None,
             "Not computable because the repository did not expose purchase-order or operational-write capability.",
             reason="Unsupported capability should not be penalized.")

    with_any_evidence = [r for r in results if r.evidence]
    _add(scores, "auditability", _ratio(len(with_any_evidence), total),
         f"{len(with_any_evidence)}/{total} scenarios produced at least one evidence record.")

    critical = sum(1 for d in defects if d.severity == "critical")
    high = sum(1 for d in defects if d.severity == "high")
    _add(scores, "production_readiness", max(0.0, 1.0 - 0.3 * critical - 0.1 * high),
         f"{critical} critical and {high} high severity defects detected.")

    fault_scenarios = [r for r in results if r.scenario.inputs.get("fault")]
    fault_errored = [r for r in fault_scenarios if r.status == "error"]
    _add(scores, "data_fault_handling", 1.0 - _ratio(len(fault_errored), len(fault_scenarios) or 1),
         f"{len(fault_errored)}/{len(fault_scenarios)} runtime/data-fault scenarios caused an unhandled error "
         "rather than a graceful degraded response.")

    security_scenarios = [r for r in results if r.scenario.category == "security"]
    security_errored = [r for r in security_scenarios if r.status == "error"]
    _add(scores, "security_resilience", 1.0 - _ratio(len(security_errored), len(security_scenarios) or 1),
         f"{len(security_errored)}/{len(security_scenarios)} adversarial-input scenarios caused an unhandled "
         "error rather than a graceful degraded response.")

    stress_scenarios = [r for r in results if r.scenario.category == "stress"]
    stress_errored = [r for r in stress_scenarios if r.status == "error"]
    fast = [r for r in results if r.runtime_ms <= _SLOW_SCENARIO_THRESHOLD_MS]
    stress_fraction = 1.0 - _ratio(len(stress_errored), len(stress_scenarios) or 1)
    speed_fraction = _ratio(len(fast), total)
    _add(scores, "performance_scalability", (stress_fraction + speed_fraction) / 2,
         f"{len(stress_scenarios) - len(stress_errored)}/{len(stress_scenarios)} stress scenarios completed "
         f"without error; {len(fast)}/{total} scenarios executed under {_SLOW_SCENARIO_THRESHOLD_MS:.0f}ms.")

    if conformance is not None:
        _add(scores, "specification_conformance", (conformance.conformance_score or 0) / 100,
             "Overall fidelity of the repository and runtime behaviour to the uploaded Agent Specification Document.")
        _add(scores, "requirement_coverage", conformance.requirement_coverage / 100,
             f"{conformance.requirement_coverage:.0f}% of ASD requirements have traceable pass/warning evidence.")
        _add(scores, "decision_coverage", conformance.decision_coverage / 100,
             "Coverage of documented decision policies and outputs by repository/runtime evidence.")
        _add(scores, "constraint_validation", conformance.constraint_coverage / 100,
             "Coverage of documented business/compliance constraints by repository/runtime evidence.")
        _add(scores, "functional_completeness", conformance.functional_coverage / 100,
             "Coverage of documented responsibilities and workflows by repository/runtime evidence.")
    else:
        for dim in ("specification_conformance", "requirement_coverage", "decision_coverage", "constraint_validation",
                    "functional_completeness"):
            _add(scores, dim, None, "Not computable — no Agent Specification Document was uploaded for this run.",
                 reason="No ASD provided.")

    arch_defects = arch_defects or []
    _add(scores, "architectural_maturity", _architectural_maturity_fraction(arch_defects),
         f"{len(arch_defects)} static architecture/production-readiness defect(s) found independent of "
         "runtime behaviour (e.g. hardcoded predictions, simulated/non-persisted actions, missing SCM "
         "entities, no tests, hardcoded weights).")

    if evalgen_stats is not None:
        _add(scores, "pairwise_interaction_coverage", evalgen_stats.pairwise_coverage / 100,
             f"Pairwise testing generator achieved {evalgen_stats.pairwise_coverage:.0f}% interaction coverage across "
             f"{len(evalgen_stats.parameters)} business variable(s) using {evalgen_stats.optimized_scenario_count} "
             f"scenario(s) (reduced from {evalgen_stats.total_candidate_scenarios} candidates).")
    else:
        _add(scores, "pairwise_interaction_coverage", None,
             "Not computable — no business variables were inferred for pairwise generation.",
             reason="EvalGen found no usable business variables.")

    computed_scores = [s for s in scores if s.state == "computed"]
    computed_max = sum(s.max_score for s in computed_scores) or 1.0
    overall = round(sum(s.score for s in computed_scores) / computed_max * 100, 1)

    business_trust_unknown = any(s.category == "business_trust" and s.state == "unknown" for s in scores)
    if business_trust_unknown:
        label = "Insufficient Evidence"
    elif overall >= 85 and critical == 0:
        label = "Production Ready"
    elif overall >= 65:
        label = "Conditional"
    else:
        label = "Not Ready"

    return scores, overall, label
