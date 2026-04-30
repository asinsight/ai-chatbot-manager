"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function WorkflowReplace({
  name,
  onSaved,
}: {
  name: string;
  onSaved: () => Promise<void> | void;
}) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  const parsed = useMemo(() => {
    if (text.trim() === "") return { ok: false, error: "(empty — paste a workflow JSON)", content: null };
    try {
      const v = JSON.parse(text) as object;
      return { ok: true, error: null, content: v };
    } catch (err) {
      return { ok: false, error: (err as Error).message, content: null };
    }
  }, [text]);

  const submit = async () => {
    if (!parsed.ok || parsed.content === null) return;
    setSaving(true);
    try {
      const r = await fetch(`/api/workflows/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "replace", content: parsed.content }),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Replace failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Replaced · restart bot to load");
      setText("");
      await onSaved?.();
    } catch (err) {
      toast.error(`Replace failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3 rounded-md border p-4">
      <p className="text-xs text-muted-foreground">
        Paste a workflow JSON exported from ComfyUI&apos;s &ldquo;Save (API
        Format)&rdquo;. The Positive node&apos;s <code className="font-mono">text</code> must contain{" "}
        <code className="font-mono">%prompt%</code> and the Negative node&apos;s must contain{" "}
        <code className="font-mono">%negative_prompt%</code>; otherwise Replace
        is rejected with <code className="font-mono">PLACEHOLDER_MISSING</code>.
      </p>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={14}
        placeholder="Paste workflow JSON here…"
        className="font-mono text-xs"
      />
      <div className="flex items-center justify-between text-xs">
        <span className={parsed.ok ? "text-green-700" : "text-amber-700"}>
          {parsed.ok ? "Parse OK" : `Parse error: ${parsed.error}`}
        </span>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="sm" disabled={!parsed.ok || saving}>
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Validate & Replace"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Replace {name}?</AlertDialogTitle>
              <AlertDialogDescription>
                This overwrites the entire workflow file. The previous version is
                saved automatically as a <code className="font-mono">.bak</code>.
                The bot still needs a restart to pick up the change.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void submit()}>Replace</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
