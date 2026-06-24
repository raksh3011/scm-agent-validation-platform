"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createRun } from "../../lib/api";

export default function NewValidationPage() {
  const router = useRouter();
  const [agentName, setAgentName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [useCase, setUseCase] = useState("");
  const [expectedIo, setExpectedIo] = useState("");
  const [description, setDescription] = useState("");
  const [enableLlm, setEnableLlm] = useState(false);
  const [files, setFiles] = useState<FileList | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  function validate(): string[] {
    const errs: string[] = [];
    if (!agentName.trim()) errs.push("Agent name is required.");
    if (!repoUrl.trim() && (!files || files.length === 0)) {
      errs.push("Provide a repository URL or upload at least one file / a ZIP of the project.");
    }
    if (!useCase.trim() && !description.trim()) {
      errs.push("Add a brief SCM use case or description so reviewers know what the agent is meant to do.");
    }
    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (errs.length > 0) return;

    setSubmitting(true);
    try {
      const form = new FormData();
      form.append("agent_name", agentName);
      if (repoUrl.trim()) form.append("repo_url", repoUrl.trim());
      if (useCase.trim()) form.append("use_case", useCase.trim());
      if (expectedIo.trim()) form.append("expected_io", expectedIo.trim());
      if (description.trim()) form.append("description", description.trim());
      form.append("enable_llm_insights", String(enableLlm));
      if (files) {
        Array.from(files).forEach((f) => form.append("files", f));
      }
      const res = await createRun(form);
      if (res.status === "failed") {
        setErrors([res.error || "Validation run failed to start."]);
        setSubmitting(false);
        return;
      }
      router.push(`/runs/${res.run_id}/progress`);
    } catch (err: unknown) {
      setErrors([err instanceof Error ? err.message : "Something went wrong."]);
      setSubmitting(false);
    }
  }

  return (
    <div className="shell">
      <h1>Submit an SCM Agent for Validation</h1>
      <p className="muted">
        Provide a repository, ZIP, or script files, plus a little context. The platform runs a deterministic
        validation and shows results directly in this app — no report file to download or open.
      </p>

      <form onSubmit={handleSubmit} className="card" style={{ maxWidth: 720, marginTop: 20 }}>
        {errors.length > 0 && (
          <div className="card" style={{ background: "#fef2f2", borderColor: "#fecaca", marginBottom: 18 }}>
            <strong style={{ color: "var(--critical)" }}>Missing or incomplete information:</strong>
            <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
              {errors.map((e, i) => (
                <li key={i} className="small">{e}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="field">
          <label>Agent name *</label>
          <input type="text" value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="e.g. Smart Reorder Agent" />
        </div>

        <div className="field">
          <label>Repository URL</label>
          <input type="url" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/org/agent-repo" />
        </div>

        <div className="field">
          <label>Or upload script / ZIP / files</label>
          <input type="file" multiple onChange={(e) => setFiles(e.target.files)} />
        </div>

        <div className="field">
          <label>SCM use case</label>
          <input type="text" value={useCase} onChange={(e) => setUseCase(e.target.value)} placeholder="e.g. Inventory reorder recommendation" />
        </div>

        <div className="field">
          <label>Expected input / output</label>
          <textarea rows={3} value={expectedIo} onChange={(e) => setExpectedIo(e.target.value)} placeholder="e.g. Input: SKU + sales history. Output: reorder quantity + reasoning." />
        </div>

        <div className="field">
          <label>Description</label>
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Brief description of what this agent does" />
        </div>

        <div className="field" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <input
            type="checkbox"
            id="llm"
            checked={enableLlm}
            onChange={(e) => setEnableLlm(e.target.checked)}
            style={{ width: "auto" }}
          />
          <label htmlFor="llm" style={{ margin: 0 }}>
            Enable optional AI insights (commentary only — does not affect the official trust score)
          </label>
        </div>

        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? "Submitting…" : "Run Validation"}
        </button>
      </form>
    </div>
  );
}
