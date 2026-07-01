"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AlertCircle, FileCheck2, ShieldCheck, UploadCloud, Workflow } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { CirceMark } from "../../components/CirceLogo";
import { useCreateRun } from "../../lib/queries";
import { cn } from "../../lib/utils";

const FEATURES = [
  { icon: ShieldCheck, label: "Deterministic", detail: "Same repo, same scenarios, every time" },
  { icon: Workflow, label: "Evidence-backed", detail: "Every score traces to a runtime observation" },
  { icon: FileCheck2, label: "Spec-driven", detail: "Validates against your ASD, not generic rules" },
];

function Dropzone({ id, label, hint, active, onChange }: {
  id: string; label: string; hint: string; active: boolean;
  onChange: (files: FileList | null) => void;
}) {
  const [dragging, setDragging] = useState(false);
  return (
    <label
      htmlFor={id}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        onChange(e.dataTransfer.files);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm transition-colors",
        dragging ? "border-primary bg-primary/5" : active ? "bg-accent/40" : "border-border hover:bg-accent/30"
      )}
      style={active && !dragging ? { borderColor: "#C4A06B" } : undefined}
    >
      <UploadCloud className={cn("h-5 w-5", active ? "text-primary" : "text-muted-foreground")} />
      <span className={cn("font-medium", active && "text-primary")}>{label}</span>
      <span className="text-xs text-muted-foreground">{hint}</span>
    </label>
  );
}

export default function NewValidationPage() {
  const router = useRouter();
  const createRun = useCreateRun();
  const [agentName, setAgentName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [useCase, setUseCase] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [asdFile, setAsdFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

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

    const form = new FormData();
    form.append("agent_name", agentName);
    if (repoUrl.trim()) form.append("repo_url", repoUrl.trim());
    if (useCase.trim()) form.append("use_case", useCase.trim());
    if (description.trim()) form.append("description", description.trim());
    if (files) Array.from(files).forEach((f) => form.append("files", f));
    if (asdFile) form.append("asd_file", asdFile);

    try {
      const res = await createRun.mutateAsync(form);
      router.push(`/runs/${res.run_id}/progress`);
    } catch (err) {
      setErrors([err instanceof Error ? err.message : "Something went wrong."]);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
        className="relative overflow-hidden rounded-2xl border border-border bg-card px-8 py-10 text-center"
      >
        <CirceMark className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 opacity-[0.06]" />
        <h1 className="relative text-3xl font-semibold tracking-tight">
          Validation Intelligence for <span style={{ color: "#C4A06B" }}>SCM AI Agents</span>
        </h1>
        <p className="relative mx-auto mt-3 max-w-lg text-sm text-muted-foreground">
          Provide a repository, ZIP, or script files, plus a little context. CirceAI classifies the agent,
          generates a deterministic scenario suite, executes it in a sandbox, and produces an evidence-backed
          trust score — no static linting pretending to be assurance.
        </p>
        <div className="relative mt-6 flex flex-wrap justify-center gap-3">
          {FEATURES.map((f) => (
            <div key={f.label} className="flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1.5 text-xs">
              <f.icon className="h-3.5 w-3.5 text-primary" />
              <span className="font-medium">{f.label}</span>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}>
        <Card className="mt-6 border-t-2 border-t-primary shadow-sm">
          <CardHeader>
            <CardTitle>Agent Details</CardTitle>
            <CardDescription>Currently fully supported agent types: Smart Reorder, Demand Forecasting.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-5">
              {errors.length > 0 && (
                <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <ul className="list-inside list-disc space-y-1">
                    {errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="agent_name">Agent name *</Label>
                <Input id="agent_name" value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="e.g. Smart Reorder Agent" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="repo_url">Repository URL</Label>
                <Input id="repo_url" type="url" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/org/agent-repo" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="files">Or upload script / ZIP / files</Label>
                <Dropzone
                  id="files"
                  label={files && files.length > 0 ? `${files.length} file(s) selected` : "Drag & drop, or click to choose files"}
                  hint=".py, .zip, or individual source files"
                  active={Boolean(files && files.length > 0)}
                  onChange={setFiles}
                />
                <input id="files" type="file" multiple className="hidden" onChange={(e) => setFiles(e.target.files)} />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="asd_file">Agent Specification Document (optional)</Label>
                <Dropzone
                  id="asd_file"
                  label={asdFile ? asdFile.name : "Drag & drop, or click to choose a spec"}
                  hint=".md, .docx, .pdf, .yaml, or .json"
                  active={Boolean(asdFile)}
                  onChange={(fl) => setAsdFile(fl?.[0] ?? null)}
                />
                <input
                  id="asd_file"
                  type="file"
                  accept=".md,.docx,.pdf,.yaml,.yml,.json,.txt"
                  className="hidden"
                  onChange={(e) => setAsdFile(e.target.files?.[0] ?? null)}
                />
                <p className="text-xs text-muted-foreground">
                  Uploading a specification turns this run into a contract-based validation: the platform checks
                  requirement, functional, input/output, constraint, integration, KPI, and decision coverage against
                  the document, in addition to inferred repository capabilities.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="use_case">SCM use case</Label>
                <Input id="use_case" value={useCase} onChange={(e) => setUseCase(e.target.value)} placeholder="e.g. Inventory reorder recommendation" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="description">Description</Label>
                <Textarea id="description" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Brief description of what this agent does" />
              </div>

              <Button type="submit" className="w-full" disabled={createRun.isPending}>
                {createRun.isPending ? "Submitting…" : "Run Validation"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
