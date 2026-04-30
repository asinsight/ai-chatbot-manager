"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type Tier = {
  condition: { fixation: [number, number] };
  prompt: string;
};

const TIER_LABELS = ["VERY LOW", "LOW", "MEDIUM", "HIGH"];

export function BehaviorsForm({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const tiers: Tier[] = Array.isArray(value.proactive_behavior)
    ? (value.proactive_behavior as Tier[])
    : [];

  const setTier = (i: number, patch: Partial<Tier>) => {
    const next = tiers.map((t, j) => (j === i ? { ...t, ...patch } : t));
    onChange({ ...value, proactive_behavior: next });
  };

  const setRange = (i: number, lo: number, hi: number) => {
    const t = tiers[i];
    if (!t) return;
    setTier(i, { condition: { fixation: [lo, hi] } });
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Fixation-tier behavior table — the bot picks the tier whose range
        contains the current fixation value and injects only that tier's prompt
        into the system prompt.
      </p>
      {tiers.map((t, i) => {
        const [lo, hi] = t.condition?.fixation ?? [0, 0];
        return (
          <div key={i} className="space-y-2 rounded-md border bg-muted/20 p-3">
            <div className="flex items-center gap-3">
              <Label className="font-mono text-xs uppercase tracking-wider">
                {TIER_LABELS[i] ?? `Tier ${i + 1}`}
              </Label>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                fixation
                <Input
                  type="number"
                  value={lo}
                  onChange={(e) => setRange(i, Number(e.target.value), hi)}
                  className="h-7 w-16 font-mono text-xs"
                />
                –
                <Input
                  type="number"
                  value={hi}
                  onChange={(e) => setRange(i, lo, Number(e.target.value))}
                  className="h-7 w-16 font-mono text-xs"
                />
              </div>
            </div>
            <Textarea
              value={t.prompt ?? ""}
              onChange={(e) => setTier(i, { prompt: e.target.value })}
              rows={3}
              className="font-mono text-xs"
            />
          </div>
        );
      })}
    </div>
  );
}
