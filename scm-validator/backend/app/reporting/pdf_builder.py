"""Assembles the consultant-grade PDF report. ~40% of the document is the generated
test case catalogue + scenario execution results, per spec — nothing is hidden."""
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# Consultant-report palette.
NAVY = colors.HexColor("#1e2433")
INDIGO = colors.HexColor("#4f46e5")
SUCCESS = colors.HexColor("#16a34a")
WARNING = colors.HexColor("#d97706")
DANGER = colors.HexColor("#dc2626")
MUTED = colors.HexColor("#6b7280")
LIGHT_BG = colors.HexColor("#f3f4f6")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=NAVY, fontSize=17, spaceAfter=4, fontName="Helvetica-Bold")
H1_SUB = ParagraphStyle("H1Sub", parent=styles["BodyText"], textColor=INDIGO, fontSize=9, spaceAfter=10, fontName="Helvetica-Bold")
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=NAVY, fontSize=12, spaceAfter=6, spaceBefore=12)
BODY = ParagraphStyle("BodyCustom", parent=styles["BodyText"], fontSize=9, leading=12.5, textColor=colors.HexColor("#1f2937"))
SMALL = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=7.5, leading=9)
COVER_TITLE = ParagraphStyle("CoverTitle", parent=styles["Title"], textColor=NAVY, fontSize=26, leading=30)


def _status_text_color(status: str):
    return {"ok": SUCCESS, "failed": DANGER, "partial": WARNING, "skipped": MUTED}.get(status, MUTED)


def _bar_chart(rows: list[tuple], max_value: float = 100, bar_width: float = 280, row_height: float = 16):
    """rows: list of (label, value, color). Simple horizontal bar chart with no
    external plotting dependency — just reportlab shape primitives."""
    if not rows:
        return Spacer(1, 1)
    height = row_height * len(rows) + 6
    label_width = 130
    d = Drawing(label_width + bar_width + 50, height)
    for i, (label, value, color) in enumerate(rows):
        y = height - (i + 1) * row_height + 4
        d.add(String(0, y, str(label)[:20], fontSize=7, fillColor=NAVY))
        bw = max(2, (max(0.0, min(100.0, value)) / max_value) * bar_width)
        d.add(Rect(label_width, y - 2, bar_width, row_height - 6, fillColor=LIGHT_BG, strokeColor=None))
        d.add(Rect(label_width, y - 2, bw, row_height - 6, fillColor=color, strokeColor=None))
        d.add(String(label_width + bar_width + 6, y, f"{value:.0f}", fontSize=7, fillColor=NAVY))
    return d


def _p(text: str, style=BODY):
    return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def _section_title(text: str):
    return [Paragraph(text, H1), HRFlowable(width="100%", thickness=1.2, color=INDIGO, spaceAfter=8)]


def _kv_table(rows: list[tuple[str, str]]):
    data = [[_p(k), _p(v)] for k, v in rows]
    t = Table(data, colWidths=[2.2 * inch, 4.3 * inch])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]))
    return t


def _exec_summary(ctx: dict) -> list:
    context = ctx.get("context") or {}
    asd_spec = ctx.get("asd_spec")
    story = [*_section_title("Executive Summary")]
    story.append(_kv_table([
        ("Agent Name", ctx["agent_name"]),
        ("Run ID", ctx["run_id"]),
        ("Generated", ctx["timestamp"]),
        ("Source Repository / Upload", context.get("source_ref") or "Not recorded"),
        ("Agent Specification", asd_spec.source_name if asd_spec else "Not uploaded for this run"),
        ("Primary SCM Agent Type", ctx["classification"].primary_type.replace("_", " ").title()),
        ("Classification Confidence", f"{ctx['classification'].confidence:.0%}"),
        ("Secondary Capabilities", ", ".join(ctx["classification"].secondary_capabilities) or "None detected"),
        ("Overall Trust Score", f"{ctx['overall_score']} / 100" if ctx["overall_score"] is not None else "Not computable"),
        ("Production Readiness", ctx["readiness_label"]),
        ("Total Scenarios Generated", str(len(ctx["scenarios"]))),
        ("Scenarios Passed", str(sum(1 for r in ctx["results"] if r.status == "pass"))),
        ("Defects Identified", str(len(ctx["defects"]))),
    ]))
    if asd_spec and asd_spec.business_objective:
        story.append(Spacer(1, 6))
        story.append(_p(f"<b>Specification gist:</b> {asd_spec.business_objective}"))
    return story


def _repo_overview(ctx: dict) -> list:
    facts = ctx["static_facts"]
    return [*_section_title("Repository Overview"), _kv_table([
        ("Language", ctx["profile"].language),
        ("Framework", ctx["profile"].framework or "Not detected"),
        ("Python Files Analyzed", str(facts.get("total_files", 0))),
        ("Lines of Code", str(facts.get("total_lines", 0))),
        ("Persistence Calls Found", str(facts.get("has_persistence_call"))),
        ("Error Handling Found", str(facts.get("has_error_handling"))),
        ("Logging Found", str(facts.get("has_logging"))),
    ])]


def _classification_section(ctx: dict) -> list:
    c = ctx["classification"]
    graph = (ctx.get("static_facts") or {}).get("business_capability_graph") or {}
    story = [*_section_title("SCM Agent Classification")]
    story.append(_p(f"Primary type: <b>{c.primary_type.replace('_', ' ').title()}</b> "
                     f"(confidence {c.confidence:.0%}), derived from the repository's decision-function "
                     f"workflow graph rather than keyword matching."))
    story.append(Spacer(1, 6))
    top_terms = c.signals.get("top_terms", [])
    if top_terms:
        story.append(_p("Dominant business-decision terms observed in branching, structured-return functions:"))
        story.append(_kv_table([(term, str(round(weight, 1))) for term, weight in top_terms[:10]]))
    if graph:
        caps = graph.get("supported_capabilities", [])
        story.append(Spacer(1, 8))
        story.append(_p("<b>Business Capability Graph</b>"))
        story.append(_kv_table([
            ("Business Objective", graph.get("business_objective", "Unknown")),
            ("Inferred Policy", f"{graph.get('primary_policy', 'unknown')} ({graph.get('policy_confidence', 0):.0%})"),
            ("Supported Capabilities", ", ".join(c.get("name", "") for c in caps) or "None detected"),
            ("Business Entities", ", ".join(graph.get("business_entities", [])) or "None detected"),
            ("Optimization Objectives", ", ".join(graph.get("optimization_objectives", [])) or "None detected"),
            ("Unsupported Capabilities", ", ".join(graph.get("unsupported_capabilities", [])[:8]) or "None"),
        ]))
    return story


def _scenario_dashboard(ctx: dict) -> list:
    results = ctx["results"]
    total = len(results) or 1
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    partial = sum(1 for r in results if r.status == "partial")
    errored = sum(1 for r in results if r.status == "error")
    avg_runtime = sum(r.runtime_ms for r in results) / total
    return [*_section_title("Scenario Dashboard"), _kv_table([
        ("Total Test Cases Generated", str(len(ctx["scenarios"]))),
        ("Total Executed", str(total)),
        ("Passed", str(passed)),
        ("Failed", str(failed)),
        ("Partial Pass", str(partial)),
        ("Runtime / Environment Failures", str(errored)),
        ("Average Runtime (ms)", f"{avg_runtime:.1f}"),
        ("Scenario Categories Covered", str(len({r.scenario.category for r in results}))),
    ])]


def _status_color(status: str):
    return {"pass": colors.HexColor("#1a7f37"), "fail": colors.HexColor("#b00020"),
            "partial": colors.HexColor("#b06000"), "error": colors.HexColor("#6e6e6e")}.get(status, colors.black)


def _test_case_matrix(ctx: dict) -> list:
    story = [*_section_title("Complete Test Case Catalogue & Scenario Execution Results"),
             _p("Every generated scenario is listed below — no hidden test cases.")]
    header = ["ID", "Scenario", "Category", "Expected", "Actual", "Status", "Runtime (ms)", "Severity"]
    data = [header]
    for r in ctx["results"]:
        actual_summary = "error" if r.error else str(r.actual_behaviour.get("return_value"))[:60]
        data.append([
            r.scenario.id, r.scenario.name[:28], r.scenario.category,
            r.scenario.expected_behaviour[:40], actual_summary, r.status.upper(),
            f"{r.runtime_ms:.0f}", r.scenario.severity_if_failed,
        ])
    t = Table(data, colWidths=[0.55 * inch, 1.25 * inch, 0.85 * inch, 1.3 * inch, 1.3 * inch, 0.55 * inch, 0.6 * inch, 0.6 * inch],
              repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6.3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, r in enumerate(ctx["results"], start=1):
        style.append(("TEXTCOLOR", (5, i), (5, i), _status_color(r.status)))
    t.setStyle(TableStyle(style))
    story.append(t)
    return story


def _behaviour_analysis(ctx: dict) -> list:
    results = ctx["results"]
    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r.scenario.category, []).append(r)
    rows = []
    for cat, rs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        pass_rate = sum(1 for r in rs if r.status == "pass") / len(rs)
        rows.append((cat, f"{pass_rate:.0%} pass ({len(rs)} scenarios)"))
    strongest = max(rows, key=lambda kv: kv[1]) if rows else None
    story = [*_section_title("Behaviour Analysis")]
    story.append(_p("Pass rate by scenario category (weakest categories indicate the riskiest business behaviour):"))
    story.append(_kv_table(rows))
    return story


def _trust_score_section(ctx: dict) -> list:
    story = [*_section_title("Trust Score Breakdown")]
    overall = ctx["overall_score"]
    overall_text = f"{overall} / 100" if overall is not None else "Not computable"
    story.append(_p(f"<b>Overall Trust Score: {overall_text} — {ctx['readiness_label']}</b>"))
    story.append(Spacer(1, 8))

    computed = [s for s in ctx["trust_scores"] if s.state == "computed"]
    if computed:
        chart_rows = [(s.dimension.replace("_", " ").title(), (s.score / s.max_score) * 100,
                       SUCCESS if s.score / s.max_score >= 0.7 else (WARNING if s.score / s.max_score >= 0.4 else DANGER))
                      for s in computed]
        story.append(_bar_chart(chart_rows))
        story.append(Spacer(1, 10))

    rows = []
    for s in ctx["trust_scores"]:
        if s.state == "unknown":
            rows.append((f"{s.dimension.replace('_', ' ').title()} (UNKNOWN)", s.reason or "Not computable."))
        else:
            rows.append((s.dimension.replace("_", " ").title(), f"{s.score}/{s.max_score} — {s.rationale}"))
    story.append(_kv_table(rows))
    return story


def _pipeline_dashboard_section(ctx: dict) -> list:
    story = [*_section_title("Pipeline Execution Dashboard")]
    stages = ctx.get("stages") or []
    if not stages:
        story.append(_p("No staged pipeline data was recorded for this run."))
        return story
    story.append(_p("Shows exactly which stage validation stopped at, if any — business metrics are never "
                     "scored from a stage that never ran."))
    story.append(Spacer(1, 6))
    symbol = {"ok": "PASS", "failed": "FAILED", "skipped": "SKIPPED", "partial": "PARTIAL"}
    data = [[_p("Stage"), _p("Status"), _p("Detail")]]
    row_colors = []
    for s in stages:
        data.append([_p(s.stage.replace("_", " ").title()), _p(symbol.get(s.status, s.status.upper())), _p(s.detail[:90])])
        row_colors.append(_status_text_color(s.status))
    t = Table(data, colWidths=[1.6 * inch, 0.8 * inch, 4.1 * inch], repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, c in enumerate(row_colors, start=1):
        style.append(("TEXTCOLOR", (1, i), (1, i), c))
        style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    story.append(t)

    failed_stages = [s for s in stages if s.status == "failed" and s.recovery_suggestions]
    if failed_stages:
        story.append(Spacer(1, 10))
        story.append(_p("<b>Recovery Suggestions</b>", H2))
        for s in failed_stages:
            for rec in s.recovery_suggestions:
                story.append(_p(f"• ({s.stage.replace('_', ' ')}) {rec}"))
    return story


def _root_cause_section(ctx: dict) -> list:
    story = [*_section_title("Root Cause Analysis")]
    causes = ctx.get("root_causes") or []
    if not causes:
        story.append(_p("No repeated failure signatures were detected for this run."))
        return story
    story.append(_p("Repeated identical failures are grouped into a single root cause below, instead of "
                     "listing every affected scenario individually."))
    story.append(Spacer(1, 6))
    for rc in causes:
        story.append(_p(f"<b>{rc.exception_type}</b> — {rc.affected_count} scenario(s) affected "
                         f"(confidence {rc.confidence:.0%})", H2))
        story.append(_kv_table([
            ("Message", rc.normalized_message[:200]),
            ("Recovery Suggestion", rc.recovery_suggestion),
            ("Affected Scenarios", ", ".join(rc.affected_scenario_ids[:15]) +
             (f" +{len(rc.affected_scenario_ids) - 15} more" if len(rc.affected_scenario_ids) > 15 else "")),
        ]))
        story.append(Spacer(1, 6))
    return story


def _defects_section(ctx: dict) -> list:
    story = [*_section_title("Defects & Business Risks")]
    if not ctx["defects"]:
        story.append(_p("No defects were identified that meet the evidence-backed reporting threshold."))
        return story
    for d in ctx["defects"]:
        story.append(_p(f"<b>[{d.severity.upper()}] {d.title}</b> (confidence {d.confidence:.0%})", H2))
        location = "Not applicable — repository-wide finding, no single line of origin"
        if d.file_path:
            location = f"{d.file_path}" + (f":{d.line_number}" if d.line_number else "") + \
                (f" (in `{d.function_name}`)" if d.function_name else "")
        story.append(_kv_table([
            ("Category", d.category), ("Type", d.defect_type),
            ("File / Line / Function", location),
            ("Violated Requirement", ", ".join(d.violated_requirement) or "Not linked to a specific ASD requirement"),
            ("Root Cause", d.root_cause or d.technical_explanation),
            ("Business Impact", d.business_impact),
            ("Technical Explanation", d.technical_explanation),
            ("Recommendation", d.recommendation),
            ("Affected Scenarios", ", ".join(d.scenario_refs[:15]) or "None (static finding)"),
            ("Verification Steps", "; ".join(d.verification_steps)),
        ]))
        story.append(Spacer(1, 6))
    return story


def _readiness_section(ctx: dict) -> list:
    story = [*_section_title("Production Readiness Assessment")]
    score_text = f"{ctx['overall_score']}/100" if ctx["overall_score"] is not None else "not computable"
    story.append(_p(f"This agent is assessed as: <b>{ctx['readiness_label']}</b> (overall trust score {score_text})."))
    if ctx["readiness_label"] == "Insufficient Evidence":
        story.append(_p("Business decision validation did not run — see the Pipeline Execution Dashboard and "
                         "Root Cause Analysis sections for exactly where validation stopped."))
    critical = [d for d in ctx["defects"] if d.severity == "critical"]
    if critical:
        story.append(_p(f"{len(critical)} critical defect(s) must be resolved before production deployment."))
    return story


def _roadmap_section(ctx: dict) -> list:
    story = [*_section_title("Prioritized Improvement Roadmap")]
    ordered = sorted(ctx["defects"], key=lambda d: {"critical": 0, "high": 1, "medium": 2, "low": 3}[d.severity])
    rows = [(f"P{i+1}", f"{d.title} — {d.recommendation}") for i, d in enumerate(ordered)]
    if rows:
        story.append(_kv_table(rows))
    else:
        story.append(_p("No outstanding improvements identified."))
    return story


def _kpi_section(ctx: dict) -> list:
    story = [*_section_title("Business KPI Analysis")]
    kpis = ctx.get("kpis") or []
    if not kpis:
        story.append(_p("No business KPIs were computable for this run."))
        return story
    story.append(_kv_table([(k.name.replace("_", " ").title(), f"{k.value} {k.unit} — {k.description}") for k in kpis]))
    return story


def _decision_trace_section(ctx: dict) -> list:
    story = [*_section_title("Decision Trace (representative scenarios)")]
    traces = ctx.get("decision_traces") or {}
    if not traces:
        story.append(_p("No decision traces were captured for this run."))
        return story
    for scenario_id, steps in list(traces.items())[:10]:
        story.append(_p(f"<b>{scenario_id}</b>", H2))
        rows = [(s["step"].replace("_", " ").title(), str(s["value"])) for s in steps]
        story.append(_kv_table(rows))
        story.append(Spacer(1, 6))
    return story


def _risk_matrix_section(ctx: dict) -> list:
    story = [*_section_title("Risk Matrix")]
    defects = ctx.get("defects") or []
    if not defects:
        story.append(_p("No defects to plot on the risk matrix."))
        return story
    data = [[_p("Severity"), _p("Confidence"), _p("Defect")]]
    for d in sorted(defects, key=lambda d: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[d.severity])):
        data.append([_p(d.severity.upper()), _p(f"{d.confidence:.0%}"), _p(d.title)])
    t = Table(data, colWidths=[1.0 * inch, 1.0 * inch, 4.5 * inch])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    return story


def _historical_section(ctx: dict) -> list:
    delta = ctx.get("historical_delta")
    if not delta:
        return [*_section_title("Historical Comparison"), _p("This is the first recorded run for this agent.")]
    story = [*_section_title("Historical Comparison")]
    story.append(_kv_table([
        ("Previous Run", delta.get("previous_run_id") or "N/A"),
        ("Score Delta", str(delta.get("score_delta"))),
        ("New Defects", str(len(delta.get("new_defects", [])))),
        ("Resolved Defects", str(len(delta.get("resolved_defects", [])))),
    ]))
    return story


def _asd_summary_section(ctx: dict) -> list:
    spec = ctx.get("asd_spec")
    story = [*_section_title("Agent Specification Summary")]
    if not spec:
        story.append(_p("No Agent Specification Document was uploaded for this run — the platform validated "
                         "the repository against inferred capabilities only, not a declared contract."))
        return story
    story.append(_kv_table([
        ("Source", f"{spec.source_name} ({spec.format})"),
        ("Agent Name", spec.agent_name or "Not specified"),
        ("SCM Domain", spec.scm_domain or "Not specified"),
        ("Business Objective", spec.business_objective or "Not specified"),
        ("Scope", "; ".join(spec.scope) or "Not specified"),
        ("Out of Scope", "; ".join(spec.out_of_scope) or "Not specified"),
        ("Stakeholders", "; ".join(spec.stakeholders) or "Not specified"),
        ("Inputs", "; ".join(spec.inputs) or "Not specified"),
        ("Outputs", "; ".join(spec.outputs) or "Not specified"),
        ("Integrations", "; ".join(spec.integrations) or "Not specified"),
        ("Constraints", "; ".join(spec.constraints) or "Not specified"),
        ("KPIs", "; ".join(spec.kpis) or "Not specified"),
        ("Total Requirements Extracted", str(len(spec.requirements))),
    ]))
    return story


def _conformance_section(ctx: dict) -> list:
    story = [*_section_title("Specification Conformance Score")]
    conf = ctx.get("conformance")
    if not conf:
        story.append(_p("No conformance assessment was computed — upload an Agent Specification Document to "
                         "enable specification-traceable validation."))
        return story
    score_text = f"{conf.conformance_score}/100" if conf.conformance_score is not None else "Not computable"
    story.append(_p(f"<b>Overall Specification Conformance: {score_text}</b>"))
    story.append(Spacer(1, 6))
    story.append(_kv_table([
        ("Requirement Coverage", f"{conf.requirement_coverage:.0f}%"),
        ("Functional Coverage", f"{conf.functional_coverage:.0f}%"),
        ("Input Coverage", f"{conf.input_coverage:.0f}%"),
        ("Output Coverage", f"{conf.output_coverage:.0f}%"),
        ("Constraint Coverage", f"{conf.constraint_coverage:.0f}%"),
        ("Integration Coverage", f"{conf.integration_coverage:.0f}%"),
        ("KPI Coverage", f"{conf.kpi_coverage:.0f}%"),
        ("Decision Coverage", f"{conf.decision_coverage:.0f}%"),
    ]))
    return story


def _requirement_traceability_section(ctx: dict) -> list:
    story = [*_section_title("Requirement Traceability Matrix")]
    conf = ctx.get("conformance")
    if not conf or not conf.requirements:
        story.append(_p("No requirement-level traceability available for this run."))
        return story
    status_color = {"pass": SUCCESS, "fail": DANGER, "warning": WARNING, "observation": MUTED, "not_tested": MUTED}
    data = [[_p("Req. ID"), _p("Status"), _p("Rationale"), _p("Scenarios"), _p("Evidence")]]
    for rc in conf.requirements:
        data.append([
            _p(rc.requirement_id), _p(rc.status.upper()), _p(rc.rationale[:90]),
            _p(", ".join(rc.scenario_refs[:6]) + (f" +{len(rc.scenario_refs) - 6}" if len(rc.scenario_refs) > 6 else "")),
            _p(str(len(rc.evidence_refs))),
        ])
    t = Table(data, colWidths=[0.6 * inch, 0.7 * inch, 2.6 * inch, 1.7 * inch, 0.7 * inch], repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, rc in enumerate(conf.requirements, start=1):
        style.append(("TEXTCOLOR", (1, i), (1, i), status_color.get(rc.status, MUTED)))
        style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    story.append(t)
    return story


def _evalgen_section(ctx: dict) -> list:
    story = [*_section_title("Pairwise Testing Coverage Summary")]
    stats = ctx.get("evalgen_stats")
    if not stats:
        story.append(_p("No pairwise testing scenarios were generated — no usable business variables were "
                         "inferred from the specification, repository, or business capability graph."))
        return story
    story.append(_p("Pairwise testing applies a deterministic greedy combinatorial algorithm to the inferred "
                     "business variables, replacing brute-force enumeration with a compact, high-coverage "
                     "scenario set."))
    story.append(Spacer(1, 6))
    story.append(_kv_table([
        ("Business Variables", ", ".join(stats.parameters) or "None"),
        ("Total Candidate Scenarios", str(stats.total_candidate_scenarios)),
        ("Optimized Scenario Count", str(stats.optimized_scenario_count)),
        ("Redundant Scenario Reduction", f"{stats.redundant_scenario_reduction:.0f}%"),
        ("Pairwise Coverage", f"{stats.pairwise_coverage:.0f}%"),
        ("Parameter Coverage", f"{stats.parameter_coverage:.0f}%"),
        ("Interaction Coverage", f"{stats.interaction_coverage:.0f}%"),
    ]))
    return story


def _evidence_appendix(ctx: dict) -> list:
    story = [*_section_title("Evidence Appendix")]
    story.append(_p("Evidence referenced throughout this report (truncated for length):"))
    rows = []
    count = 0
    for r in ctx["results"]:
        for e in r.evidence:
            rows.append((e.id, f"{e.evidence_type} (scenario {r.scenario.id})"))
            count += 1
            if count >= 80:
                break
        if count >= 80:
            break
    if rows:
        story.append(_kv_table(rows))
    return story


def build_report(ctx: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    story = []
    for section_fn in (_exec_summary, _repo_overview, _classification_section, _scenario_dashboard):
        story += section_fn(ctx)
        story.append(Spacer(1, 10))
    story.append(PageBreak())
    for section_fn in (_asd_summary_section, _conformance_section, _evalgen_section):
        story += section_fn(ctx)
        story.append(Spacer(1, 10))
    story.append(PageBreak())
    story += _requirement_traceability_section(ctx)
    story.append(PageBreak())
    story += _test_case_matrix(ctx)
    story.append(PageBreak())
    story += _pipeline_dashboard_section(ctx)
    story.append(PageBreak())
    story += _root_cause_section(ctx)
    story.append(PageBreak())
    for section_fn in (_behaviour_analysis, _trust_score_section):
        story += section_fn(ctx)
        story.append(Spacer(1, 10))
    story.append(PageBreak())
    story += _kpi_section(ctx)
    story.append(Spacer(1, 10))
    story += _decision_trace_section(ctx)
    story.append(PageBreak())
    story += _defects_section(ctx)
    story += _risk_matrix_section(ctx)
    story += _readiness_section(ctx)
    story += _roadmap_section(ctx)
    story.append(PageBreak())
    story += _historical_section(ctx)
    story += _evidence_appendix(ctx)
    doc.build(story)
    return output_path
