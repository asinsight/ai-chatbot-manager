"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { PERSONA_FIELDS, type FieldDef } from "@/lib/char-schema";
import {
  ChipsWidget,
  KvWidget,
  MonacoField,
  StatLimitsWidget,
  TriggerListWidget,
  type Trigger,
} from "./widgets";

export function PersonaForm({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const set = <K extends string>(k: K, v: unknown) => {
    onChange({ ...value, [k]: v });
  };

  return (
    <div className="space-y-5">
      {PERSONA_FIELDS.map((f) => (
        <FieldRow key={f.key} field={f}>
          {renderField(f, value[f.key], (v) => set(f.key, v))}
        </FieldRow>
      ))}
    </div>
  );
}

function FieldRow({
  field,
  children,
}: {
  field: FieldDef;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Label htmlFor={field.key} className="font-mono text-xs">
          {field.label}
        </Label>
        {field.required && (
          <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-destructive">
            required
          </span>
        )}
        <span className="font-mono text-[10px] text-muted-foreground">
          {field.key}
        </span>
      </div>
      {field.description && (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      )}
      {children}
    </div>
  );
}

function renderField(
  field: FieldDef,
  rawValue: unknown,
  onChange: (v: unknown) => void,
): React.ReactNode {
  switch (field.widget) {
    case "text":
      return (
        <Input
          id={field.key}
          value={typeof rawValue === "string" ? rawValue : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          className="font-mono text-xs"
        />
      );
    case "textarea":
      return (
        <Textarea
          id={field.key}
          value={typeof rawValue === "string" ? rawValue : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={field.multiline ? 6 : 3}
          className="font-mono text-xs"
        />
      );
    case "monaco":
      return (
        <MonacoField
          value={typeof rawValue === "string" ? rawValue : ""}
          onChange={onChange}
          height="280px"
        />
      );
    case "chips":
      return (
        <ChipsWidget
          value={Array.isArray(rawValue) ? (rawValue as string[]) : []}
          onChange={onChange}
        />
      );
    case "kv":
      return (
        <KvWidget
          value={
            rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)
              ? (rawValue as Record<string, string>)
              : {}
          }
          onChange={onChange}
        />
      );
    case "trigger-list":
      return (
        <TriggerListWidget
          value={Array.isArray(rawValue) ? (rawValue as Trigger[]) : []}
          onChange={onChange}
        />
      );
    case "stat-limits":
      return (
        <StatLimitsWidget
          value={
            rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)
              ? (rawValue as { fixation?: { up?: number; down?: number } })
              : {}
          }
          onChange={onChange}
        />
      );
  }
}
