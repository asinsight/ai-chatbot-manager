import { z } from "zod";

// Scenes / presets are dictionaries keyed by scene-id.
// Underscore-prefixed keys (`_doc`, `_template`) are loader-skipped — we
// preserve them on save but don't enforce shape.

const sceneEntrySchema = z
  .object({
    label: z.string(),
    person_tags: z.string(),
    pose_pool: z.array(z.string()),
    camera_pool: z.array(z.string()),
    location_pool: z.array(z.string()),
    activity_tags: z.string(),
    expression_hint: z.string(),
    notes: z.string().optional(),
  })
  .strict();

export type SceneEntry = z.infer<typeof sceneEntrySchema>;

export function validateSfwScenes(content: unknown): { ok: true } | { ok: false; errors: string[] } {
  if (typeof content !== "object" || content === null || Array.isArray(content)) {
    return { ok: false, errors: ["root must be an object"] };
  }
  const obj = content as Record<string, unknown>;
  const errors: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("_")) continue; // _doc / _template — pass-through
    const r = sceneEntrySchema.safeParse(v);
    if (!r.success) {
      for (const issue of r.error.issues) {
        errors.push(`${k}.${issue.path.join(".") || "<root>"}: ${issue.message}`);
      }
    }
  }
  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

const presetEntrySchema = z
  .object({
    primary: z.string(),
    camera: z.string(),
    audio: z.string(),
    ambient_fallback: z.string(),
    anchor_risk: z.enum(["low", "medium", "high"]),
    notes: z.string().optional(),
  })
  .strict();

export type PresetEntry = z.infer<typeof presetEntrySchema>;

export function validatePoseMotionPresets(
  content: unknown,
): { ok: true } | { ok: false; errors: string[] } {
  if (typeof content !== "object" || content === null || Array.isArray(content)) {
    return { ok: false, errors: ["root must be an object"] };
  }
  const obj = content as Record<string, unknown>;
  const errors: string[] = [];
  let hasGeneric = false;
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("_")) continue;
    if (k === "generic") hasGeneric = true;
    const r = presetEntrySchema.safeParse(v);
    if (!r.success) {
      for (const issue of r.error.issues) {
        errors.push(`${k}.${issue.path.join(".") || "<root>"}: ${issue.message}`);
      }
    }
  }
  if (!hasGeneric) errors.push("missing required `generic` preset (lookup() fallback)");
  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

const sfwDenylistSchema = z
  .object({
    _doc: z.string().optional(),
    outfit_state_keywords: z.array(z.string().min(1)),
  })
  .strict();

export function validateSfwDenylist(
  content: unknown,
): { ok: true } | { ok: false; errors: string[] } {
  const r = sfwDenylistSchema.safeParse(content);
  if (r.success) return { ok: true };
  return {
    ok: false,
    errors: r.error.issues.map(
      (i) => `${i.path.join(".") || "<root>"}: ${i.message}`,
    ),
  };
}

const profileKeysSchema = z
  .object({
    _doc: z.string().optional(),
    canonical_keys: z.record(z.string(), z.array(z.string().min(1))),
  })
  .strict();

export function validateProfileKeys(
  content: unknown,
): { ok: true } | { ok: false; errors: string[] } {
  const r = profileKeysSchema.safeParse(content);
  if (r.success) return { ok: true };
  return {
    ok: false,
    errors: r.error.issues.map(
      (i) => `${i.path.join(".") || "<root>"}: ${i.message}`,
    ),
  };
}
