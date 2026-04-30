"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { SafeFields } from "@/lib/workflows-meta";

export function WorkflowForm({
  name,
  initial,
  onSaved,
}: {
  name: string;
  initial: SafeFields;
  onSaved: () => Promise<void> | void;
}) {
  const [draft, setDraft] = useState<SafeFields>(initial);
  const [saving, setSaving] = useState(false);

  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/workflows/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "safe_fields", fields: draft }),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Save failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Saved · restart bot to load");
      await onSaved?.();
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="space-y-1">
        <Label className="text-xs">Checkpoint (CheckpointLoaderSimple.ckpt_name)</Label>
        <Input
          value={draft.checkpoint ?? ""}
          onChange={(e) => setDraft({ ...draft, checkpoint: e.target.value })}
          className="font-mono text-xs"
          placeholder="(node not present)"
          disabled={draft.checkpoint === null && initial.checkpoint === null}
        />
      </div>

      {draft.ksampler ? (
        <div className="space-y-2">
          <Label className="text-xs">KSampler</Label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">seed</div>
              <Input
                type="number"
                value={draft.ksampler.seed}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    ksampler: { ...draft.ksampler!, seed: Number(e.target.value) },
                  })
                }
                className="font-mono text-xs"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">cfg</div>
              <Input
                type="number"
                step="0.1"
                value={draft.ksampler.cfg}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    ksampler: { ...draft.ksampler!, cfg: Number(e.target.value) },
                  })
                }
                className="font-mono text-xs"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">steps</div>
              <Input
                type="number"
                value={draft.ksampler.steps}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    ksampler: { ...draft.ksampler!, steps: Number(e.target.value) },
                  })
                }
                className="font-mono text-xs"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">sampler_name</div>
              <Input
                value={draft.ksampler.sampler_name}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    ksampler: { ...draft.ksampler!, sampler_name: e.target.value },
                  })
                }
                className="font-mono text-xs"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">scheduler</div>
              <Input
                value={draft.ksampler.scheduler}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    ksampler: { ...draft.ksampler!, scheduler: e.target.value },
                  })
                }
                className="font-mono text-xs"
              />
            </div>
          </div>
        </div>
      ) : (
        <p className="text-xs italic text-muted-foreground">No KSampler node — fields hidden.</p>
      )}

      <div className="space-y-1">
        <Label className="text-xs">SaveImage filename prefix</Label>
        <Input
          value={draft.save_filename_prefix ?? ""}
          onChange={(e) => setDraft({ ...draft, save_filename_prefix: e.target.value })}
          className="font-mono text-xs"
          placeholder="(node not present)"
          disabled={draft.save_filename_prefix === null && initial.save_filename_prefix === null}
        />
      </div>

      <div className="flex items-center justify-end gap-2">
        {dirty && <span className="text-xs text-amber-600">● unsaved</span>}
        <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save form fields"}
        </Button>
      </div>
    </div>
  );
}
