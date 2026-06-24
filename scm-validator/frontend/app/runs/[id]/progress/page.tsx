"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getRunStatus } from "../../../../lib/api";

const STEPS = ["queued", "running", "completed"];

export default function ProgressPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [status, setStatus] = useState<string>("queued");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const res = await getRunStatus(params.id);
        if (cancelled) return;
        setStatus(res.status);
        if (res.status === "completed") {
          router.push(`/runs/${params.id}/results`);
          return;
        }
        if (res.status === "failed") {
          setError(res.error || "Validation failed.");
          return;
        }
        timer = setTimeout(poll, 1200);
      } catch {
        if (!cancelled) timer = setTimeout(poll, 1500);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [params.id, router]);

  const stepIndex = STEPS.indexOf(status);

  return (
    <div className="shell">
      <h1>Running Validation</h1>
      <div className="card" style={{ maxWidth: 600, marginTop: 20 }}>
        {error ? (
          <>
            <p style={{ color: "var(--critical)", fontWeight: 600 }}>Validation failed</p>
            <p className="small muted">{error}</p>
          </>
        ) : (
          <>
            <ol style={{ paddingLeft: 20 }}>
              {["Queued", "Ingesting & analyzing repository", "Finalizing results"].map((label, i) => (
                <li
                  key={label}
                  style={{
                    marginBottom: 12,
                    fontWeight: i === stepIndex ? 700 : 400,
                    color: i <= stepIndex ? "var(--text)" : "var(--text-muted)",
                  }}
                >
                  {label}
                  {i === stepIndex ? " …" : i < stepIndex ? " ✓" : ""}
                </li>
              ))}
            </ol>
            <p className="small muted">Run ID: {params.id}</p>
          </>
        )}
      </div>
    </div>
  );
}
