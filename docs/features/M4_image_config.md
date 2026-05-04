# M4 — Image config editor

> **Branch**: `feat/feature_M4_image_config`
> **Status**: Plan only — awaiting PM sign-off.
> **Parent plan**: [plan.md §4.2](../../plan.md), [plan.md §8 M4](../../plan.md)
> **Estimate**: 1.5–2 days

---

## 1. Goals

### Done criteria
1. `/config` page replaces the placeholder. Outer tabs over the 5 fork-managed config files:
   - `sfw_scenes` → `config/sfw_scenes.json`
   - `pose_motion_presets` → `config/pose_motion_presets.json`
   - `sfw_denylist` → `config/sfw_denylist.json`
   - `profile_keys` → `config/profile_keys.json`
   - `character_card_schema` → `character_card_schema.json` (repo root)
2. Per file: a tailored editor (not just generic Monaco) — see §3 for the per-file UX. A **Raw JSON tab** is always available as a fallback.
3. **Save** writes the file with the same atomic + auto-backup pattern as M1/M2/M3 (`platform/data/backups/<basename>.<KST>.bak`).
4. **Validation before save**:
   - `sfw_scenes` / `pose_motion_presets` / `sfw_denylist` / `profile_keys` — schema check (zod, hand-coded per file). 422 on failure.
   - `character_card_schema` — `Ajv2020.compile()` dry-run on the new schema. If compile throws → 422. Plus an optional dry-run against the existing `persona/char05.json` to surface "this schema would now reject the live character" warnings (non-blocking).
5. **Restart-required notice** — same toast pattern as M1 ("Saved · restart bot to load"). All 5 files are read at import time by `src/trait_pools.py` / `src/pose_motion_presets.py` / `src/handlers_char.py` / `src/profile_keys.py` / `platform/lib/ajv.ts`.
6. **Inline metadata** at the top of every tab: title + 1-line summary + "Used by" line + link to the file path. Same pattern as M2 prompt editor.
7. Sidebar `/config` enabled (currently it's already a nav item, just placeholder).

### Out-of-scope
- Adding **new** scene-pool fields beyond the existing schema (e.g. weather_pool). Scope = edit existing fields, add/delete entries — not extend the per-entry shape.
- Editing `_doc` / `_template` keys via the form. They are visible in Raw JSON only, the form mode hides underscore-prefixed keys.
- ComfyUI workflow (`comfyui_workflow/*.json`) editor — that's M5.
- Image-asset upload / preview (e.g. anchor_image upload). Stays out of scope until a dedicated image-asset milestone.
- Schema-aware migration (e.g. "rename a key in pose_motion_presets and update every `persona/charNN.json` that references it"). Edits are local to one file.

---

## 2. ★ PM decisions (answer before implementation)

### #1 — `character_card_schema.json` editing
This is the schema the Character editor's ajv validator depends on. Editing it can break the live `/characters` page if persona/charNN.json no longer validates against the new schema.

- **A (recommended)**: editable, with a **non-blocking dry-run warning** — on save we re-compile + revalidate every existing `persona/charNN.json` and surface any new validation errors as warnings in the response. User decides whether to proceed.
- **B**: read-only — surface the schema as a viewer only. Direct file edit if you really need to change it.
- **C**: editable + **blocking** dry-run — refuse to save if any live persona stops validating.

Recommend A — gives the user freedom while making the consequences visible. C is too restrictive (e.g. you might *want* to add a new required field that you'll backfill manually). B leaves no UI for one of the 5 files which makes the page feel inconsistent.

### #2 — `sfw_scenes` editor UX (1339 lines, 60+ scenes, 6 list-fields per scene)
Each entry has 4 small list fields (`pose_pool`, `camera_pool`, `location_pool`, `activity_tags` chips) + 4 string fields (`label`, `person_tags`, `expression_hint`, `notes`).

- **A (recommended)**: master-detail. Left pane = scene-key list (60+ rows, search box), right pane = form for the selected scene with chip widgets for the 4 list fields. "Add scene" button copies `_template` to a new key prompt-ed from the user. "Delete" with AlertDialog.
- **B**: single accordion of all scenes — every entry expandable inline. Slower to scan with 60+ scenes.
- **C**: Raw JSON only — easier to ship, harder to review changes.

Recommend A — same master-detail pattern as M3 character list, scales to 100+ scenes.

### #3 — `pose_motion_presets` editor UX (~30 entries, 5 string fields each + `anchor_risk` enum)
Smaller than sfw_scenes (no list fields, just text + one enum).

- **A (recommended)**: same master-detail layout as sfw_scenes but with 5 textareas + 1 select for `anchor_risk` (low/medium/high). Add/Duplicate/Delete from the list pane.
- **B**: single-page table with inline edit. Fast for small files, breaks down for long `primary` strings.

Recommend A — consistent with sfw_scenes; saves the user one navigation pattern to learn.

### #4 — `sfw_denylist` editor UX (1 array of strings)
- **A (recommended)**: simple chip widget — one chip per denied keyword, "+" button to add, × to remove. Same `ChipsWidget` we built in M3.
- **B**: textarea, one keyword per line.

Recommend A — discrete tokens are best as chips.

### #5 — `profile_keys` editor UX (key → list of aliases dictionary)
This file is `{ canonical_key: [alias1, alias2, ...], ... }` inside `canonical_keys`. ~15 canonical keys, each with 2–7 aliases.

- **A (recommended)**: master-detail with chip widget — left pane lists canonical keys, right pane edits the alias list as chips. Add canonical key (text input) / delete with confirmation.
- **B**: single grid (key column + chip-row column) inline.

Recommend A for consistency. B is workable if PM wants a one-screen view.

### #6 — Library: zod vs hand-rolled validation
For the 4 non-character-schema files we need shape validation.

- **A (recommended)**: add **zod** dependency. Schemas are concise + per-file errors are informative. Already a common Next.js dep.
- **B**: hand-rolled type-guards. Saves a dependency, doubles the validation code.

Recommend A — it's <50KB and pays off when we add more configs in M5+.

---

## 3. Per-file UX detail

### 3a. `sfw_scenes`
- Tab body: master-detail.
- Left pane (~280px): search box + scrolling list of scene keys. Each row: `<key>` (mono) + `<label>` (truncated). Sort: alphabetical by key. `_template` and `_doc` hidden.
- Right pane: form with these widgets:
  - `label` — text
  - `person_tags` — text (comma-sep validated as Danbooru tags pattern; warning toast only)
  - `pose_pool` / `camera_pool` / `location_pool` — chip widgets
  - `activity_tags` — text (comma-sep)
  - `expression_hint` — text
  - `notes` — textarea
- Top of right pane: scene key (read-only after creation, no rename in M4 — too disruptive), "Delete scene" button.
- Bottom of left pane: "+ Add scene" button → prompt for new key (regex `^[a-z][a-z0-9_]*$`), seeds from `_template`.
- Save button: page-level (per the whole file). Dirty indicator on the tab.
- Raw JSON sub-tab: full Monaco view of the file (read-write, parse error inline indicator).

### 3b. `pose_motion_presets`
- Identical master-detail layout as sfw_scenes.
- Right pane fields:
  - `primary` — textarea (4 rows)
  - `camera` — text
  - `audio` — text
  - `ambient_fallback` — text
  - `anchor_risk` — `<Select>` with 3 options
  - `notes` — textarea (3 rows)
- "+ Add preset" → prompt for new key, seed from `_template_text_only` minus `_doc`.
- Special key: `generic` cannot be deleted (asserted server-side too — `lookup()` requires it).

### 3c. `sfw_denylist`
- Single right-side card (no master list).
- Big chip widget bound to `outfit_state_keywords`.
- Description above: "Words inside [OUTFIT: …] tags are silently dropped if they match any of these (case-insensitive, whole-word)."

### 3d. `profile_keys`
- Master-detail.
- Left: list of canonical keys.
- Right: chip widget bound to the alias list. Top of right pane: canonical key (text, editable on save — server moves the entry).
- "+ Add canonical key" → prompt, seeds with empty alias list.
- Constraint: a canonical key must include itself in its aliases — server normalizes on save.

### 3e. `character_card_schema` (root file)
- Single-pane Monaco editor (full schema).
- "Validate now" button → calls `POST /api/config/character_card_schema/validate` with the current draft → returns `{ compile_ok: bool, dry_run: { charId: [issues], ... } }`.
- Save button only succeeds if `compile_ok === true` (compile errors are blocking — a syntactically invalid schema would brick the Character page).
- Persona dry-run is **non-blocking** (PM decision #1A) — issues shown as warnings.

---

## 4. Directory structure (M4 additions)

```
platform/
├── app/
│   ├── config/
│   │   ├── page.tsx                      # outer tabs (5 file tabs) — server entry
│   │   ├── config-page.tsx               # client — tab state
│   │   ├── sfw-scenes/{master-detail,scene-form}.tsx
│   │   ├── pose-presets/{master-detail,preset-form}.tsx
│   │   ├── denylist/denylist-form.tsx
│   │   ├── profile-keys/{master-detail,key-form}.tsx
│   │   └── character-schema/schema-editor.tsx
│   └── api/
│       └── config/
│           ├── sfw_scenes/route.ts                 # GET / PUT
│           ├── pose_motion_presets/route.ts        # GET / PUT
│           ├── sfw_denylist/route.ts               # GET / PUT
│           ├── profile_keys/route.ts               # GET / PUT
│           ├── character_card_schema/route.ts      # GET / PUT
│           └── character_card_schema/validate/route.ts  # POST (dry-run only)
└── lib/
    ├── config-files.ts                  # ★ new — paths + read/write/backup helpers
    ├── config-schemas.ts                # ★ new — zod schemas for 4 file shapes
    └── schema-dry-run.ts                # ★ new — recompile + revalidate every persona
```

Backups land in `platform/data/backups/<basename>.<KST>.bak` (same as existing files — `sfw_scenes.json.20260430-...bak`, `character_card_schema.json.20260430-...bak`, etc.).

---

## 5. New libraries

- **zod** — schema validation for the 4 non-character-schema files. ~`zod@3.23`.
- (No new UI libraries — chip / master-detail widgets reused from M3.)

Install: `cd platform && npm install zod`

---

## 6. `lib/config-files.ts` design

```ts
export type ConfigFileKey =
  | "sfw_scenes"
  | "pose_motion_presets"
  | "sfw_denylist"
  | "profile_keys"
  | "character_card_schema";

export const CONFIG_FILE_PATHS: Record<ConfigFileKey, string> = {
  sfw_scenes: "config/sfw_scenes.json",
  pose_motion_presets: "config/pose_motion_presets.json",
  sfw_denylist: "config/sfw_denylist.json",
  profile_keys: "config/profile_keys.json",
  character_card_schema: "character_card_schema.json",
};

export async function readConfigFile(key: ConfigFileKey): Promise<{ content: unknown; mtime: number }>;
export async function writeConfigFile(
  key: ConfigFileKey,
  content: unknown,
): Promise<{ backup_path: string; warnings?: ValidationIssue[] }>;
```

Internal helpers reuse `lib/backup.ts` (KST timestamp).

---

## 7. `lib/config-schemas.ts` (zod)

```ts
const sceneEntry = z.object({
  label: z.string(),
  person_tags: z.string(),
  pose_pool: z.array(z.string()),
  camera_pool: z.array(z.string()),
  location_pool: z.array(z.string()),
  activity_tags: z.string(),
  expression_hint: z.string(),
  notes: z.string().optional(),
}).strict();

export const sfwScenesSchema = z.record(z.union([z.string(), sceneEntry]));
// allow `_doc`/`_template` (string-keyed) to remain — tolerated by the loader

const presetEntry = z.object({
  primary: z.string(),
  camera: z.string(),
  audio: z.string(),
  ambient_fallback: z.string(),
  anchor_risk: z.enum(["low", "medium", "high"]),
  notes: z.string().optional(),
}).strict();

export const poseMotionPresetsSchema = z.record(z.union([z.string(), z.object({}).passthrough(), presetEntry]));

export const sfwDenylistSchema = z.object({
  _doc: z.string().optional(),
  outfit_state_keywords: z.array(z.string().min(1)),
}).strict();

export const profileKeysSchema = z.object({
  _doc: z.string().optional(),
  canonical_keys: z.record(z.array(z.string().min(1))),
}).strict();
```

`character_card_schema` is validated by `Ajv2020.compile()` (success/failure) — no zod schema-of-schema needed.

---

## 8. `lib/schema-dry-run.ts`

```ts
export async function dryRunPersonaValidation(
  draftSchema: object,
): Promise<{ compile_ok: boolean; compile_error?: string; per_character: Record<string, ValidationIssue[]> }>;
```

Steps:
1. `new Ajv2020({ allErrors: true, strict: false }).compile(draftSchema)` → wrap in try/catch.
2. If compiled, iterate `behaviors/` to enumerate live charNN, read each `persona/charNN.json`, run validator, collect issues.

Used by:
- `POST /api/config/character_card_schema/validate` — dry-run only (no write).
- `PUT /api/config/character_card_schema` — writes the file only if `compile_ok` and includes `dry_run` warnings in the response.

---

## 9. API contracts

| Route | Method | Body | Response | Errors |
|---|---|---|---|---|
| `/api/config/<file>` | GET | — | `{ key, content, mtime }` | 500 |
| `/api/config/sfw_scenes` | PUT | `{ content }` | `{ ok, backup_path }` | 422 INVALID_SHAPE / SAVE_FAILED |
| `/api/config/pose_motion_presets` | PUT | `{ content }` | `{ ok, backup_path }` | 422 INVALID_SHAPE / MISSING_GENERIC |
| `/api/config/sfw_denylist` | PUT | `{ content }` | `{ ok, backup_path }` | 422 INVALID_SHAPE |
| `/api/config/profile_keys` | PUT | `{ content }` | `{ ok, backup_path }` | 422 INVALID_SHAPE |
| `/api/config/character_card_schema` | PUT | `{ content }` | `{ ok, backup_path, warnings }` | 422 SCHEMA_COMPILE_FAILED |
| `/api/config/character_card_schema/validate` | POST | `{ content }` | `{ compile_ok, compile_error?, per_character }` | — |

All routes: `runtime = 'nodejs'`, `dynamic = 'force-dynamic'`.

---

## 10. UX details inherited from M2/M3

- Page title + "Used by" line at the top of every tab (M2 metadata pattern).
- Save button disabled until dirty.
- Dirty indicator (•) on the tab label.
- "Last backup at …" line under the Save button.
- AlertDialog for delete confirmations (chip-removal of single items is fine without a dialog).
- Toast on save: `"Saved · restart bot to load"` (M2 pattern).
- localStorage draft auto-save (M3 pattern, 400ms debounce, restore banner) — applied to `sfw_scenes` and `pose_motion_presets` since edits to those are larger. Smaller files (denylist / profile_keys / schema) skip draft auto-save.

---

## 11. Test scenarios (12)

> Run after implementation. Every scenario must PASS before merging to develop.

1. **Read-roundtrip** — open every tab, hit Save with no changes → file content unchanged (mtime updates only); no backup created.
2. **sfw_scenes add scene** — click "+ Add scene" → enter `night_walk` → fill label + 1 pose + 1 camera + 1 location → Save → file now has `night_walk` entry; backup written; bot restart loads it (verify with `python -c "from src.trait_pools import list_sfw_scene_keys; print('night_walk' in list_sfw_scene_keys())"`).
3. **sfw_scenes delete scene** — select `cafe_coffee` → Delete → confirm → entry removed; backup written.
4. **sfw_scenes shape error** — Raw JSON tab, paste `{ "bad": { "label": "x" } }` (missing required fields) → Save → 422 INVALID_SHAPE; toast surfaces zod error path; file untouched.
5. **pose_motion_presets add preset** — add `kneeling` → fill 5 fields + anchor_risk=low → Save → file ok.
6. **pose_motion_presets delete `generic`** — UI shows the Delete button disabled; if user crafts a PUT without `generic`, server returns 422 MISSING_GENERIC.
7. **sfw_denylist** — add `swimsuit_only` chip → Save → file content has the new entry. Remove it → Save → file restored.
8. **profile_keys add canonical key** — add `pet_name_for_user` with aliases `["nick","what_to_call"]` → Save → file ok.
9. **profile_keys rename canonical key** — change `nickname` to `nick_name` (text edit on right pane) → Save → key moved server-side; previous key removed.
10. **character_card_schema add required field** — add `"theme_color"` to `required` → POST validate → response shows `per_character.char05` reports missing field → save anyway → file written; UI shows warning banner; existing /characters page now flags char05 as invalid (expected).
11. **character_card_schema syntax error** — paste `{"$schema":"..."` (truncated) → Save blocked client-side (Monaco parse error); manual API PUT → server returns 422 SCHEMA_COMPILE_FAILED.
12. **Restart-required toast** — every successful Save in tabs 2–10 shows "Saved · restart bot to load" with Dashboard link; backup file present in `platform/data/backups/`.

---

## 12. Out-of-scope follow-ups (queue for after M4)

- Field-level help tooltips sourced from `_doc` keys inside each JSON.
- Side-by-side diff modal (M2-style) for config files. Not strictly needed since the master-detail UI already isolates per-entry changes, but could be added later for the Raw JSON tabs.
- Search across all configs (e.g. find a scene-key that references `from_above`).

---

## 13. Open questions for PM

1. **#1 dry-run policy for character_card_schema**: A / B / C? (recommend A)
2. **#2 sfw_scenes UX**: A / B / C? (recommend A)
3. **#3 pose_motion_presets UX**: A / B? (recommend A)
4. **#4 sfw_denylist UX**: A / B? (recommend A)
5. **#5 profile_keys UX**: A / B? (recommend A)
6. **#6 zod vs hand-rolled**: A / B? (recommend A)
7. Anything else you want included before sign-off?
