from __future__ import annotations

from .models import AgentSpecification, AsdConformanceReport, RequirementConformance


def _norm(s: str) -> str:
    return s.lower().replace("_", " ")


def _graph_terms(graph: dict, static_facts: dict) -> set[str]:
    terms = set()
    for c in graph.get("supported_capabilities", []):
        if isinstance(c, dict):
            terms.add(_norm(c.get("name", "")))
            terms.update(_norm(e) for e in c.get("evidence", []))
    terms.update(_norm(v) for v in graph.get("decision_variables", []))
    terms.update(_norm(v) for v in graph.get("business_entities", []))
    terms.update(_norm(v) for v in graph.get("optimization_objectives", []))
    if static_facts.get("has_persistence_call"):
        terms.update({"purchase order", "database", "persistence", "operational write"})
    if static_facts.get("has_error_handling"):
        terms.add("error handling")
    return terms


def _coverage(items: list[str], terms: set[str]) -> float:
    if not items:
        return 100.0
    covered = 0
    for item in items:
        lower = _norm(item)
        if any(t and (t in lower or lower in t) for t in terms):
            covered += 1
    return round(covered / len(items) * 100, 1)


def evaluate(spec: AgentSpecification | None, graph: dict, static_facts: dict, scenarios: list,
             results: list) -> AsdConformanceReport | None:
    if not spec:
        return None
    terms = _graph_terms(graph, static_facts)
    scenario_by_kw: dict[str, list[str]] = {}
    for s in scenarios:
        hay = _norm(f"{s.name} {s.category} {s.business_objective} {s.expected_behaviour} "
                    f"{' '.join(s.traceability.get('requirements', [])) if getattr(s, 'traceability', None) else ''}")
        for req in spec.requirements:
            if any(_norm(k).replace("_", " ") in hay for k in req.keywords):
                scenario_by_kw.setdefault(req.id, []).append(s.id)

    result_by_sid = {r.scenario.id: r for r in results}
    conformance: list[RequirementConformance] = []
    passed = 0
    tested = 0
    for req in spec.requirements:
        text = _norm(req.text)
        repo_hits = [t for t in terms if t and (t in text or text in t)]
        scenario_refs = scenario_by_kw.get(req.id, [])
        evidence_refs = []
        runtime_ok = False
        for sid in scenario_refs:
            r = result_by_sid.get(sid)
            if r:
                evidence_refs.extend(e.id for e in r.evidence[:5])
                runtime_ok = runtime_ok or r.status in ("pass", "partial")
        if repo_hits and scenario_refs and runtime_ok:
            status, conf = "pass", 0.86
            passed += 1
            tested += 1
        elif repo_hits:
            status, conf = "warning", 0.65
            passed += 0.5
            tested += 1
        elif req.required:
            status, conf = "fail", 0.72
            tested += 1
        else:
            status, conf = "observation", 0.55
        conformance.append(RequirementConformance(
            requirement_id=req.id, status=status, confidence=conf,
            rationale=("Requirement has repository and runtime traceability." if status == "pass"
                       else "Requirement has repository evidence but limited runtime traceability." if status == "warning"
                       else "Required capability was not found in repository understanding signals." if status == "fail"
                       else "Optional/undocumented capability observed."),
            repository_evidence=repo_hits[:8],
            scenario_refs=scenario_refs[:20],
            evidence_refs=evidence_refs[:20],
        ))

    req_cov = round((passed / tested * 100) if tested else 100.0, 1)
    functional = _coverage(spec.responsibilities + spec.workflows, terms)
    input_cov = _coverage(spec.inputs, terms)
    output_cov = _coverage(spec.outputs, terms)
    constraint_cov = _coverage(spec.constraints, terms)
    integration_cov = _coverage(spec.integrations, terms)
    kpi_cov = _coverage(spec.kpis, terms)
    decision_cov = _coverage(spec.decision_policies + spec.outputs, terms)
    score = round((req_cov + functional + input_cov + output_cov + constraint_cov + integration_cov + kpi_cov + decision_cov) / 8, 1)
    return AsdConformanceReport(score, req_cov, functional, input_cov, output_cov,
                                constraint_cov, integration_cov, kpi_cov, decision_cov, conformance)
