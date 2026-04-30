# M5 — Workflows + Logs

> **Branch**: `feat/feature_M5_workflows_logs`
> **Status**: Plan only — awaiting PM sign-off.
> **Parent plan**: [plan.md §4.5 + §8 M5](../../plan.md)
> **Estimate**: 2 days

---

## 1. Goals

### 1a. `/workflows`
Replace the placeholder. Manage the 3 ComfyUI workflow JSONs in `comfyui_workflow/`:
- `main_character_build.json` — primary `/random` SFW + chat image-gen
- `main_character_build_highqual.json` — `/highqual` button (more steps)
- `main_character_build_archived.json` — rollback snapshot

**What admins actually need (per CLAUDE.md note "prefer editing through ComfyUI UI"):**
1. **See** which workflow is currently active for image-gen.
2. **View** the node graph of each workflow (read-only, formatted JSON).
3. **Edit a small set of safe parameters** without touching graph topology — checkpoint, sampler steps/cfg/seed, save-filename prefix.
4. **Replace** an entire workflow JSON when the user has just exported an updated one from ComfyUI's "Save (API Format)".
5. **Atomic write + auto-backup** on every save.
6. **Bot restart required** toast (same as M1/M2/M3/M4 pattern).

### 1b. `/logs`
Replace the placeholder. Full-page log viewer.
- Read `logs/bot.log` (current) + dated archives (`bot.log.YYYY-MM-DD`).
- Tail size up to 5000 lines; default 1000.
- Polling-based streaming (1s interval — fits the existing pattern, no SSE/WebSocket added).
- Client-side regex filter (case-insensitive).
- Archive picker (dropdown of available log files).
- Pause / resume button.
- Download raw log button.
- Auto-scroll toggle (already in dashboard log-tail).

### Done criteria
1. `/workflows` page lists the 3 workflows with active indicator + per-workflow Raw JSON viewer + safe-fields form + Replace-from-paste button + Save w/ backup.
2. `/logs` page shows full-screen log viewer with archive picker, regex filter, polling toggle, download.
3. Sidebar `/workflows` and `/logs` enabled.
4. Existing dashboard log-tail card stays as-is (200 lines, 5s polling) — `/logs` complements it.

### Out-of-scope
- Editing the workflow node graph topology (add/remove nodes / rewire). User does this in ComfyUI desktop, exports JSON, pastes into the Replace dialog.
- Per-environment workflow profiles (one node-graph per character / per scene).
- Live SSE/WebSocket streaming — polling 1s is enough for log volume.
- Workflow git integration / versioning beyond `*.bak` files.
- Log alerting / Pattern matching (warn on N errors per minute).
- Combined log search across multiple archives.
- Archive rotation policy management (user manages from shell).

---

## 2. ★ PM decisions (answer before implementation)

### #1 — Workflow editing UX
- **A (recommended)**: 3 panels per workflow:
  1. **Form** — safe fields only (checkpoint name dropdown if we can list, else free text; KSampler `seed` / `cfg` / `steps` / `sampler_name` / `scheduler`; SaveImage `filename_prefix`).
  2. **Raw JSON** — Monaco read-only **viewer** for the full node graph (admins look up node ids, debug).
  3. **Replace** — paste-textarea + "Validate & Replace" button. Parses JSON, runs minimal sanity check (must have `class_type` on every key, must contain a CheckpointLoaderSimple), backs up, writes.
- **B**: Form-only — strip Replace, edit only safe fields. Simpler but no path to update from a fresh ComfyUI export.
- **C**: Raw JSON edit-anything — Monaco read-write, no form, no Replace. Most flexible but easiest to break the graph.

Recommend A — covers the day-to-day knob-tuning (Form), debugging (Raw JSON viewer), and the "I just exported a new workflow" path (Replace). No accidental graph edits.

### #2 — Stage → workflow assignment ★ EXPANDED PER PM REQUEST
The bot has **2 active rendering stages** today:

| Stage | Caller | Current binding |
|---|---|---|
| **Standard** | `/random` SFW + character-card / chat image-gen (default) | `comfyui.py:19` `DEFAULT_WORKFLOW_PATH = "comfyui_workflow/main_character_build.json"` — already overridable via `COMFYUI_WORKFLOW` env var (`comfyui.py:244`). |
| **HQ** | When the user has toggled `/hq on` (`hq_mode` session flag — see `handlers_imagegen.py:565`, `:704`, `:783`, `:848`) | `handlers_imagegen.py:122` `_HQ_WORKFLOW = "comfyui_workflow/main_character_build_highqual.json"` — currently hardcoded. |

`main_character_build_archived.json` is rollback-only and not loaded at runtime.

PM wants the stage→file mapping to be admin-configurable in `/workflows`, with the differences between the assigned files visible.

- **A**: leave hardcoded.
- **B (chosen — per PM request)**: expose two env vars and surface them as dropdowns on `/workflows`:
  - `COMFYUI_WORKFLOW` (already exists — Standard stage)
  - `COMFYUI_WORKFLOW_HQ` (★ new — HQ stage; `handlers_imagegen.py:122` reads it via `os.getenv("COMFYUI_WORKFLOW_HQ", "comfyui_workflow/main_character_build_highqual.json")`)

  UI: a top-of-page **Stage assignments** card with 2 selects — Standard, HQ — both populated from the file list. Same file may back both stages (e.g. point HQ at standard during testing). Save writes to `.env` via the existing `applyUpdates`. Backed by the same backup pipeline as `/env`. Restart-required toast.

- **C**: full UI picker (no env vars; bespoke `config/workflow_assignments.json`).

**Chosen: B**. Reuses `.env` infra, keeps the "value lives in environment" model consistent with everything else admin-editable. The new `COMFYUI_WORKFLOW_HQ` requires a one-line change in `handlers_imagegen.py` (turn the hardcoded constant into a getenv).

**Tradeoff**: archived is excluded from the dropdown (unsafe to bind to live stage). User can still inspect / edit it via the per-file tabs.

### #2b — How to show "what's different" between HQ and Standard
- **A (recommended)**: each workflow tab shows an **auto-computed facts block** + an admin-editable **description** field. Auto facts:
  - Node count
  - Total `KSampler.steps` (sum across all sampler nodes)
  - Refiner / upscaler presence (any node whose `class_type` matches `^(KSamplerAdvanced|.*Upscale.*|UltimateSDUpscale.*)$` — flag yes/no)
  - File size (KB)
- Per-file description: stored in **`config/workflow_descriptions.json`** (new file — loaded read-only by the bot but editable in UI). Schema:
  ```json
  {
    "_doc": "Free-form description shown next to each comfyui_workflow/*.json in the platform admin.",
    "main_character_build.json": "Default 24-step Illustrious render. Used for standard /random rolls and chat image-gen.",
    "main_character_build_highqual.json": "38-step Illustrious + refiner. ~2.5× slower than standard.",
    "main_character_build_archived.json": "Pre-rev rollback snapshot. Not loaded at runtime."
  }
  ```
- **B**: store description inside each workflow JSON's `_meta.description`. Less clean — pollutes the ComfyUI-exported file.
- **C**: skip; show only auto facts.

Recommend A — admins know best whether a workflow is "fast" / "experimental" / "blocked on a fix"; auto facts can't replace that.

### #3 — Embedding prefix exposure
`src/comfyui.py:47-48` hardcodes `EMBEDDING_POS_PREFIX` / `EMBEDDING_NEG_PREFIX`. Today only editable via Python source.

- **A (recommended)**: leave in Python source for M5. The fork's SFW invariant lives there (lazynsfw moved to negative). Adding UI to edit it = trivial path to break the SFW guard.
- **B**: move to `.env` as `COMFYUI_EMBEDDING_POS_PREFIX` + `COMFYUI_EMBEDDING_NEG_PREFIX`, surfaced in the existing /env "ComfyUI" tab. Editable but at least visible.
- **C**: dedicated panel in `/workflows`.

Recommend A — keep the SFW guard in source where it requires a code review to alter. Optional follow-up: surface the values **read-only** on `/workflows` so admins know what's prefixed onto every render.

### #4 — Log streaming mechanism
- **A (recommended)**: polling — 1s interval on `/logs`, 5s on `/dashboard` (already in place). Same `/api/bot/logs` endpoint, just different `tail` param.
- **B**: SSE (Server-Sent Events) — new `/api/bot/logs/stream` route, simpler than WebSocket but still adds complexity.
- **C**: WebSocket.

Recommend A — bot logs are low-volume (≤ a few hundred lines/min). 1s polling reads the same 1MB window each tick; cheap and dead-simple. SSE only buys responsiveness we don't need.

### #5 — Log filtering
- **A (recommended)**: client-side regex filter — applied to the visible tail buffer. Fast, no server changes. Works fine for a 1k-line buffer. Highlights matched substrings.
- **B**: server-side grep — `?q=...` query param that filters before returning. Faster for large archives but more code.
- **C**: no filter.

Recommend A — the file is ~MB-scale and the client buffer is bounded. If the buffer ever blows past 5k lines we can revisit.

### #6 — Archive switching
- **A (recommended)**: dropdown listing `bot.log` plus dated `bot.log.YYYY-MM-DD` files (descending). Server returns the file list via the same `/api/bot/logs` route extended with a `?file=` param (whitelist-validated to prevent path traversal).
- **B**: `bot.log` only (current archives via shell).

Recommend A — small server-side change, big quality-of-life improvement when tracing yesterday's incident.

### #7 — `/logs` polling interval default
- **A (recommended)**: 1s default, with 1s / 2s / 5s / paused selector.
- **B**: 5s fixed.

Recommend A — 1s feels live without overloading; the selector lets admins pause when reading carefully.

### #8 — Workflow placeholder handling on Replace ★ DECIDED: B
ComfyUI workflows depend on two literal placeholder tokens that the runtime
substitutes:
- node `4` (`CLIPTextEncode`, title "Positive") `inputs.text` must contain `%prompt%`
- node `5` (`CLIPTextEncode`, title "Negative") `inputs.text` must contain `%negative_prompt%`

[src/comfyui.py:121-122](../../src/comfyui.py#L121) calls `str.replace("%prompt%", …)` —
if the placeholder is missing, the replacement is a silent no-op and every
render uses whatever literal prompt happened to be in the file (broken).

Pasting a fresh export from ComfyUI's "Save (API Format)" UI will NOT contain
those tokens — it'll contain whatever the user last typed in the Positive /
Negative nodes when they exported.

- **A**: auto-rewrite — Replace silently overwrites `text` of the matching nodes with the placeholder strings.
- **B (chosen)**: validate + reject — Replace returns 422 `PLACEHOLDER_MISSING` if either token is absent. UI surfaces a clear hint: "Positive node `text` must contain `%prompt%` and Negative node `text` must contain `%negative_prompt%`. Edit the JSON before pasting."
- **C**: hybrid (auto-rewrite checkbox).
- **D** (deferred follow-up): change `inject_prompts()` in `src/comfyui.py` to locate Positive / Negative nodes by `_meta.title` + `class_type` and assign directly, eliminating the placeholder convention entirely. Out of scope for M5 — touches runtime image-gen and risks changing render semantics.

**Rationale for B**: stricter is better here. The cost of accidentally shipping a workflow with no placeholders is silently-broken renders; the cost of a 422 is one edit + re-paste. A clear error message keeps the contract explicit.

---

## 3. Per-page UX detail

### 3a. `/workflows` — page layout

```
┌─ Workflows (page header)
│
├─ Stage assignments card (top of page)
│   ┌─ Standard stage  — Select  [main_character_build.json ▾]   reads/writes COMFYUI_WORKFLOW
│   ├─ HQ stage        — Select  [main_character_build_highqual.json ▾]   reads/writes COMFYUI_WORKFLOW_HQ
│   └─ "Save assignments" button → backs up .env, writes both keys.
│       Diff hint: "Standard ↔ HQ identical" or "HQ overlay = +N nodes / +M sampler steps / refiner: yes"
│
├─ Tabs: [main_character_build] [main_character_build_highqual] [main_character_build_archived]
│
│ For the active tab:
│ ┌─ Tab header
│ │  Title · file path · "Standard"/"HQ"/"Both"/"Unused" badge based on stage assignment
│ │  Last backup at … · file size · N nodes
│ ├─ Auto facts block:
│ │  Node count · Σ KSampler.steps · Refiner present? · File size
│ ├─ Description textarea (sourced from config/workflow_descriptions.json)
│ │  "Save description" button
│ ├─ Inner tabs: [Form] [Raw JSON] [Replace]
│ ├─ Form tab:
│ │   Checkpoint (text input)
│ │   KSampler — seed (number) / cfg (number) / steps (number) / sampler (text) / scheduler (text)
│ │   SaveImage — filename_prefix (text)
│ │   "Save form fields" button
│ ├─ Raw JSON tab: read-only Monaco (65vh)
│ └─ Replace tab:
│     Big textarea — paste JSON exported from ComfyUI's "Save (API Format)"
│     Live "Parse OK" / parse error indicator
│     "Validate & Replace" button — checks shape (every value has class_type, has at least one CheckpointLoaderSimple, %prompt% + %negative_prompt% placeholders present), backs up, writes
└─
```

Form tab implementation note: each safe field maps to a fixed node id (the IDs are stable across our 3 workflows: `2` = checkpoint, `119` = KSampler, `30` = SaveImage). Code uses the `_meta.title` + `class_type` to find them rather than hardcoding numeric ids. If a node is missing, the field is hidden.

### 3b. `/logs` — page layout

```
┌─ Logs (page header)
├─ Toolbar
│   ├─ File picker dropdown — bot.log / bot.log.2026-04-27 / bot.log.2026-04-28 / …
│   ├─ Tail size selector — 200 / 500 / 1000 / 2000 / 5000 (default 1000)
│   ├─ Poll interval — 1s / 2s / 5s / Paused (default 1s)
│   ├─ Filter input — regex, case-insensitive, debounced 200ms
│   ├─ Auto-scroll checkbox
│   ├─ Download button — fetches raw file
│   └─ Refresh now button
├─ Log pane — pre, monospace, ~80vh, virtualized? (skip — even 5000 lines × 200 chars renders fine)
│   Highlight: matching lines have a subtle background tint; matching substrings are bold.
└─ Footer — line count · last fetch ts · "match: 23/1000"
```

---

## 4. Directory structure (M5 additions)

```
platform/
├── app/
│   ├── workflows/
│   │   ├── page.tsx                # server entry
│   │   ├── workflows-page.tsx      # client outer tabs + stage-assignments card
│   │   ├── stage-assignments.tsx   # ★ Standard / HQ dropdowns → COMFYUI_WORKFLOW{,_HQ}
│   │   ├── workflow-tab.tsx        # one tab body (facts + description + Form / Raw / Replace)
│   │   ├── workflow-form.tsx       # safe-field editor
│   │   ├── workflow-raw.tsx        # Monaco read-only viewer
│   │   ├── workflow-replace.tsx    # paste + validate + replace
│   │   └── workflow-facts.tsx      # auto facts block (node count / sampler steps / refiner / size)
│   ├── logs/
│   │   ├── page.tsx                # server entry
│   │   ├── logs-page.tsx           # client log viewer
│   │   └── logs-toolbar.tsx        # file picker + tail size + filter + interval
│   └── api/
│       ├── workflows/
│       │   ├── route.ts            # GET (list workflows + facts + stage badges)
│       │   ├── assignments/route.ts # ★ GET / PUT — Standard/HQ dropdowns → .env
│       │   ├── descriptions/route.ts # ★ GET / PUT — config/workflow_descriptions.json
│       │   └── [name]/route.ts     # GET / PUT (safe_fields | replace)
│       └── bot/logs/route.ts       # extended — accept ?file= param + ?listFiles=1
└── lib/
    ├── workflows.ts                # ★ new — read/write/backup + safe-field extraction + Replace validation + auto-facts
    └── log-files.ts                # ★ new — list bot.log + bot.log.YYYY-MM-DD
```

Plus a one-line bot-side change in `src/handlers_imagegen.py:122`:
```python
_HQ_WORKFLOW = os.getenv("COMFYUI_WORKFLOW_HQ", "comfyui_workflow/main_character_build_highqual.json")
```
And a new file at the repo root: `config/workflow_descriptions.json` (seeded with description text for the 3 existing workflows).

No new third-party libraries. Reuses Monaco / shadcn / sonner / Tabs / Select.

---

## 5. `lib/workflows.ts` design

```ts
export type WorkflowKey =
  | "main_character_build"
  | "main_character_build_highqual"
  | "main_character_build_archived";

export const WORKFLOW_KEYS: WorkflowKey[] = [
  "main_character_build",
  "main_character_build_highqual",
  "main_character_build_archived",
];

export const WORKFLOW_META: Record<
  WorkflowKey,
  { title: string; usedFor: string; isActive: boolean }
> = {
  main_character_build: {
    title: "Main character build",
    usedFor: "Default for /random SFW + chat image-gen",
    isActive: true,
  },
  main_character_build_highqual: {
    title: "High-quality variant",
    usedFor: "/highqual button",
    isActive: true,
  },
  main_character_build_archived: {
    title: "Archived snapshot",
    usedFor: "Rollback only — not loaded at runtime",
    isActive: false,
  },
};

export type SafeFields = {
  checkpoint: string | null;            // ckpt_name in CheckpointLoaderSimple
  ksampler: {
    seed: number;
    cfg: number;
    steps: number;
    sampler_name: string;
    scheduler: string;
  } | null;
  save_filename_prefix: string | null;  // SaveImage.filename_prefix
};

export async function readWorkflow(key: WorkflowKey): Promise<{ content: object; mtime: number; size_nodes: number; facts: Facts }>;
export async function writeWorkflowSafeFields(key: WorkflowKey, fields: Partial<SafeFields>): Promise<{ backup_path: string }>;
export async function replaceWorkflow(key: WorkflowKey, content: object): Promise<{ backup_path: string; warnings: string[] }>;
export function extractSafeFields(content: object): SafeFields;
export function validateWorkflowShape(content: unknown): { ok: true } | { ok: false; errors: string[] };

// ── auto-facts ──────────────────────────────────────────────────────────────
export type Facts = {
  node_count: number;
  sampler_steps_total: number;          // Σ KSampler.steps + Σ KSamplerAdvanced.steps
  has_refiner_or_upscaler: boolean;     // /^(KSamplerAdvanced|.*Upscale.*|UltimateSDUpscale.*)/.test(class_type)
  size_bytes: number;
};
export function computeFacts(content: object, size_bytes: number): Facts;

// ── stage assignment (env-backed) ───────────────────────────────────────────
export type StageAssignments = {
  standard: string;   // basename without dir, e.g. "main_character_build.json"
  hq: string;
  options: string[];  // basenames eligible for assignment (excludes *_archived.json)
};
export async function readStageAssignments(): Promise<StageAssignments>;
export async function writeStageAssignments(next: Partial<Pick<StageAssignments, "standard" | "hq">>): Promise<{ backup_path: string }>;

// ── per-file descriptions (config/workflow_descriptions.json) ───────────────
export async function readWorkflowDescriptions(): Promise<Record<string, string>>;
export async function writeWorkflowDescription(filename: string, description: string): Promise<{ backup_path: string }>;
```

**Shape validation**:
- Top-level must be an object whose values all have `class_type: string` + `inputs: object`.
- Must contain at least one `class_type === "CheckpointLoaderSimple"` node.
- **Must contain a Positive `CLIPTextEncode` node whose `inputs.text` contains the literal `%prompt%` token.** A node is "Positive" if `class_type === "CLIPTextEncode"` and `_meta.title === "Positive"` (case-sensitive). Failure → 422 `PLACEHOLDER_MISSING`.
- **Must contain a Negative `CLIPTextEncode` node whose `inputs.text` contains the literal `%negative_prompt%` token.** Same `_meta.title === "Negative"` rule. Failure → 422 `PLACEHOLDER_MISSING`.
- All numeric IDs (key strings) must be unique digit strings (informational warning if not, not blocking).

> Per PM decision #8, the Replace flow does NOT auto-rewrite missing placeholders — the user must edit the pasted JSON to include `%prompt%` / `%negative_prompt%` before saving. The error message includes the file location of the offending node id when available.

**Safe-fields write flow**:
1. Read current workflow.
2. For each provided field, locate the matching node by `class_type` + `_meta.title` (first match) and patch its `inputs.*`.
3. Backup + atomic write.

**Replace flow**:
1. Parse pasted text.
2. `validateWorkflowShape()` — must pass.
3. Backup + atomic write.
4. Return warnings (e.g., "checkpoint name changed from X to Y", "node count: 47 → 53").

---

## 6. `lib/log-files.ts`

```ts
export type LogFileInfo = {
  name: string;       // "bot.log" or "bot.log.2026-04-27"
  size: number;
  mtime: number;
  is_current: boolean;
};

export async function listLogFiles(): Promise<LogFileInfo[]>;
export function isAllowedLogFile(name: string): boolean;
```

`isAllowedLogFile` validates `name === "bot.log"` OR `name` matches `^bot\.log\.\d{4}-\d{2}-\d{2}$` to prevent path traversal.

---

## 7. `/api/bot/logs` extension

Existing route: `GET /api/bot/logs?tail=N` → `{ lines, note? }`. Extend to accept:

- `?file=bot.log.2026-04-27` — switch source file (whitelist-validated).
- `?listFiles=1` — return `{ files: LogFileInfo[] }` instead of lines.

Response stays backward-compatible. The dashboard log-tail keeps working unchanged.

---

## 8. API contracts

| Route | Method | Body / Query | Response | Errors |
|---|---|---|---|---|
| `/api/workflows` | GET | — | `{ workflows: { key, title, mtime, size_bytes, facts, description, stage_badges: ("standard"\|"hq")[] }[] }` | 500 |
| `/api/workflows/[name]` | GET | — | `{ key, content, mtime, facts, description, safe_fields, stage_badges }` | 404 UNKNOWN_WORKFLOW |
| `/api/workflows/[name]` | PUT | `{ kind: "safe_fields", fields: Partial<SafeFields> } \| { kind: "replace", content: object }` | `{ ok, backup_path, warnings? }` | 422 INVALID_SHAPE / NO_CHECKPOINT_LOADER / PLACEHOLDER_MISSING |
| `/api/workflows/assignments` | GET | — | `{ standard: filename, hq: filename, options: filename[] }` (options excludes `_archived`) | 500 |
| `/api/workflows/assignments` | PUT | `{ standard?, hq? }` | `{ ok, backup_path, restart_required: true }` | 422 UNKNOWN_FILE / INVALID_VALUE |
| `/api/workflows/descriptions` | GET | — | `{ content: { [filename]: string } }` | 500 |
| `/api/workflows/descriptions` | PUT | `{ filename, description }` | `{ ok, backup_path }` | 422 UNKNOWN_FILE / INVALID_PAYLOAD |
| `/api/bot/logs` (extended) | GET | `?file=&tail=&listFiles=` | `{ lines, note? } \| { files: LogFileInfo[] }` | 422 INVALID_FILE / 500 LOGS_FAILED |

All routes: `runtime = 'nodejs'`, `dynamic = 'force-dynamic'`.

---

## 9. UX details inherited from M2/M3/M4

- Page title + "Used by" line at the top of every workflow tab (M4 pattern).
- Save button disabled until dirty.
- Dirty indicator (•) on the tab label.
- Toast on save: `"Saved · restart bot to load"`.
- AlertDialog for "Replace will overwrite the entire workflow" confirmation.
- localStorage draft auto-save for the Replace textarea (so accidental nav doesn't lose paste).

---

## 10. Test scenarios (10)

> Run after implementation. Every scenario must PASS before merging to develop.

1. **List workflows** — `/workflows` opens, all 3 tabs render. The first 2 show "Active" badge.
2. **Read-only Raw JSON** — Raw JSON tab on each workflow renders Monaco; editing is disabled.
3. **Form: edit checkpoint** — change `ckpt_name` to `illustrious/foo.safetensors` → Save form fields → file updated; backup written; bot import test (`python -c "from src.comfyui import load_workflow; print(load_workflow()['2']['inputs']['ckpt_name'])"`) prints the new value.
4. **Form: edit KSampler steps** — change `steps` to 30 → Save → KSampler node updated; cfg / seed / etc. unchanged.
5. **Replace: valid paste** — paste a small modified workflow → Validate & Replace → confirm dialog → Save → file replaced; backup written.
6. **Replace: invalid JSON** — paste `{"bad":` → Parse error indicator shows; Replace button disabled.
7. **Replace: missing CheckpointLoaderSimple** — paste a JSON with no checkpoint loader → 422 NO_CHECKPOINT_LOADER; toast surfaces error.
7b. **Replace: missing `%prompt%` placeholder** — paste a JSON whose Positive node has `text: "1girl"` (no `%prompt%`) → 422 PLACEHOLDER_MISSING; error message names the offending node id and the missing token; file untouched.
7c. **Replace: missing `%negative_prompt%` placeholder** — same as 7b for the Negative node → 422 PLACEHOLDER_MISSING.
8a. **Stage assignment: HQ → standard file** — set HQ stage to `main_character_build.json` via dropdown → Save → `.env` now has `COMFYUI_WORKFLOW_HQ=comfyui_workflow/main_character_build.json`; restart-required toast; restart bot; `python -c "from src.handlers_imagegen import _HQ_WORKFLOW; print(_HQ_WORKFLOW)"` prints the new path.
8b. **Stage assignment: archived rejected** — try to set Standard or HQ to `main_character_build_archived.json` → dropdown excludes it; manual API PUT returns 422 UNKNOWN_FILE.
8c. **Stage badge** — after 8a, the `main_character_build.json` tab header shows both "Standard" + "HQ" badges; the HQ tab header shows "Unused".
9. **Description edit** — type "Test description" in the description textarea → Save → `config/workflow_descriptions.json` updated; backup written; reload page shows the new text.
10. **Auto facts** — verify the facts block shows correct node count + Σ KSampler steps + refiner detection for each of the 3 shipped workflows.
8. **Logs: archive switch** — pick `bot.log.2026-04-28` → contents change; `?file=bot.log.2026-04-28` is the network call.
9. **Logs: filter** — type `ERROR` in regex box → only matching lines visible; match count updates.
10. **Logs: pause / download** — Paused → no further fetches; Download → file streams as attachment.

---

## 11. Out-of-scope follow-ups (queue for after M5)

- `COMFYUI_DEFAULT_WORKFLOW` env var for runtime workflow switching (PM #2 option B).
- `COMFYUI_EMBEDDING_*` env-var exposure (PM #3 option B).
- **Title-based prompt injection** in `src/comfyui.py` (PM #8 option D) — locate Positive / Negative `CLIPTextEncode` nodes by `_meta.title` instead of relying on a `%prompt%` literal. Eliminates the placeholder-coupling between source files and runtime injection. Deferred per PM: too much risk of changing render semantics; revisit in a separate PR.
- Workflow versioning page (browse `*.bak` files in `platform/data/backups/`).
- Log alerting (e.g. notify-on-pattern Prometheus-style).
- SSE-based live log push (drop polling).

---

## 12. Open questions for PM

1. **#1 workflow editing UX**: A / B / C? (recommend A)
2. **#2 stage→workflow assignment**: ★ chosen B (env-var dropdowns for Standard + HQ on `/workflows`).
2b. **#2b how to show HQ vs Standard difference**: A / B / C? (recommend A — auto facts + admin description in `config/workflow_descriptions.json`)
3. **#3 embedding prefix exposure**: A / B / C? (recommend A — keep in Python)
4. **#4 log streaming**: A / B / C? (recommend A — polling)
5. **#5 log filtering**: A / B / C? (recommend A — client regex)
6. **#6 archive switching**: A / B? (recommend A — dropdown)
7. **#7 default poll interval on /logs**: A / B? (recommend A — 1s)
8. **#8 workflow placeholder handling on Replace**: ★ chosen B (validate + reject; no auto-rewrite). D deferred.
9. Anything else you want included before sign-off?
