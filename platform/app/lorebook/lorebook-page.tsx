"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import type { WorldSummary } from "@/lib/lorebook-meta";

import { MappingCard } from "./mapping-card";
import { WorldEditor } from "./world-editor";
import { WorldList } from "./world-list";

type Resp = { worlds: WorldSummary[] };

export function LorebookPage() {
  const [worlds, setWorlds] = useState<WorldSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/lorebook/worlds", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as Resp;
      setWorlds(body.worlds);
      if (selected === null && body.worlds.length > 0) setSelected(body.worlds[0].name);
      if (selected && !body.worlds.some((w) => w.name === selected)) {
        setSelected(body.worlds[0]?.name ?? null);
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [selected]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-destructive">Lorebook load failed: {error}</p>;
  }
  if (!worlds) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading lorebook…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <MappingCard onSaved={load} />

      <div className="grid grid-cols-[280px_1fr] gap-4">
        <WorldList
          worlds={worlds}
          selected={selected}
          onSelect={(name) => setSelected(name || null)}
          onChanged={load}
        />
        {selected ? (
          <WorldEditor name={selected} onChanged={load} />
        ) : (
          <p className="text-sm italic text-muted-foreground">
            Select a world from the list, or add a new one.
          </p>
        )}
      </div>
    </div>
  );
}
