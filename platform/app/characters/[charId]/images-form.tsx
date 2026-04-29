"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const BODY_FIELDS: { key: string; label: string }[] = [
  { key: "size", label: "Size (height)" },
  { key: "build", label: "Build (slim / athletic / etc)" },
  { key: "curve", label: "Curve (waist line)" },
  { key: "accent", label: "Accent (collarbone / abs / framing-conditional)" },
  { key: "ass", label: "Ass (framing-conditional)" },
];

const BREAST_FIELDS: { key: string; label: string }[] = [
  { key: "size", label: "Size (small / medium / large …)" },
  { key: "feature", label: "Feature (silhouette only — no NSFW)" },
];

export function ImagesForm({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const setNested = (
    parent: "body_shape" | "breast",
    childKey: string,
    childVal: string,
  ) => {
    const current =
      value[parent] && typeof value[parent] === "object" && !Array.isArray(value[parent])
        ? (value[parent] as Record<string, unknown>)
        : {};
    onChange({ ...value, [parent]: { ...current, [childKey]: childVal } });
  };
  const get = (k: string): string =>
    typeof value[k] === "string" ? (value[k] as string) : "";
  const getNested = (parent: string, childKey: string): string => {
    const obj = value[parent];
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return "";
    const c = (obj as Record<string, unknown>)[childKey];
    return typeof c === "string" ? c : "";
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Danbooru-tag fields injected into the image-generation prompt. SFW
        invariant: clothing must be a complete outfit; no exposure tags. Body
        shape and breast feature are silhouette-only (no NSFW descriptors).
      </p>

      <div className="space-y-1.5">
        <Label className="font-mono text-xs">char_id</Label>
        <Input value={get("char_id")} disabled className="font-mono text-xs" />
      </div>

      {(["appearance_tags", "clothing", "alt_outfit", "underwear"] as const).map(
        (k) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={k} className="font-mono text-xs">
              {k}
            </Label>
            <Textarea
              id={k}
              value={get(k)}
              onChange={(e) => set(k, e.target.value)}
              rows={2}
              className="font-mono text-xs"
            />
          </div>
        ),
      )}

      <div className="space-y-2 rounded-md border bg-muted/20 p-3">
        <Label className="font-mono text-xs uppercase tracking-wider">
          body_shape
        </Label>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {BODY_FIELDS.map((bf) => (
            <div key={bf.key} className="space-y-1">
              <Label className="text-xs text-muted-foreground">{bf.label}</Label>
              <Input
                value={getNested("body_shape", bf.key)}
                onChange={(e) =>
                  setNested("body_shape", bf.key, e.target.value)
                }
                className="font-mono text-xs"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 rounded-md border bg-muted/20 p-3">
        <Label className="font-mono text-xs uppercase tracking-wider">
          breast
        </Label>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {BREAST_FIELDS.map((bf) => (
            <div key={bf.key} className="space-y-1">
              <Label className="text-xs text-muted-foreground">{bf.label}</Label>
              <Input
                value={getNested("breast", bf.key)}
                onChange={(e) => setNested("breast", bf.key, e.target.value)}
                className="font-mono text-xs"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
