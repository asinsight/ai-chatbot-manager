"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { MonacoEditor } from "@/components/monaco-client";

export function ChipsWidget({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (value.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...value, v]);
    setDraft("");
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {value.length === 0 && (
          <span className="text-xs italic text-muted-foreground">(empty)</span>
        )}
        {value.map((v, i) => (
          <span
            key={`${v}-${i}`}
            className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="text-muted-foreground hover:text-foreground"
              aria-label={`Remove ${v}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder="Add a value and press Enter"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="font-mono text-xs"
        />
        <Button type="button" size="sm" variant="outline" onClick={add}>
          <Plus /> Add
        </Button>
      </div>
    </div>
  );
}

export function KvWidget({
  value,
  onChange,
}: {
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  const entries = Object.entries(value);
  const [newKey, setNewKey] = useState("");
  const setKey = (k: string, v: string) => onChange({ ...value, [k]: v });
  const renameKey = (oldK: string, newK: string) => {
    if (!newK || newK === oldK || newK in value) return;
    const next: Record<string, string> = {};
    for (const [k, v] of entries) {
      next[k === oldK ? newK : k] = v;
    }
    onChange(next);
  };
  const removeKey = (k: string) => {
    const next = { ...value };
    delete next[k];
    onChange(next);
  };
  const addKey = () => {
    const k = newKey.trim();
    if (!k || k in value) return;
    onChange({ ...value, [k]: "" });
    setNewKey("");
  };
  return (
    <div className="space-y-2">
      {entries.length === 0 && (
        <p className="text-xs italic text-muted-foreground">(empty — add a mood key below)</p>
      )}
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-start gap-2">
          <Input
            value={k}
            onBlur={(e) => renameKey(k, e.target.value.trim())}
            onChange={(e) => {
              // local-only edit, commit on blur
              e.target.value = e.target.value;
            }}
            className="w-40 font-mono text-xs"
            placeholder="mood key"
          />
          <Textarea
            value={v}
            onChange={(e) => setKey(k, e.target.value)}
            className="flex-1 font-mono text-xs"
            rows={2}
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => removeKey(k)}
            aria-label={`Remove ${k}`}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <div className="flex gap-2 pt-1">
        <Input
          value={newKey}
          placeholder="new mood key"
          onChange={(e) => setNewKey(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addKey();
            }
          }}
          className="w-40 font-mono text-xs"
        />
        <Button type="button" size="sm" variant="outline" onClick={addKey}>
          <Plus /> Add mood
        </Button>
      </div>
    </div>
  );
}

export type Trigger = { trigger: string; mood: string };

export function TriggerListWidget({
  value,
  onChange,
}: {
  value: Trigger[];
  onChange: (next: Trigger[]) => void;
}) {
  const update = (i: number, patch: Partial<Trigger>) => {
    onChange(value.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  };
  const remove = (i: number) => onChange(value.filter((_, j) => j !== i));
  const add = () => onChange([...value, { trigger: "", mood: "" }]);
  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <p className="text-xs italic text-muted-foreground">(empty — add a trigger below)</p>
      )}
      {value.map((t, i) => (
        <div key={i} className="flex items-start gap-2">
          <Textarea
            value={t.trigger}
            onChange={(e) => update(i, { trigger: e.target.value })}
            placeholder="Trigger condition (free text)"
            className="flex-1 font-mono text-xs"
            rows={2}
          />
          <Input
            value={t.mood}
            onChange={(e) => update(i, { mood: e.target.value })}
            placeholder="→ mood"
            className="w-32 font-mono text-xs"
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => remove(i)}
            aria-label="Remove trigger"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={add}>
        <Plus /> Add trigger
      </Button>
    </div>
  );
}

type StatLimitsValue = { fixation?: { up?: number; down?: number } };

export function StatLimitsWidget({
  value,
  onChange,
}: {
  value: StatLimitsValue;
  onChange: (next: StatLimitsValue) => void;
}) {
  const fixation = value.fixation ?? {};
  const setFix = (patch: { up?: number; down?: number }) => {
    onChange({ ...value, fixation: { ...fixation, ...patch } });
  };
  return (
    <div className="grid grid-cols-2 gap-3 rounded-md border bg-muted/20 p-3">
      <div>
        <label className="text-xs text-muted-foreground">fixation up cap</label>
        <Input
          type="number"
          value={fixation.up ?? ""}
          placeholder="(default 5)"
          onChange={(e) =>
            setFix({
              up: e.target.value === "" ? undefined : Number(e.target.value),
            })
          }
          className="font-mono text-xs"
        />
      </div>
      <div>
        <label className="text-xs text-muted-foreground">fixation down cap</label>
        <Input
          type="number"
          value={fixation.down ?? ""}
          placeholder="(default -5)"
          onChange={(e) =>
            setFix({
              down: e.target.value === "" ? undefined : Number(e.target.value),
            })
          }
          className="font-mono text-xs"
        />
      </div>
    </div>
  );
}

export function MonacoField({
  value,
  onChange,
  language = "markdown",
  height = "240px",
}: {
  value: string;
  onChange: (next: string) => void;
  language?: string;
  height?: string;
}) {
  return (
    <div className="overflow-hidden rounded-md border">
      <MonacoEditor
        height={height}
        defaultLanguage={language}
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          wordWrap: "on",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 12,
          tabSize: 2,
        }}
      />
    </div>
  );
}
