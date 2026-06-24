"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getRunResults } from "../../../../lib/api";
import { Evidence, Finding, InvariantResult, ScenarioResult, Severity, ValidationResult } from "../../../../lib/types";
import ScoreBar from "../../../../components/ScoreBar";
import { SeverityBadge, DemoReadinessBadge, ProductionReadinessBadge } from "../../../../components/Badges";
import DownloadReport from "../../../../components/DownloadReport";

type Tab = "overview" | "harness" | "signals" | "defects" | "corrections" | "evidence" | "insights";

const ADAPTER_STATUS_LABEL: Record<string, string> = {
  loaded: "Submitted adapter loaded",
  auto_generated: "Adapter auto-generated from detected entrypoint",
  failed: "No agent could be executed",
  not_attempted: "Not attempted",
};

const SEVERITY_ORDER: Severity[] = ["Critical", "High", "Medium", "Low"];

export default function ResultsPage() {
  const params = useParams<{ id: string }>();
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    getRunResults(params.id)
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load results"));
  }, [params.id]);

  if (error) {
    return (
      <div className="shell">
        <div className="card" style={{ background: "#fef2f2", borderColor: "#fecaca" }}>{error}</div>
      </div>
    );
  }
  if (!result) {
    return (
      <div className="shell">
        <p className="muted">Loading results…</p>
      </div>
    );
  }

  if (!result.summary.applicable) {
    return (
      <div className="shell">
        <div className="card" style={{ background: "#fffbeb", borderColor: "#fde68a" }}>
          <h2 style={{ marginTop: 0 }}>Not Applicable</h2>
          <p>
            This submission was not scored. {result.summary.not_applicable_reason}
          </p>
          <p className="muted small">
            The platform only scores submissions that look like a real SCM decision agent.
            A score of 0 would wrongly imply a real agent was evaluated and failed — this
            submission was never evaluated at all.
          </p>
        </div>
      </div>
    );
  }

  const evidenceById = new Map(result.evidence.map((e) => [e.id, e]));

  return (
    <div className="shell">
      <SummaryHeader result={result} />

      <div className="tabs">
        <TabBtn tab="overview" active={tab} onClick={setTab} label="Overview" />
        <TabBtn
          tab="harness"
          active={tab}
          onClick={setTab}
          label={`Trust Harness (${result.invariant_results.filter((r) => r.passed).length + result.scenario_results.filter((r) => r.passed).length}/${result.invariant_results.length + result.scenario_results.length})`}
        />
        <TabBtn tab="signals" active={tab} onClick={setTab} label={`Positive Signals (${result.positive_signals.length})`} />
        <TabBtn tab="defects" active={tab} onClick={setTab} label={`Defects (${result.findings.length})`} />
        <TabBtn tab="corrections" active={tab} onClick={setTab} label={`Corrections (${result.recommendations.length})`} />
        <TabBtn tab="evidence" active={tab} onClick={setTab} label={`Evidence (${result.evidence.length})`} />
        <TabBtn tab="insights" active={tab} onClick={setTab} label="AI Insights" />
      </div>

      {tab === "overview" && <Overview result={result} />}
      {tab === "harness" && <TrustHarness result={result} />}
      {tab === "signals" && <PositiveSignals signals={result.positive_signals} />}
      {tab === "defects" && <Defects findings={result.findings} evidenceById={evidenceById} />}
      {tab === "corrections" && <Corrections result={result} />}
      {tab === "evidence" && <EvidenceExplorer evidence={result.evidence} />}
      {tab === "insights" && <Insights insights={result.ai_insights} />}
    </div>
  );
}

function TabBtn({ tab, active, onClick, label }: { tab: Tab; active: Tab; onClick: (t: Tab) => void; label: string }) {
  return (
    <button className={`tab-btn ${active === tab ? "active" : ""}`} onClick={() => onClick(tab)}>
      {label}
    </button>
  );
}

function SummaryHeader({ result }: { result: ValidationResult }) {
  const { summary } = result;
  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 style={{ margin: 0 }}>{summary.agent_name}</h1>
          <p className="small muted" style={{ margin: "6px 0 0" }}>
            Run {summary.run_id} · {new Date(summary.timestamp).toLocaleString()}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 44, fontWeight: 800, color: "var(--primary)", lineHeight: 1 }}>
              {summary.overall_trust_score ?? "—"}
            </div>
            <div className="small muted">Trust Score / 100</div>
          </div>
          <DownloadReport runId={summary.run_id} result={result} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap", alignItems: "center" }}>
        <DemoReadinessBadge value={summary.demo_readiness} />
        <ProductionReadinessBadge value={summary.production_readiness} />
      </div>

      {(summary.hygiene_score != null || summary.behavior_score != null) && (
        <div className="grid-2" style={{ marginTop: 16 }}>
          <div className="card" style={{ background: "#f8fafc" }}>
            <div className="small muted" style={{ marginBottom: 4 }}>Hygiene score — static code rules (secondary signal)</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.hygiene_score ?? "—"}<span className="small muted">/100</span></div>
          </div>
          <div className="card" style={{ background: "#f8fafc" }}>
            <div className="small muted" style={{ marginBottom: 4 }}>Behavior score — executed SCM decisions (dominant signal, 75% of overall)</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.behavior_score ?? "—"}<span className="small muted">/100</span></div>
          </div>
        </div>
      )}

      {result.adapter_status === "failed" && (
        <div className="card" style={{ background: "#fef2f2", borderColor: "#fecaca", marginTop: 16 }}>
          <strong style={{ color: "var(--critical)" }}>No agent could be executed</strong>
          <p className="small" style={{ margin: "6px 0 0" }}>
            The platform could not find or run a decision function for this submission, so the trust score is
            forced to 0 regardless of how clean the static code looks — a clean hygiene score with no behavior
            evidence is not a trustworthy agent. See the Trust Harness tab for details, or add a{" "}
            <code>scm_adapter.py</code> exposing <code>run_decision(scenario)</code> at the repository root.
          </p>
        </div>
      )}
    </div>
  );
}

function Overview({ result }: { result: ValidationResult }) {
  const topFindings = [...result.findings]
    .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
    .slice(0, 4);
  const topFixes = result.recommendations.slice(0, 4);

  return (
    <>
      <h3>Trust Score Breakdown</h3>
      <div className="grid-3" style={{ marginBottom: 28 }}>
        {result.score_breakdown.map((item) => (
          <div className="card" key={item.dimension}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <strong className="small">{item.dimension}</strong>
              <span className="small muted">{item.score}/{item.max_score}</span>
            </div>
            <ScoreBar score={item.score} max={item.max_score} />
            <p className="small muted" style={{ marginTop: 8 }}>{item.remarks}</p>
          </div>
        ))}
      </div>

      <div className="grid-3" style={{ marginBottom: 28 }}>
        <div className="card" style={{ gridColumn: "span 1" }}>
          <h3 style={{ marginTop: 0 }}>What this agent does well</h3>
          {result.positive_signals.length === 0 && <p className="small muted">No positive signals detected.</p>}
          {result.positive_signals.slice(0, 5).map((sig, i) => (
            <div className="signal-chip" key={i} style={{ marginBottom: 8 }}>
              <span className="check">✓</span>
              <span>{sig}</span>
            </div>
          ))}
          {result.positive_signals.length > 5 && (
            <p className="small muted" style={{ marginTop: 8 }}>+{result.positive_signals.length - 5} more in Positive Signals tab</p>
          )}
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Top Issues</h3>
          {topFindings.length === 0 && <p className="small muted">No issues found.</p>}
          {topFindings.map((f) => (
            <div key={f.id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                <SeverityBadge severity={f.severity} />
                <strong className="small">{f.title}</strong>
              </div>
              <p className="small muted" style={{ margin: 0 }}>{f.category}</p>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Top Fixes</h3>
          {topFixes.length === 0 && <p className="small muted">No fixes needed.</p>}
          {topFixes.map((r) => (
            <div key={r.id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
              <strong className="small">{r.title}</strong>
              <p className="small muted" style={{ margin: "4px 0 0" }}>{r.recommendation}</p>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function PassFailBadge({ passed }: { passed: boolean }) {
  return (
    <span
      className="badge"
      style={{ background: passed ? "#dcfce7" : "#fee2e2", color: passed ? "var(--success)" : "var(--critical)" }}
    >
      {passed ? "PASS" : "FAIL"}
    </span>
  );
}

function TrustHarness({ result }: { result: ValidationResult }) {
  const invariants = result.invariant_results;
  const scenarios = result.scenario_results;
  const requiredScenarios = scenarios.filter((s) => s.tier === "required");
  const recommendedScenarios = scenarios.filter((s) => s.tier === "recommended");

  return (
    <div>
      <div className="card" style={{ marginBottom: 20 }}>
        <strong>Adapter status: {ADAPTER_STATUS_LABEL[result.adapter_status] ?? result.adapter_status}</strong>
        <p className="small muted" style={{ margin: "6px 0 0" }}>
          {result.adapter_status === "loaded" &&
            "This submission provided its own scm_adapter.py, which the harness called directly."}
          {result.adapter_status === "auto_generated" &&
            "No scm_adapter.py was found, so the platform detected the most likely decision function and " +
            "auto-generated a best-effort bridge to call it. Review the detected mapping if results look off."}
          {result.adapter_status === "failed" &&
            "Neither a submitted adapter nor a confident auto-detected entrypoint could be executed. " +
            "Behavior score is 0 and the overall trust score is forced to 0."}
        </p>
      </div>

      <h3>Invariant Tests ({invariants.filter((i) => i.passed).length}/{invariants.length} passed)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Each test runs the agent's actual decision function against systematically varied scenarios and checks
        a relationship every correct SCM agent must satisfy (e.g. reorder point must rise with lead time, a
        worse-on-every-axis supplier must never be chosen).
      </p>
      <div style={{ marginBottom: 28 }}>
        {invariants.length === 0 && <p className="muted small">No invariant tests ran for this submission.</p>}
        {invariants.map((inv) => <InvariantCard key={inv.test_id} inv={inv} />)}
      </div>

      <h3>Golden Scenarios — Required ({requiredScenarios.filter((s) => s.passed).length}/{requiredScenarios.length} passed)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Hand-verified scenarios with known-correct expected decisions (reorder math, HOLD vs REORDER, supplier
        eligibility by SKU, Pareto dominance, degenerate inputs). A single failure here caps the behavior score
        at 40, regardless of how many other scenarios pass.
      </p>
      <div style={{ marginBottom: 28 }}>
        {requiredScenarios.map((sc) => <ScenarioCard key={sc.scenario_id} sc={sc} />)}
      </div>

      {recommendedScenarios.length > 0 && (
        <>
          <h3>Golden Scenarios — Recommended ({recommendedScenarios.filter((s) => s.passed).length}/{recommendedScenarios.length} passed)</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Good practice, not a hard blocker — e.g. respecting a supplier's minimum order quantity.
          </p>
          <div>
            {recommendedScenarios.map((sc) => <ScenarioCard key={sc.scenario_id} sc={sc} />)}
          </div>
        </>
      )}
    </div>
  );
}

function InvariantCard({ inv }: { inv: InvariantResult }) {
  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <strong className="small">{inv.test_id}</strong>
        <PassFailBadge passed={inv.passed} />
      </div>
      <p className="small muted" style={{ margin: 0 }}>{inv.detail}</p>
    </div>
  );
}

function ScenarioCard({ sc }: { sc: ScenarioResult }) {
  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <strong className="small">{sc.scenario_id} — {sc.description}</strong>
        <PassFailBadge passed={sc.passed} />
      </div>
      <p className="small muted" style={{ margin: "0 0 6px" }}>{sc.detail}</p>
      {!sc.passed && (
        <div className="small" style={{ display: "flex", gap: 16 }}>
          <div><strong>Expected:</strong> <code>{JSON.stringify(sc.expected)}</code></div>
          <div><strong>Actual:</strong> <code>{JSON.stringify(sc.actual)}</code></div>
        </div>
      )}
    </div>
  );
}

function PositiveSignals({ signals }: { signals: string[] }) {
  if (signals.length === 0) {
    return <p className="muted">No positive trust signals were detected for this agent.</p>;
  }
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>
        Deterministic patterns that increase trust in this agent. These are detected from code structure,
        not subjective judgment.
      </p>
      <div className="grid-2">
        {signals.map((sig, i) => (
          <div className="signal-chip" key={i}>
            <span className="check">✓</span>
            <span>{sig}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Defects({ findings, evidenceById }: { findings: Finding[]; evidenceById: Map<string, Evidence> }) {
  const [severityFilter, setSeverityFilter] = useState<string>("All");
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const categories = useMemo(() => Array.from(new Set(findings.map((f) => f.category))), [findings]);

  const filtered = findings.filter(
    (f) => (severityFilter === "All" || f.severity === severityFilter) && (categoryFilter === "All" || f.category === categoryFilter)
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <div style={{ width: 200 }}>
          <label>Severity</label>
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
            <option>All</option>
            {SEVERITY_ORDER.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div style={{ width: 280 }}>
          <label>Category</label>
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option>All</option>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {filtered.length === 0 && <p className="muted">No findings match the current filters.</p>}

      {filtered.map((f) => (
        <div className="card" key={f.id} style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <SeverityBadge severity={f.severity} />
                <span className="small muted">{f.category}</span>
              </div>
              <h3 style={{ margin: "0 0 8px" }}>{f.title}</h3>
            </div>
            <span className="small muted">-{f.score_impact} pts</span>
          </div>
          <p style={{ margin: "0 0 6px" }}>{f.description}</p>
          <p className="small muted" style={{ margin: "0 0 10px" }}><strong>Why it matters:</strong> {f.why_it_matters}</p>
          {f.evidence_refs.length > 0 && (
            <div className="small">
              <strong>Evidence:</strong>{" "}
              {f.evidence_refs.map((id) => {
                const ev = evidenceById.get(id);
                if (!ev) return null;
                return (
                  <code key={id} style={{ marginRight: 6 }}>
                    {ev.file_path}{ev.line_start ? `:${ev.line_start}` : ""}
                  </code>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Corrections({ result }: { result: ValidationResult }) {
  const [priorityFilter, setPriorityFilter] = useState<string>("All");
  const priorities = useMemo(() => Array.from(new Set(result.recommendations.map((r) => r.priority))), [result]);
  const findingById = new Map(result.findings.map((f) => [f.id, f]));

  const filtered = result.recommendations.filter((r) => priorityFilter === "All" || r.priority === priorityFilter);

  return (
    <div>
      <div style={{ width: 200, marginBottom: 16 }}>
        <label>Priority</label>
        <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
          <option>All</option>
          {priorities.map((p) => <option key={p}>{p}</option>)}
        </select>
      </div>

      {filtered.map((r) => {
        const finding = findingById.get(r.finding_id);
        return (
          <div className="card" key={r.id} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <h3 style={{ margin: 0 }}>{r.title}</h3>
              <span className="badge" style={{ background: "#eef2ff", color: "var(--primary)" }}>{r.priority}</span>
            </div>
            {finding && <p className="small muted" style={{ margin: "0 0 8px" }}>Fixes: {finding.title}</p>}
            <p style={{ margin: "0 0 8px" }}>{r.recommendation}</p>
            <p className="small muted" style={{ margin: 0 }}>{r.expected_impact}</p>
          </div>
        );
      })}
    </div>
  );
}

function EvidenceExplorer({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) return <p className="muted">No evidence recorded for this run.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>Line</th>
          <th>Snippet</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        {evidence.map((e) => (
          <tr key={e.id}>
            <td><code>{e.file_path}</code></td>
            <td>{e.line_start || "—"}</td>
            <td>{e.snippet ? <code>{e.snippet}</code> : <span className="muted">—</span>}</td>
            <td className="small">{e.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Insights({ insights }: { insights: string[] }) {
  if (insights.length === 0) {
    return (
      <p className="muted">
        No AI insights for this run. AI insights are optional and only generated when explicitly enabled at
        submission — they never affect the official trust score.
      </p>
    );
  }
  return (
    <div className="card">
      <ul>
        {insights.map((insight, i) => (
          <li key={i} style={{ marginBottom: 10 }}>{insight}</li>
        ))}
      </ul>
    </div>
  );
}
