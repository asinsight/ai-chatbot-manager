"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Assignments = {
  standard: string;
  hq: string;
  options: string[];
};

export function StageAssignments({ onChanged }: { onChanged?: () => void }) {
  const [data, setData] = useState<Assignments | null>(null);
  const [draft, setDraft] = useState<{ standard: string; hq: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/workflows/assignments", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as Assignments;
      setData(body);
      setDraft({ standard: body.standard, hq: body.hq });
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-destructive">Stage assignments load failed: {error}</p>;
  }
  if (!data || !draft) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading stage assignments…
      </div>
    );
  }

  const dirty = draft.standard !== data.standard || draft.hq !== data.hq;

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch("/api/workflows/assignments", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Save failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Saved · restart bot to load");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stage assignments</CardTitle>
        <CardDescription>
          Pick which workflow JSON backs each rendering stage. Standard fires for{" "}
          <code className="font-mono">/random</code> SFW + chat image-gen. HQ fires
          when a user has toggled <code className="font-mono">/hq on</code>. Saved
          via <code className="font-mono">.env</code> (
          <code className="font-mono">COMFYUI_WORKFLOW</code> +{" "}
          <code className="font-mono">COMFYUI_WORKFLOW_HQ</code>); bot restart
          required.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-xs">Standard stage</Label>
            <Select
              value={draft.standard}
              onValueChange={(v) => setDraft({ ...draft, standard: v })}
            >
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.options.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">HQ stage</Label>
            <Select
              value={draft.hq}
              onValueChange={(v) => setDraft({ ...draft, hq: v })}
            >
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.options.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2">
          {dirty && <span className="text-xs text-amber-600">● unsaved</span>}
          <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save assignments"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
