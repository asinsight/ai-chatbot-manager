"use client";

import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { ChipsWidget } from "@/app/characters/[charId]/widgets";

import type { LorebookEntry } from "@/lib/lorebook-meta";

export function EntryForm({
  index,
  entry,
  onChange,
  onDelete,
}: {
  index: number;
  entry: LorebookEntry;
  onChange: (next: LorebookEntry) => void;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Entry #{index + 1}
        </span>
        <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
          <Trash2 className="h-3.5 w-3.5" /> Delete entry
        </Button>
      </div>
      <div>
        <Label className="text-xs">Keywords (substring-matched, case-insensitive)</Label>
        <ChipsWidget
          value={entry.keywords}
          onChange={(v) => onChange({ ...entry, keywords: v })}
        />
      </div>
      <div>
        <Label className="text-xs">Content (injected into the prompt when any keyword matches)</Label>
        <Textarea
          value={entry.content}
          onChange={(e) => onChange({ ...entry, content: e.target.value })}
          rows={4}
          className="font-mono text-xs"
        />
      </div>
      <div>
        <Label className="text-xs">Position</Label>
        <Select
          value={entry.position}
          onValueChange={(v) =>
            onChange({ ...entry, position: v as LorebookEntry["position"] })
          }
        >
          <SelectTrigger className="text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="background">background — long-term backdrop facts</SelectItem>
            <SelectItem value="active">active — situational/current context</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
