"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import type { SafeFields, WorkflowFacts } from "@/lib/workflows-meta";

import { StageBadges, WorkflowFactsBlock } from "./workflow-facts";
import { WorkflowForm } from "./workflow-form";
import { WorkflowRaw } from "./workflow-raw";
import { WorkflowReplace } from "./workflow-replace";

type DetailResp = {
  name: string;
  content: object;
  mtime_ms: number;
  size_bytes: number;
  facts: WorkflowFacts;
  safe_fields: SafeFields;
};

export function WorkflowTab({
  name,
  stageBadges,
  description: initialDescription,
  onChanged,
}: {
  name: string;
  stageBadges: ("standard" | "hq")[];
  description: string;
  onChanged: () => Promise<void> | void;
}) {
  const [data, setData] = useState<DetailResp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [description, setDescription] = useState<string>(initialDescription);
  const [savedDescription, setSavedDescription] = useState<string>(initialDescription);
  const [savingDesc, setSavingDesc] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/workflows/${encodeURIComponent(name)}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as DetailResp;
      setData(body);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [name]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setDescription(initialDescription);
    setSavedDescription(initialDescription);
  }, [initialDescription, name]);

  const saveDescription = async () => {
    setSavingDesc(true);
    try {
      const r = await fetch("/api/workflows/descriptions", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: name, description }),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Save failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Description saved");
      setSavedDescription(description);
      await onChanged();
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSavingDesc(false);
    }
  };

  if (error) {
    return <p className="text-sm text-destructive">Load failed: {error}</p>;
  }
  if (!data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading workflow…
      </div>
    );
  }

  const descDirty = description !== savedDescription;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <code className="font-mono text-sm font-semibold">{name}</code>
          <p className="text-xs text-muted-foreground">
            comfyui_workflow/{name}
          </p>
        </div>
        <StageBadges stages={stageBadges} />
      </div>

      <WorkflowFactsBlock facts={data.facts} />

      <div className="space-y-2 rounded-md border p-3">
        <Label className="text-xs">Description</Label>
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="text-xs"
          placeholder="Free-form description shown alongside this workflow on the admin /workflows page."
        />
        <div className="flex items-center justify-end gap-2">
          {descDirty && <span className="text-xs text-amber-600">● unsaved</span>}
          <Button size="sm" disabled={!descDirty || savingDesc} onClick={() => void saveDescription()}>
            {savingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save description"}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="form">
        <TabsList>
          <TabsTrigger value="form">Form</TabsTrigger>
          <TabsTrigger value="raw">Raw JSON</TabsTrigger>
          <TabsTrigger value="replace">Replace</TabsTrigger>
        </TabsList>
        <TabsContent value="form">
          <WorkflowForm name={name} initial={data.safe_fields} onSaved={() => load().then(onChanged)} />
        </TabsContent>
        <TabsContent value="raw">
          <WorkflowRaw content={data.content} />
        </TabsContent>
        <TabsContent value="replace">
          <WorkflowReplace name={name} onSaved={() => load().then(onChanged)} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
