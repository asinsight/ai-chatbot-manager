"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import type { WorkflowSummary } from "@/lib/workflows-meta";

import { StageAssignments } from "./stage-assignments";
import { WorkflowTab } from "./workflow-tab";

type Resp = { workflows: WorkflowSummary[] };

export function WorkflowsPage() {
  const [data, setData] = useState<WorkflowSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/workflows", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as Resp;
      setData(body.workflows);
      if (!active && body.workflows.length > 0) setActive(body.workflows[0].name);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [active]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-destructive">Workflows load failed: {error}</p>;
  }
  if (!data || !active) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading workflows…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <StageAssignments onChanged={load} />

      <Tabs value={active} onValueChange={setActive}>
        <TabsList className="flex h-auto flex-wrap justify-start">
          {data.map((w) => (
            <TabsTrigger key={w.name} value={w.name}>
              <span className="font-mono text-xs">{w.name}</span>
              {w.stage_badges.length > 0 && (
                <span className="ml-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                  {w.stage_badges.join(" + ")}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        {data.map((w) => (
          <TabsContent key={w.name} value={w.name}>
            <WorkflowTab
              name={w.name}
              stageBadges={w.stage_badges}
              description={w.description}
              onChanged={load}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
