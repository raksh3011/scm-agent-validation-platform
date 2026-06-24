import { Severity, DemoReadiness, ProductionReadiness } from "../lib/types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge ${severity}`}>{severity}</span>;
}

function readinessClass(value: string) {
  if (value === "Demo Ready" || value === "Production Ready") return "ready-good";
  if (value === "Conditionally Ready" || value === "Requires Hardening") return "ready-warn";
  return "ready-bad";
}

export function DemoReadinessBadge({ value }: { value: DemoReadiness | null }) {
  return (
    <div className="readiness-pill">
      <span className="readiness-label">Demo</span>
      <span className={`readiness-value ${readinessClass(value ?? "")}`}>{value ?? "—"}</span>
    </div>
  );
}

export function ProductionReadinessBadge({ value }: { value: ProductionReadiness | null }) {
  return (
    <div className="readiness-pill">
      <span className="readiness-label">Production</span>
      <span className={`readiness-value ${readinessClass(value ?? "")}`}>{value ?? "—"}</span>
    </div>
  );
}
