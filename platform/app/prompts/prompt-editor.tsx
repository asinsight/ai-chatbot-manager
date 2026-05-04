"use client";

import { useCallback, useMemo, useState } from "react";
import { GitCompare, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MonacoEditor } from "@/components/monaco-client";

import { lintPlaceholders, type LintIssue } from "./lint";
import { metaFor } from "./metadata";

type PromptKey = { name: string; value: string; size: number };
type PromptFile = "grok" | "system";

type Props = {
  file: PromptFile;
  initial: PromptKey;
  onSaved: () => Promise<void> | void;
};

export function PromptEditor({ file, initial, onSaved }: Props) {
  const [draft, setDraft] = useState<string>(initial.value);
  const [saving, setSaving] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);

  const dirty = draft !== initial.value;
  const lint = useMemo<LintIssue[]>(() => lintPlaceholders(draft), [draft]);
  const meta = metaFor(file, initial.name);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/prompts/${file}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ updates: { [initial.name]: draft } }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        backup_path?: string;
        warnings?: LintIssue[];
        error?: string;
      };
      if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
      const backupName = body.backup_path?.split("/").pop() ?? "(backup ok)";
      const warnCount = body.warnings?.length ?? 0;
      toast.success(`${initial.name} saved · restart required`, {
        description:
          `backup: ${backupName}` +
          (warnCount > 0 ? ` · ${warnCount} placeholder warning(s)` : ""),
        duration: 8000,
        action: {
          label: "Go to Dashboard",
          onClick: () => {
            window.location.href = "/dashboard";
          },
        },
      });
      setDiffOpen(false);
      await onSaved();
    } catch (err) {
      toast.error("Save failed", { description: (err as Error).message });
    } finally {
      setSaving(false);
    }
  }, [draft, file, initial.name, onSaved]);

  return (
    <div className="space-y-3">
      {meta && (
        <div className="rounded-md border border-border/60 bg-muted/30 p-3 text-xs">
          <p className="text-sm font-semibold text-foreground">{meta.title}</p>
          <p className="mt-1 text-muted-foreground">{meta.summary}</p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            <span className="font-semibold uppercase tracking-wider">Used by</span> · {meta.used_by}
          </p>
        </div>
      )}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-3">
          <span className="font-mono">
            {initial.name} · {draft.length.toLocaleString()} chars
          </span>
          {dirty && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700 dark:text-amber-400">
              ● dirty
            </span>
          )}
          {lint.length > 0 && (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700 dark:text-amber-400">
              {lint.length} warning{lint.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setDiffOpen(true)}
            disabled={!dirty}
          >
            <GitCompare /> Preview diff
          </Button>
          <Button size="sm" onClick={save} disabled={!dirty || saving}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />} Save
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border">
        <MonacoEditor
          height="65vh"
          defaultLanguage="markdown"
          value={draft}
          onChange={(v) => setDraft(v ?? "")}
          options={{
            wordWrap: "on",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            tabSize: 2,
          }}
        />
      </div>

      {lint.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
          <p className="mb-1 font-medium text-amber-700 dark:text-amber-400">
            Placeholder lint warnings (save still allowed):
          </p>
          <ul className="space-y-0.5 text-amber-700 dark:text-amber-400">
            {lint.map((l, idx) => (
              <li key={idx} className="font-mono">
                {l.line ? `L${l.line}: ` : ""}
                {l.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Diff — {initial.name}
            </DialogTitle>
            <DialogDescription>
              Disk version (left) vs. editor draft (right). Save will overwrite
              disk version and create a backup.
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-auto rounded border text-xs">
            <ReactDiffViewer
              oldValue={initial.value}
              newValue={draft}
              splitView={true}
              compareMethod={DiffMethod.LINES}
              styles={{
                contentText: { fontSize: "11px", lineHeight: "1.4" },
                gutter: { padding: "0 6px" },
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDiffOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={saving}>
              {saving ? <Loader2 className="animate-spin" /> : <Save />} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
