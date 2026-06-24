"use client";

import { useState } from "react";
import { ValidationResult } from "../lib/types";
import { buildReportHtml } from "../lib/report";

export default function DownloadReport({ runId, result }: { runId: string; result: ValidationResult }) {
  const [open, setOpen] = useState(false);

  function downloadBlob(filename: string, content: string, type: string) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setOpen(false);
  }

  function downloadJson() {
    downloadBlob(`scm-validation-${runId}.json`, JSON.stringify(result, null, 2), "application/json");
  }

  function downloadHtml() {
    // Same validation data the dashboard renders -> self-contained report document.
    downloadBlob(`scm-validation-${runId}.html`, buildReportHtml(result), "text/html");
  }

  return (
    <div style={{ position: "relative" }}>
      <button className="btn" onClick={() => setOpen((o) => !o)}>
        Download Report ▾
      </button>
      {open && (
        <div
          className="card"
          style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 20, padding: 8, minWidth: 220 }}
        >
          <button className="btn secondary" style={{ width: "100%", marginBottom: 6, justifyContent: "flex-start" }} onClick={downloadJson}>
            Download JSON
          </button>
          <button className="btn secondary" style={{ width: "100%", justifyContent: "flex-start" }} onClick={downloadHtml}>
            Download Report (HTML)
          </button>
          <p className="small muted" style={{ margin: "8px 4px 2px" }}>
            HTML opens in any browser and prints to PDF.
          </p>
        </div>
      )}
    </div>
  );
}
