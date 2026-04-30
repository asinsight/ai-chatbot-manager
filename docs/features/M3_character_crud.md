# M3 — Character card CRUD

> **Branch**: `feat/feature_M3_character_crud`
> **Status**: Plan only — awaiting PM sign-off.
> **Parent plan**: [plan.md §4.2](../../plan.md), [plan.md §8 M3](../../plan.md)
> **Estimate**: 2–2.5 days

---

## 1. Goals

### Done criteria
1. `/characters` page — list of all characters (currently 1: char05) with profile summary, mtime, action menu (Edit / Duplicate / Delete).
2. `/characters/[charId]` page — single-form editor for the **3-file bundle** (`persona/charNN.json` + `behaviors/charNN.json` + `images/charNN.json`).
3. **Form mode** (schema-driven, default) + **Raw JSON mode** toggle — per file, Monaco viewer.
4. **Create new character**:
   - Auto-allocate next free `charNN` (lowest available — currently char01 since char01-04 + char06-09 were dropped during i18n; recommended is **char01**).
   - Blank template seeded into all 3 files (with required-field placeholders).
   - Auto-add `TEST_CHAR_BOT_<charNN>=` + `TEST_CHAR_USERNAME_<charNN>=` + `PROD_*` lines to `.env`.
5. **Duplicate**: copy the 3 files to next free `charNN`, prefix `name` with "Copy of …", clear `anchor_image`.
6. **Delete**: backup all 3 files + `.env` lines, then remove. Optional: also drop `images/<charNN>.png` if present.
7. **first_mes preview**: render markdown with `{{user}}` → "User" and `{{char}}` → character `name` substitution. Side panel.
8. **Schema validation** via ajv: dry-run before save; error toast when invalid.
9. **Auto-backup** on save (same `platform/data/backups/<file>.<KST>.bak` pattern as M1/M2).
10. Sidebar `/characters` enabled.

### Out-of-scope
- `anchor_image` upload UI (stays read-only text field with filename — image-config + actual upload is M4).
- Inline image preview of `anchor_image`.
- Character preview chat (a "test message" panel that calls Grok).
- Bulk import / export (.png card format).
- Versioning beyond per-file backups.

---

## 2. ★ PM decisions (answer before implementation)

### #1 — charNN allocation strategy
- **A (recommended)**: lowest free number — fork ships only char05; new = char01, then char02, …
- **B**: highest + 1 — new = char06, char07, …
- Recommend A — keeps numbering tight and matches `_CHAR_ORDER` seed expectation.

### #2 — Schema-driven form generator: hand-coded vs library
- **A (recommended)**: hand-coded form using shadcn primitives. ~22 fields × 5 widget types (text / textarea / Monaco / chip-list / object-list). Custom fields: `mes_example` (Monaco multi-line), `mood_behaviors` (key-value editor), `mood_triggers` (object array editor), `stat_limits.fixation` (integer pair).
- **B**: library — `@rjsf/core` (react-json-schema-form). Auto-generates from JSON Schema; less code but generic UX.
- Recommend A — fixed schema, custom widgets matter more than auto-gen flexibility.

### #3 — Raw JSON mode UX
- **A (recommended)**: per-file Raw JSON tab — 3 tabs (persona / behaviors / images), each with Monaco. Toggle Form ↔ Raw at the top of the page.
- **B**: single Raw JSON Monaco showing all 3 files concatenated as `{persona, behaviors, images}` object.
- Recommend A — easier to lint individually; matches file-on-disk layout.

### #4 — Bot lifecycle on Create / Delete
- Adding a new character requires bot restart (since `bot.py` enumerates `behaviors/char*.json` at boot). Same as `.env` saves.
- **A (recommended)**: post-save toast `"Character saved · restart bot to load"` with Dashboard link. No auto-restart.
- **B**: auto-restart on Create/Delete (might surprise users).
- Recommend A — consistent with M1/M2 UX.

### #5 — Delete cascade
- **A (recommended)**: delete all 3 JSON files + .env character lines (TEST_/PROD_ both) + ComfyUI input PNG (if present).
- **B**: Move 3 JSONs to `platform/data/backups/deleted/<charNN>.<ts>/` instead of `rm` (soft delete).
- Recommend B — backups are cheap, recovery is trivial.

---

## 3. Directory structure (M3 additions)

```
platform/
├── app/
│   ├── characters/
│   │   ├── page.tsx                  # list page (server entry)
│   │   ├── characters-list.tsx       # client — fetches list, action menu
│   │   ├── new/page.tsx              # create flow (or modal — TBD; recommend modal)
│   │   ├── [charId]/
│   │   │   ├── page.tsx              # edit page
│   │   │   ├── character-editor.tsx  # client — form + raw + preview
│   │   │   ├── form-fields.tsx       # client — schema-driven widgets
│   │   │   ├── raw-tab.tsx           # client — 3 Monaco editors
│   │   │   └── preview-panel.tsx     # client — first_mes / description preview
│   │   └── (action helpers)
│   └── api/
│       └── characters/
│           ├── route.ts              # GET (list) + POST (create)
│           └── [charId]/
│               ├── route.ts          # GET / PUT / DELETE
│               └── duplicate/route.ts # POST (clone)
├── components/ui/
│   └── textarea.tsx                  # ★ new shadcn primitive (multi-line input)
└── lib/
    ├── characters.ts                 # ★ new — read/write/delete + ajv validation
    ├── char-schema.ts                # ★ new — typed shape from character_card_schema.json + helpers
    └── ajv.ts                        # ★ new — singleton Ajv instance + compiled validators
```

The 3 files per character live in:
- `behaviors/charNN.json`
- `persona/charNN.json`
- `images/charNN.json`

Backups land in `platform/data/backups/{persona,behaviors,images}_charNN.json.{KST}.bak`.

Soft-delete (option B): `platform/data/backups/deleted/charNN.<KST>/`.

---

## 4. New libraries

- `ajv` — JSON Schema validator (active, well-maintained).
- `ajv-formats` — adds standard formats (date, email, uri, …) — optional, skip if unused.
- `react-markdown` — render markdown for `first_mes` preview.
- `remark-gfm` — GitHub-flavored markdown plugin (lists / tables — minor but standard pairing).

Install: `cd platform && npm install ajv react-markdown remark-gfm`

---

## 5. `lib/characters.ts` design

```ts
export type CharacterId = `char${number}`;

export type CharacterCard = {
  charId: string;            // "char05"
  persona: Record<string, unknown>;     // contents of persona/charNN.json
  behaviors: Record<string, unknown>;   // contents of behaviors/charNN.json
  images: Record<string, unknown>;      // contents of images/charNN.json
};

export type CharacterListEntry = {
  charId: string;
  name: string;
  profile_summary_ko: string;
  mtime: number;             // ms since epoch — max of 3 files
};

export async function listCharacters(): Promise<CharacterListEntry[]>;
export async function readCharacter(charId: string): Promise<CharacterCard>;
export async function writeCharacter(charId: string, card: CharacterCard): Promise<{ backup_paths: string[]; warnings: ValidationIssue[] }>;
export async function deleteCharacter(charId: string): Promise<{ backup_dir: string }>;
export async function duplicateCharacter(srcCharId: string): Promise<{ charId: string }>;
export async function nextFreeCharId(): Promise<string>;   // "char01" / "char02" / ...
```

Internal helpers:
- `_loadJson(file: string)` — read + parse, throws on syntax error.
- `_writeJsonAtomically(file: string, content: object)` — `JSON.stringify(content, null, 2) + "\n"` → tmp file → rename.
- `_backupAll(charId)` — backup 3 files in one call, returns 3 paths.
- `_envCharLines(charId)` — generate the 4 .env lines (TEST_CHAR_BOT_, TEST_CHAR_USERNAME_, PROD_CHAR_BOT_, PROD_CHAR_USERNAME_).
- `_appendEnvLines(charId)` — uses `applyUpdates` from `env-parser.ts` to add char lines.
- `_removeEnvLines(charId)` — removes the same 4 lines (preserves all other order).

`writeCharacter` flow:
1. Validate via ajv (errors → throw 422).
2. Backup 3 files.
3. Write 3 files atomically.
4. Return backup paths + ajv warnings (if any).

`deleteCharacter` flow:
1. `mkdir platform/data/backups/deleted/<charId>.<ts>/`.
2. Move 3 JSON files into that dir (preserve original filenames).
3. `_removeEnvLines(charId)` (with .env auto-backup).
4. Return backup dir path.

---

## 6. `lib/ajv.ts` + `char-schema.ts`

```ts
// ajv.ts
import Ajv from "ajv";
import schema from "@/character_card_schema.json"; // imported via tsconfig path mapping

const ajv = new Ajv({ allErrors: true, strict: false });
export const validatePersona = ajv.compile(schema);
```

`char-schema.ts` exports type-safe field metadata for the form generator:

```ts
export type FieldDef = {
  key: string;
  label: string;
  description?: string;
  required: boolean;
  widget: "text" | "textarea" | "monaco" | "chips" | "kv" | "trigger-list" | "stat-limits";
  multiline?: boolean;
  placeholder?: string;
};

export const PERSONA_FIELDS: FieldDef[] = [
  { key: "name", label: "Name", required: true, widget: "text" },
  { key: "profile_summary_ko", label: "Profile summary", widget: "textarea" },
  { key: "description", label: "Description", required: true, widget: "textarea", multiline: true },
  { key: "personality", label: "Personality", widget: "textarea" },
  { key: "scenario", label: "Scenario", widget: "textarea" },
  { key: "first_mes", label: "First message", required: true, widget: "textarea", multiline: true },
  { key: "mes_example", label: "Example messages", widget: "monaco" },
  { key: "system_prompt", label: "System prompt", required: true, widget: "monaco" },
  { key: "post_history_instructions", label: "Post-history instructions", widget: "textarea" },
  { key: "creator_notes", label: "Creator notes", widget: "textarea" },
  { key: "anchor_image", label: "Anchor image filename", widget: "text" },
  { key: "image_prompt_prefix", label: "Image prompt prefix", widget: "textarea" },
  { key: "image_negative_prefix", label: "Image negative prefix", widget: "textarea" },
  { key: "stat_personality", label: "Stat personality", widget: "textarea" },
  { key: "stat_moods", label: "Allowed moods", widget: "chips" },
  { key: "proactive_behaviors", label: "Proactive behaviors", widget: "textarea" },
  { key: "interests", label: "Interests", widget: "chips" },
  { key: "discovery_hint_template", label: "Discovery hint template", widget: "text" },
  { key: "mood_behaviors", label: "Mood-specific behaviors", widget: "kv" },
  { key: "mood_triggers", label: "Mood triggers", widget: "trigger-list" },
  { key: "stat_limits", label: "Stat limits", widget: "stat-limits" },
  { key: "jobs", label: "Jobs", widget: "chips" },
];

// behaviors and images files are simpler — separate field defs
```

The `images/charNN.json` schema is small (char_id + appearance/clothing tags + body_shape object + breast object). Use a separate `IMAGES_FIELDS` definition.

The `behaviors/charNN.json` schema (`proactive_behavior` array of `{condition, prompt}` objects) needs custom widget — `tier-list`.

---

## 7. API routes

### `GET /api/characters`
```json
{ "characters": [{ "charId": "char05", "name": "Jiwon Han", "profile_summary_ko": "...", "mtime": 1745... }] }
```

### `POST /api/characters`
Body: `{ "from"?: "charXX" }` (optional duplicate source).
Creates new charNN with seed template (or copy of source).
Returns `{ "charId": "char01", "backup_paths": [], ".env_updated": true }`.

### `GET /api/characters/[charId]`
Returns the full 3-file bundle.

### `PUT /api/characters/[charId]`
Body: `{ persona, behaviors, images }` — all 3 must be present (whole-file replace, not key-merge — simpler semantics for character editing).
Validates → backup → write → returns `{ ok, backup_paths: 3, warnings }`.

### `DELETE /api/characters/[charId]`
Soft-delete: backup dir + remove + .env line removal.
Returns `{ ok, backup_dir, env_backup_path }`.

### `POST /api/characters/[charId]/duplicate`
Allocates next free charNN, copies 3 files, renames `name → "Copy of <name>"`, clears `anchor_image`.
Returns `{ charId: "charXX" }`.

Errors: 404 UNKNOWN_CHARACTER, 409 ALREADY_EXISTS (on POST when charNN already taken), 422 INVALID_CARD (ajv error), 500 CHAR_WRITE_FAILED.

---

## 8. UI

### `/characters` (list)
```
┌──────────────────────────────────────────────────────┐
│ Characters                       [ + New character ] │
│ ──────────────────────────────────────────────────── │
│ ┌──────────────────────────────────────────────────┐ │
│ │ char05 — Jiwon Han                                │ │
│ │ Composed 31-y/o executive assistant…              │ │
│ │ 10 Apr 11:23  [ Edit ] [ Duplicate ] [ ⋯ Delete ] │ │
│ └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- Card per character with name + summary + mtime.
- "+ New character" button → calls POST `/api/characters` → routes to `/characters/<newId>`.
- Delete confirmation via shadcn AlertDialog (or reuse Dialog).

### `/characters/[charId]` (editor)
```
┌────────────────────────────────────────────────────────┐
│ char05 — Jiwon Han                  [ Form | Raw JSON ]│
│ ─────────────────────────────────────────────────────── │
│ Persona  ●dirty                                         │
│ ┌────────────────────────┬──────────────────────┐      │
│ │ [scrollable form]      │ first_mes preview    │      │
│ │ Name: [...]            │ ────────────────     │      │
│ │ Description: [...]     │ rendered markdown    │      │
│ │ ...                    │ "User" / "Jiwon"     │      │
│ └────────────────────────┴──────────────────────┘      │
│ Behaviors  ●dirty                                       │
│ Images                                                  │
│ [ Validate ] [ Save all ]                               │
└────────────────────────────────────────────────────────┘
```

- Sections collapsed by file (Persona / Behaviors / Images) using `<details>` or shadcn Accordion.
- Per-section dirty indicator.
- Bottom button: Save all → PUT `/api/characters/[charId]` with all 3 files (whole-bundle write).
- "Form | Raw JSON" toggle at top: switches the entire page between auto-form and 3-Monaco view.
- Validate button: explicit ajv dry-run, shows toast with errors / warnings.

---

## 9. Test scenarios (manual)

1. **List**: `/characters` → 1 card (char05 Jiwon Han) shown with mtime + summary.
2. **Edit form load**: click Edit → `/characters/char05` → form loads with values from disk.
3. **Form edit + save**: change `personality` → ●dirty → Save → toast with 3 backup paths → values persist on reload.
4. **Validation error**: clear `name` (required) → Save → 422 toast "name: required".
5. **Raw JSON mode**: toggle to Raw → 3 Monaco editors per file → edit `system_prompt` → Save → new content on disk.
6. **Create new**: `+ New character` → next free charNN allocated (char01) → blank template seeded → 3 files exist + .env has 4 new lines (TEST_/PROD_ × CHAR_BOT_/CHAR_USERNAME_).
7. **Duplicate**: `Duplicate` on char05 → new char01 (or whatever's free) → 3 files copied → name = "Copy of Jiwon Han" → anchor_image cleared.
8. **Delete**: Delete on a test char → soft-delete dir created `platform/data/backups/deleted/char01.<ts>/` → 3 files moved → 4 .env lines removed.
9. **first_mes preview**: edit first_mes with `{{user}}` macro → preview panel shows substituted text.
10. **mtime sort**: list ordering by most-recently-modified file.
11. **No char available** (after deleting char05): list page shows empty state with Create button.
12. **Bot restart toast**: after every Save / Create / Delete, toast with "Restart bot to apply" + Dashboard action.

---

## 10. Risks / decisions deferred

### Risk: ajv strict-mode errors with the existing schema
- Current schema uses `additionalProperties: false` which ajv enforces strictly. Existing char05 should pass; verified during commit 2.

### Risk: charNN slug collision after delete
- If user deletes char01 then creates new char01, the soft-delete dir has `char01.<old_ts>/` — no collision since the dir name has a timestamp suffix.

### Risk: mood_triggers / mood_behaviors widget complexity
- Custom widgets with add/remove rows add ~200 LOC. Mitigated by keeping list-of-objects simple (no nested objects beyond 1 level).

### Deferred
- Image upload + ComfyUI input dir sync — M4.
- Test-message panel that calls Grok — likely never (chat is in Telegram, not webapp).
- Bot auto-reload on character change — would need IPC to running bot. Out of scope.
- Card export as PNG (SillyTavern format) — out of scope.

---

## 11. Commit plan

| # | Message | Content |
|---|---|---|
| 1 | `chore(platform): add ajv + react-markdown + remark-gfm` | npm install + package.json |
| 2 | `feat(platform): lib/{ajv,characters,char-schema}.ts` | data layer + ajv compile |
| 3 | `feat(platform): /api/characters routes (list/create/get/put/delete/duplicate)` | 6 API endpoints |
| 4 | `feat(platform): components/ui/textarea + alert-dialog primitives` | shadcn primitives |
| 5 | `feat(platform): /characters list page (cards + create/duplicate/delete actions)` | list UI |
| 6 | `feat(platform): /characters/[charId] form editor (auto-generated form + first_mes preview)` | edit UI form |
| 7 | `feat(platform): /characters/[charId] Raw JSON mode (3-Monaco view)` | edit UI raw |
| 8 | `feat(platform): enable /characters in sidebar` | sidebar wiring |
| 9 | `docs(M3): platform/CLAUDE.md + STATUS.md + root CLAUDE.md` | merge prep |

---

## 12. develop merge checklist

- [ ] All 12 test scenarios PASS.
- [ ] `npx tsc --noEmit` — 0 errors.
- [ ] `STATUS.md` updated (M3 done + M4 next).
- [ ] `platform/CLAUDE.md` table updated, M3 modules listed.
- [ ] Root `CLAUDE.md` Implementation Status row added.
- [ ] `behaviors/CLAUDE.md` / `persona/CLAUDE.md` / `images/CLAUDE.md` — char list updated if any new sample chars were created during testing.
- [ ] If test characters were left behind, soft-delete them so the merged tree still ships only `char05` as the sample.
