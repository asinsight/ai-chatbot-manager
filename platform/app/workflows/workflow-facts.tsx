import { Badge } from "@/components/ui/badge";
import type { WorkflowFacts } from "@/lib/workflows-meta";

function bytesToKb(n: number): string {
  return `${(n / 1024).toFixed(1)} KB`;
}

export function WorkflowFactsBlock({ facts }: { facts: WorkflowFacts }) {
  return (
    <div className="grid grid-cols-2 gap-2 rounded-md border bg-muted/30 p-3 text-xs sm:grid-cols-4">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Nodes</div>
        <div className="font-mono font-semibold">{facts.node_count}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Σ steps</div>
        <div className="font-mono font-semibold">{facts.sampler_steps_total}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Refiner</div>
        <div className="font-mono font-semibold">
          {facts.has_refiner_or_upscaler ? "yes" : "no"}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Size</div>
        <div className="font-mono font-semibold">{bytesToKb(facts.size_bytes)}</div>
      </div>
    </div>
  );
}

export function StageBadges({ stages }: { stages: ("standard" | "hq")[] }) {
  if (stages.length === 0) {
    return (
      <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
        Unused
      </Badge>
    );
  }
  return (
    <div className="flex gap-1">
      {stages.includes("standard") && (
        <Badge className="text-[10px] uppercase tracking-wider">Standard</Badge>
      )}
      {stages.includes("hq") && (
        <Badge className="bg-amber-600 text-[10px] uppercase tracking-wider hover:bg-amber-600/90">HQ</Badge>
      )}
    </div>
  );
}
