"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getRunResults } from "../../../../lib/api";
import { Evidence, Finding, Severity, ValidationResult } from "../../../../lib/types";
import ScoreBar from "../../../../components/ScoreBar";
import { SeverityBadge, DemoReadinessBadge, ProductionReadinessBadge } from "../../../../components/Badges";
import DownloadReport from "../../../../components/DownloadReport";

type Tab = "overview" | "signals" | "defects" | "corrections" | "evidence" | "insights";

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

  const evidenceById = new Map(result.evidence.map((e) => [e.id, e]));

  return (
    <div className="shell">
      <SummaryHeader result={result} />

      <div className="tabs">
        <TabBtn tab="overview" active={tab} onClick={setTab} label="Overview" />
        <TabBtn tab="signals" active={tab} onClick={setTab} label={`Positive Signals (${result.positive_signals.length})`} />
        <TabBtn tab="defects" active={tab} onClick={setTab} label={`Defects (${result.findings.length})`} />
        <TabBtn tab="corrections" active={tab} onClick={setTab} label={`Corrections (${result.recommendations.length})`} />
        <TabBtn tab="evidence" active={tab} onClick={setTab} label={`Evidence (${result.evidence.length})`} />
        <TabBtn tab="insights" active={tab} onClick={setTab} label="AI Insights" />
      </div>

      {tab === "overview" && <Overview result={result} />}
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
              {summary.overall_trust_score}
            </div>
            <div className="small muted">Trust Score / 100</div>
          </div>
          <DownloadReport runId={summary.run_id} result={result} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
        <DemoReadinessBadge value={summary.demo_readiness} />
        <ProductionReadinessBadge value={summary.production_readiness} />
      </div>
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
