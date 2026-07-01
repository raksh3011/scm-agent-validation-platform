"use client";

import { downloadReport } from "../lib/api";

export default function DownloadReport({ runId }: { runId: string }) {
  return (
    <button className="btn" onClick={() => downloadReport(runId)}>
      Download PDF Report
    </button>
  );
}
