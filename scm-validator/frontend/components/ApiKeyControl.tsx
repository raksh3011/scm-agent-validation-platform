"use client";

import { useEffect, useState } from "react";
import { KeyRound, Check, Copy } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { ensureApiKey, setStoredApiKey } from "../lib/apiKey";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8008";

export default function ApiKeyControl() {
  const [key, setKey] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    ensureApiKey(API_BASE).then(setKey);
  }, []);

  if (!key) return null;

  function copy() {
    navigator.clipboard.writeText(key!);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function useDraftKey() {
    if (!draft.trim()) return;
    setStoredApiKey(draft.trim());
    window.location.reload();
  }

  return (
    <div className="relative">
      <Button variant="ghost" size="icon" onClick={() => setOpen((o) => !o)} aria-label="Access key">
        <KeyRound className="h-4 w-4" />
      </Button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-md border border-border bg-popover p-4 text-sm shadow-lg">
          <p className="font-medium">Your access key</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Runs and history are private to this key. Save it to see the same history on another device.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-muted px-2 py-1 text-xs">{key}</code>
            <Button variant="ghost" size="icon" onClick={copy} aria-label="Copy key">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Have a key from another device? Paste it here:</p>
          <div className="mt-1 flex items-center gap-2">
            <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Paste access key" className="text-xs" />
            <Button size="sm" onClick={useDraftKey}>Use</Button>
          </div>
        </div>
      )}
    </div>
  );
}
