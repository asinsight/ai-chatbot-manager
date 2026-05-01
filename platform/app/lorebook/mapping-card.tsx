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

import type { MappingPayload } from "@/lib/lorebook-meta";

const FALLBACK = "__fallback__"; // dropdown value meaning "use legacy <char_id>.json"

export function MappingCard({ onSaved }: { onSaved?: () => void }) {
  const [data, setData] = useState<MappingPayload | null>(null);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/lorebook/mapping", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as MappingPayload;
      setData(body);
      setDraft({ ...body.mapping });
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-destructive">Mapping load failed: {error}</p>;
  }
  if (!data || !draft) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading mapping…
      </div>
    );
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(data.mapping);

  const setOne = (charId: string, worldId: string) => {
    const next = { ...draft };
    if (worldId === FALLBACK) {
      delete next[charId];
    } else {
      next[charId] = worldId;
    }
    setDraft(next);
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch("/api/lorebook/mapping", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mapping: draft }),
      });
      const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Save failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success("Saved · restart bot to load");
      await load();
      onSaved?.();
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Character mapping</CardTitle>
        <CardDescription>
          Pick the world (lorebook) used for each character. Multiple
          characters can share the same world. Picking{" "}
          <em>(legacy fallback)</em> drops the entry from{" "}
          <code className="font-mono">world_info/mapping.json</code> — the bot
          then looks for{" "}
          <code className="font-mono">world_info/&lt;char_id&gt;.json</code>{" "}
          on disk. Bot restart required.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.characters.length === 0 && (
          <p className="text-xs italic text-muted-foreground">
            (no characters registered)
          </p>
        )}
        <div className="space-y-2">
          {data.characters.map((charId) => {
            const cur = draft[charId] ?? FALLBACK;
            return (
              <div key={charId} className="grid grid-cols-[120px_1fr] items-center gap-3">
                <Label className="font-mono text-xs">{charId}</Label>
                <Select value={cur} onValueChange={(v) => setOne(charId, v)}>
                  <SelectTrigger className="text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={FALLBACK}>
                      (legacy fallback — world_info/{charId}.json)
                    </SelectItem>
                    {data.worlds.map((w) => (
                      <SelectItem key={w} value={w}>
                        {w}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>
        <div className="flex items-center justify-end gap-2">
          {dirty && <span className="text-xs text-amber-600">● unsaved</span>}
          <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save mapping"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
