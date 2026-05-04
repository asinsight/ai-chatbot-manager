"use client";

import { useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { SafeFields } from "@/lib/workflows-meta";

type CheckpointsResp =
  | { ok: true; comfyui_url: string; checkpoints: string[] }
  | { ok: false; reason: string; message: string; checkpoints: string[] };

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
  const [checkpoints, setCheckpoints] = useState<string[]>([]);
  const [ckptLoading, setCkptLoading] = useState(false);
  const [ckptError, setCkptError] = useState<string | null>(null);

  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const loadCheckpoints = async () => {
    setCkptLoading(true);
    setCkptError(null);
    try {
      const r = await fetch("/api/comfyui/checkpoints", { cache: "no-store" });
      const body = (await r.json()) as CheckpointsResp;
      if (body.ok) {
        setCheckpoints(body.checkpoints);
      } else {
        setCheckpoints([]);
        setCkptError(`${body.reason}: ${body.message}`);
      }
    } catch (err) {
      setCkptError((err as Error).message);
    } finally {
      setCkptLoading(false);
    }
  };

  useEffect(() => {
    void loadCheckpoints();
  }, []);

  // Make sure the current value is selectable even if ComfyUI hasn't returned
  // the list yet (or doesn't include it — different server, file renamed, etc).
  const checkpointOptions = (() => {
    const cur = draft.checkpoint;
    const set = new Set(checkpoints);
    if (cur && !set.has(cur)) set.add(cur);
    return Array.from(set).sort();
  })();

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
        <div className="flex items-center justify-between">
          <Label className="text-xs">Checkpoint (CheckpointLoaderSimple.ckpt_name)</Label>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={ckptLoading}
            onClick={() => void loadCheckpoints()}
            title="Refresh checkpoint list from ComfyUI"
          >
            {ckptLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
          </Button>
        </div>
        {draft.checkpoint === null && initial.checkpoint === null ? (
          <Input
            value=""
            placeholder="(node not present)"
            disabled
            className="font-mono text-xs"
          />
        ) : checkpointOptions.length > 0 ? (
          <Select
            value={draft.checkpoint ?? ""}
            onValueChange={(v) => setDraft({ ...draft, checkpoint: v })}
          >
            <SelectTrigger className="font-mono text-xs">
              <SelectValue placeholder="Choose a checkpoint…" />
            </SelectTrigger>
            <SelectContent>
              {checkpointOptions.map((opt) => (
                <SelectItem key={opt} value={opt} className="font-mono text-xs">
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            value={draft.checkpoint ?? ""}
            onChange={(e) => setDraft({ ...draft, checkpoint: e.target.value })}
            className="font-mono text-xs"
            placeholder="e.g. illustrious/oneObsession_v20Bold.safetensors"
          />
        )}
        {ckptError && (
          <p className="text-[10px] text-amber-600">
            ComfyUI checkpoint list unavailable ({ckptError}). Falling back to
            free-text input — make sure the path matches a file on the ComfyUI
            server.
          </p>
        )}
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
