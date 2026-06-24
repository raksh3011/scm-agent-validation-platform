import { ValidationResult } from "./types";

function esc(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function readinessColor(value: string): string {
  if (value.includes("Ready") && !value.includes("Not") && value !== "Requires Hardening") return "#16a34a";
  if (value === "Conditionally Ready" || value === "Requires Hardening") return "#d97706";
  return "#dc2626";
}

const SEVERITY_COLOR: Record<string, string> = {
  Critical: "#dc2626",
  High: "#ea580c",
  Medium: "#d97706",
  Low: "#65a30d",
};

/** Builds a self-contained, printable HTML report from the same validation data shown in the dashboard. */
export function buildReportHtml(result: ValidationResult): string {
  const { summary } = result;
  const evidenceById = new Map(result.evidence.map((e) => [e.id, e]));
  const findingById = new Map(result.findings.map((f) => [f.id, f]));

  const breakdownRows = result.score_breakdown
    .map(
      (b) => `
      <tr>
        <td>${esc(b.dimension)}</td>
        <td style="text-align:right;font-weight:600">${b.score}/${b.max_score}</td>
        <td>
          <div style="background:#eef1f5;border-radius:6px;height:8px;width:160px;overflow:hidden">
            <div style="height:100%;width:${(b.score / b.max_score) * 100}%;background:${
              b.score >= 80 ? "#16a34a" : b.score >= 55 ? "#d97706" : "#dc2626"
            }"></div>
          </div>
        </td>
        <td style="color:#64748b;font-size:13px">${esc(b.remarks)}</td>
      </tr>`
    )
    .join("");

  const signalItems = result.positive_signals.map((s) => `<li>${esc(s)}</li>`).join("");

  const findingCards = result.findings
    .map((f) => {
      const evidence = f.evidence_refs
        .map((id) => {
          const ev = evidenceById.get(id);
          if (!ev) return "";
          return `<code>${esc(ev.file_path)}${ev.line_start ? ":" + ev.line_start : ""}</code> — ${esc(ev.reason)}`;
        })
        .filter(Boolean)
        .join("<br/>");
      return `
      <div class="finding">
        <div class="finding-head">
          <span class="sev" style="background:${SEVERITY_COLOR[f.severity] || "#64748b"}">${esc(f.severity)}</span>
          <strong>${esc(f.title)}</strong>
          <span class="impact">-${f.score_impact} pts</span>
        </div>
        <div class="cat">${esc(f.category)}</div>
        <p>${esc(f.description)}</p>
        <p class="why"><strong>Why it matters:</strong> ${esc(f.why_it_matters)}</p>
        ${evidence ? `<div class="evidence">${evidence}</div>` : ""}
      </div>`;
    })
    .join("");

  const correctionCards = result.recommendations
    .map((r) => {
      const finding = findingById.get(r.finding_id);
      return `
      <div class="correction">
        <div class="correction-head">
          <strong>${esc(r.title)}</strong>
          <span class="priority">${esc(r.priority)}</span>
        </div>
        ${finding ? `<div class="cat">Fixes: ${esc(finding.title)}</div>` : ""}
        <p>${esc(r.recommendation)}</p>
        <p class="why">${esc(r.expected_impact)}</p>
      </div>`;
    })
    .join("");

  const insights = result.ai_insights.length
    ? `<section><h2>AI Insights</h2><ul>${result.ai_insights.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></section>`
    : "";

  const ADAPTER_STATUS_LABEL: Record<string, string> = {
    loaded: "Submitted adapter loaded",
    auto_generated: "Adapter auto-generated from detected entrypoint",
    failed: "No agent could be executed",
    not_attempted: "Not attempted",
  };

  function passFailBadge(passed: boolean): string {
    return `<span class="sev" style="background:${passed ? "#16a34a" : "#dc2626"}">${passed ? "PASS" : "FAIL"}</span>`;
  }

  const invariantCards = result.invariant_results
    .map(
      (inv) => `
      <div class="finding">
        <div class="finding-head">${passFailBadge(inv.passed)}<strong>${esc(inv.test_id)}</strong></div>
        <p class="why">${esc(inv.detail)}</p>
      </div>`
    )
    .join("");

  const scenarioCards = (tier: "required" | "recommended") =>
    result.scenario_results
      .filter((s) => s.tier === tier)
      .map(
        (sc) => `
      <div class="finding">
        <div class="finding-head">${passFailBadge(sc.passed)}<strong>${esc(sc.scenario_id)} — ${esc(sc.description)}</strong></div>
        <p class="why">${esc(sc.detail)}</p>
        ${!sc.passed ? `<div class="evidence">Expected: ${esc(JSON.stringify(sc.expected))}<br/>Actual: ${esc(JSON.stringify(sc.actual))}</div>` : ""}
      </div>`
      )
      .join("");

  const requiredCount = result.scenario_results.filter((s) => s.tier === "required");
  const recommendedCount = result.scenario_results.filter((s) => s.tier === "recommended");
  const invariantPassCount = result.invariant_results.filter((i) => i.passed).length;

  const harnessSection = `
  <section>
    <h2>Trust Harness — Execution-Based Behavior (dominant signal, 75% of overall)</h2>
    <p class="why"><strong>Adapter status:</strong> ${esc(ADAPTER_STATUS_LABEL[result.adapter_status] ?? result.adapter_status)}</p>
    ${result.adapter_status === "failed" ? `<p class="why" style="color:#dc2626">No agent could be executed for this submission, so the overall trust score is forced to 0 regardless of the hygiene score below.</p>` : ""}
    <h3 style="margin-bottom:4px">Invariant Tests (${invariantPassCount}/${result.invariant_results.length} passed)</h3>
    ${invariantCards || "<p>No invariant tests ran.</p>"}
    <h3 style="margin-bottom:4px">Golden Scenarios — Required (${requiredCount.filter((s) => s.passed).length}/${requiredCount.length} passed)</h3>
    ${scenarioCards("required") || "<p>No required scenarios ran.</p>"}
    ${recommendedCount.length > 0 ? `<h3 style="margin-bottom:4px">Golden Scenarios — Recommended (${recommendedCount.filter((s) => s.passed).length}/${recommendedCount.length} passed)</h3>${scenarioCards("recommended")}` : ""}
  </section>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>SCM Agent Validation Report — ${esc(summary.agent_name)}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:#1a202c; max-width:900px; margin:0 auto; padding:40px 32px; line-height:1.55; }
  h1 { margin:0 0 4px; }
  h2 { border-bottom:2px solid #e2e8f0; padding-bottom:6px; margin-top:36px; }
  .meta { color:#64748b; font-size:14px; margin-bottom:24px; }
  .summary-grid { display:flex; gap:24px; align-items:center; flex-wrap:wrap; background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:24px; }
  .score-big { font-size:52px; font-weight:800; color:#2563eb; line-height:1; }
  .pill { display:inline-flex; flex-direction:column; gap:2px; border:1px solid #e2e8f0; border-radius:10px; padding:10px 16px; }
  .pill .label { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#64748b; }
  .pill .value { font-weight:700; }
  table { width:100%; border-collapse:collapse; margin-top:12px; }
  td, th { padding:9px 10px; border-bottom:1px solid #e2e8f0; font-size:14px; text-align:left; vertical-align:middle; }
  ul.signals li { color:#14532d; margin-bottom:6px; }
  .finding, .correction { border:1px solid #e2e8f0; border-radius:10px; padding:16px; margin-bottom:12px; }
  .finding-head, .correction-head { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
  .sev { color:#fff; font-size:11px; font-weight:700; padding:3px 9px; border-radius:999px; }
  .impact { margin-left:auto; color:#64748b; font-size:13px; }
  .priority { margin-left:auto; background:#eef2ff; color:#2563eb; font-size:12px; font-weight:700; padding:3px 10px; border-radius:999px; }
  .cat { color:#64748b; font-size:13px; margin-bottom:6px; }
  .why { color:#475569; font-size:14px; }
  .evidence { background:#0f172a; color:#e2e8f0; border-radius:6px; padding:10px; font-family:Menlo,Consolas,monospace; font-size:12px; margin-top:8px; }
  code { background:#0f172a; color:#e2e8f0; padding:1px 5px; border-radius:4px; font-size:12px; }
  .evidence code { background:transparent; padding:0; }
  @media print { body { padding:0; } .finding, .correction { break-inside:avoid; } }
</style>
</head>
<body>
  <h1>SCM Agent Validation Report</h1>
  <div class="meta">${esc(summary.agent_name)} · Run ${esc(summary.run_id)} · ${esc(new Date(summary.timestamp).toLocaleString())}</div>

  <div class="summary-grid">
    <div>
      <div class="score-big">${summary.overall_trust_score ?? "—"}</div>
      <div style="color:#64748b;font-size:13px">Overall Trust Score / 100</div>
    </div>
    <div class="pill">
      <span class="label">Demo Readiness</span>
      <span class="value" style="color:${readinessColor(summary.demo_readiness ?? "")}">${esc(summary.demo_readiness ?? "—")}</span>
    </div>
    <div class="pill">
      <span class="label">Production Readiness</span>
      <span class="value" style="color:${readinessColor(summary.production_readiness ?? "")}">${esc(summary.production_readiness ?? "—")}</span>
    </div>
    <div class="pill">
      <span class="label">Hygiene (static rules)</span>
      <span class="value">${summary.hygiene_score ?? "—"}/100</span>
    </div>
    <div class="pill">
      <span class="label">Behavior (executed scenarios)</span>
      <span class="value">${summary.behavior_score ?? "—"}/100</span>
    </div>
  </div>

  ${harnessSection}

  <section>
    <h2>Static Rule Breakdown (secondary signal)</h2>
    <table>
      <thead><tr><th>Dimension</th><th style="text-align:right">Score</th><th></th><th>Notes</th></tr></thead>
      <tbody>${breakdownRows}</tbody>
    </table>
  </section>

  <section>
    <h2>Positive Trust Signals (${result.positive_signals.length})</h2>
    ${signalItems ? `<ul class="signals">${signalItems}</ul>` : "<p>None detected.</p>"}
  </section>

  <section>
    <h2>Defects / Findings (${result.findings.length})</h2>
    ${findingCards || "<p>No findings.</p>"}
  </section>

  <section>
    <h2>Recommended Corrections (${result.recommendations.length})</h2>
    ${correctionCards || "<p>No corrections needed.</p>"}
  </section>

  ${insights}

  <footer style="margin-top:48px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;padding-top:16px">
    Generated by the SCM Agent Validation Platform. Trust score and findings are produced by a deterministic engine; the same input yields the same result.
  </footer>
</body>
</html>`;
}
