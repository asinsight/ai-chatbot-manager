"use client";

import { useMemo, useState } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

import { previewMatches, type LorebookFile } from "@/lib/lorebook-meta";

export function TestPane({ content }: { content: LorebookFile }) {
  const [text, setText] = useState("");

  const matches = useMemo(() => {
    if (!text.trim()) return [];
    return previewMatches(text, content);
  }, [text, content]);

  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <div className="flex items-baseline justify-between">
        <Label className="text-xs">Test pane — paste user message</Label>
        <span className="text-[10px] text-muted-foreground">
          mirrors src/prompt.py _match_world_info()
        </span>
      </div>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="e.g. Hey, how is Director Park treating you this week?"
        className="text-xs"
      />
      <div className="text-xs">
        {text.trim() === "" ? (
          <span className="italic text-muted-foreground">
            (paste a message to preview which entries would fire)
          </span>
        ) : matches.length === 0 ? (
          <span className="italic text-muted-foreground">no matches</span>
        ) : (
          <div className="space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {matches.length} {matches.length === 1 ? "match" : "matches"}
            </div>
            {matches.map((m, i) => (
              <div key={i} className="rounded border bg-background p-2">
                <div className="mb-1 flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="text-[10px] uppercase tracking-wider"
                  >
                    {m.position}
                  </Badge>
                  <code className="font-mono text-[11px] text-muted-foreground">
                    matched: {m.keyword}
                  </code>
                </div>
                <div className="font-mono text-[11px] leading-snug">{m.content}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
