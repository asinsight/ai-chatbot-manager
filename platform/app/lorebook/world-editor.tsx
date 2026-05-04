"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import type { LorebookEntry, LorebookFile } from "@/lib/lorebook-meta";

import { EntryForm } from "./entry-form";
import { TestPane } from "./test-pane";

type DetailResp = {
  name: string;
  content: LorebookFile;
  mtime_ms: number;
  size_bytes: number;
  mapped_chars: string[];
};

const BLANK_ENTRY: LorebookEntry = {
  keywords: [],
  content: "",
  position: "background",
};

export function WorldEditor({
  name,
  onChanged,
}: {
  name: string;
  onChanged: () => Promise<void> | void;
}) {
  const [data, setData] = useState<DetailResp | null>(null);
  const [draft, setDraft] = useState<LorebookFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/lorebook/worlds/${encodeURIComponent(name)}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as DetailResp;
      setData(body);
      setDraft(JSON.parse(JSON.stringify(body.content)) as LorebookFile);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [name]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-destructive">Load failed: {error}</p>;
  }
  if (!data || !draft) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading world…
      </div>
    );
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(data.content);

  const updateEntry = (i: number, next: LorebookEntry) => {
    setDraft({
      ...draft,
      entries: draft.entries.map((e, j) => (j === i ? next : e)),
    });
  };
  const deleteEntry = (i: number) => {
    setDraft({ ...draft, entries: draft.entries.filter((_, j) => j !== i) });
  };
  const addEntry = () => {
    setDraft({ ...draft, entries: [...draft.entries, { ...BLANK_ENTRY }] });
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/lorebook/worlds/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: draft }),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Save failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Saved · restart bot to load");
      await load();
      await onChanged();
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <code className="font-mono text-sm font-semibold">{name}.json</code>
          <p className="text-xs text-muted-foreground">
            world_info/{name}.json
            {data.mapped_chars.length > 0 && (
              <> · used by <code className="font-mono">{data.mapped_chars.join(", ")}</code></>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {dirty && <span className="text-amber-600">● unsaved</span>}
          <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save world"}
          </Button>
        </div>
      </div>

      <TestPane content={draft} />

      <div className="space-y-3">
        {draft.entries.length === 0 && (
          <p className="rounded-md border bg-muted/20 p-3 text-xs italic text-muted-foreground">
            (no entries — add one below)
          </p>
        )}
        {draft.entries.map((entry, i) => (
          <EntryForm
            key={i}
            index={i}
            entry={entry}
            onChange={(next) => updateEntry(i, next)}
            onDelete={() => deleteEntry(i)}
          />
        ))}
      </div>

      <Button type="button" size="sm" variant="outline" onClick={addEntry}>
        <Plus /> Add entry
      </Button>
    </div>
  );
}
