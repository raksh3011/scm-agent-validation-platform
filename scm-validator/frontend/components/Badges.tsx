import { ReadinessLabel, ScenarioStatus, Severity } from "../lib/types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge ${severity}`}>{severity.toUpperCase()}</span>;
}

function readinessClass(value: string) {
  if (value === "Production Ready") return "ready-good";
  if (value === "Conditional") return "ready-warn";
  return "ready-bad";
}

export function ReadinessBadge({ value }: { value: ReadinessLabel | null }) {
  return (
    <div className="readiness-pill">
      <span className="readiness-label">Production</span>
      <span className={`readiness-value ${readinessClass(value ?? "")}`}>{value ?? "—"}</span>
    </div>
  );
}

const STATUS_COLOR: Record<ScenarioStatus, string> = {
  pass: "#dcfce7", fail: "#fee2e2", partial: "#fef3c7", error: "#e5e7eb", not_executed: "#e5e7eb",
};
const STATUS_TEXT: Record<ScenarioStatus, string> = {
  pass: "var(--success)", fail: "var(--critical)", partial: "#92400e", error: "#374151", not_executed: "#6b7280",
};

export function StatusBadge({ status }: { status: ScenarioStatus }) {
  return (
    <span className="badge" style={{ background: STATUS_COLOR[status], color: STATUS_TEXT[status] }}>
      {status.toUpperCase()}
    </span>
  );
}
