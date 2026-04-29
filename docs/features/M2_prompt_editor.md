# M2 — Prompt editor (`grok_prompts.json` + `system_prompt.json`)

> **Branch**: `feat/feature_M2_prompt_editor`
> **Status**: Plan only — awaiting PM sign-off.
> **Parent plan**: [plan.md §4.3](../../plan.md), [plan.md §8 M2](../../plan.md)
> **Estimate**: 1 day

---

## 1. Goals

### Done criteria
1. `/prompts` page with two tabs: **Grok prompts** (5 keys) + **System prompt** (2 keys).
2. Each key uses Monaco editor (full VS Code-style: line numbers, find, multi-cursor, keyboard).
3. **Validation on save**:
   - Both files: JSON parse must succeed.
   - `grok_prompts.json`: every required key present (`system`, `video_analyzer`, `random`, `classify`, `partial_edit`); none empty.
   - `system_prompt.json`: required keys (`master_prompt`, `image_signal_format`); none empty.
   - **`${var}` placeholder lint** — show warning (not error) when placeholders inside grok prompts look malformed (e.g. `$ {var}`, `${`, mismatched braces).
4. **Auto-backup** on save — `platform/data/backups/<file>.<KST>.bak` (same mechanism as M1's `.env`).
5. **Diff viewer** — side-by-side or inline diff between disk version and editor draft, before saving.
6. **Restart-required toast** with Dashboard shortcut (same UX as `/env`).

### Out-of-scope
- Hot reload of prompts in the live bot (bot still requires process restart).
- WebSocket-based collaborative editing.
- Audit log of prompt changes (M2 saves to backup folder only; full audit via SQLite is M5+).
- Image config (`sfw_scenes.json` etc.) — those go to M4.

---

## 2. ★ PM decisions (answer before implementation)

### #1 — Editor library: Monaco vs CodeMirror
- **A (recommended)**: `@monaco-editor/react` — VS Code-equivalent UX, mature, large bundle.
- **B**: `@uiw/react-codemirror` — lighter, less feature-rich.
- Plan §4.3 explicitly says Monaco. Recommend A unless PM has bundle-size concern.

### #2 — Save granularity: per-key or whole-file
- **A (recommended)**: per-key save — each Monaco editor has its own dirty state + Save button. Less risk of clobbering unrelated keys.
- **B**: whole-file Save — single button saves all 5 keys at once.
- Recommend A — more granular undo. PUT body still accepts `{updates: {key: value}}` shape.

### #3 — Diff viewer trigger
- **A (recommended)**: explicit "Preview diff" button — opens modal with diff before saving.
- **B**: inline diff always shown — uses more screen space.
- **C**: no diff viewer (raw save) — simplest but riskier.
- Recommend A.

### #4 — Lint policy on placeholder mismatch
- **A**: warn (allow save) — list malformed placeholders below editor as warnings.
- **B**: hard block (refuse save) — placeholder must be valid `${name}` form.
- Recommend A — over-strict lint blocks legitimate prompt iteration.

---

## 3. Directory structure (M2 additions)

```
platform/
├── app/
│   ├── prompts/
│   │   ├── page.tsx                # ★ M2 — server entry
│   │   ├── prompts-page.tsx        # ★ client wrapper with tabs
│   │   ├── prompt-editor.tsx       # ★ shared Monaco-wrapper component
│   │   └── diff-modal.tsx          # ★ diff preview modal
│   └── api/
│       └── prompts/
│           ├── grok/route.ts       # ★ M2 — GET / PUT
│           └── system/route.ts     # ★ M2 — GET / PUT
├── components/ui/
│   └── dialog.tsx                  # ★ M2 — shadcn primitive (Radix Dialog) for diff modal
└── lib/
    ├── prompts.ts                  # ★ M2 — loaders + validators + placeholder lint
    └── (no SQLite changes — M2 doesn't add tables)
```

Backup files land in the same `platform/data/backups/` directory used by M1, with file-prefix differentiating `.env`, `grok_prompts.json`, `system_prompt.json`.

---

## 4. New libraries

- `@monaco-editor/react` (Monaco wrapper for React/Next.js — already includes Monaco editor).
- `@radix-ui/react-dialog` (shadcn Dialog primitive — used for diff preview modal).
- `react-diff-viewer-continued` (active fork of `react-diff-viewer`, supports React 18).

Install: `cd platform && npm install @monaco-editor/react @radix-ui/react-dialog react-diff-viewer-continued`

---

## 5. `lib/prompts.ts` design

```ts
export const GROK_PROMPT_KEYS = ["system", "video_analyzer", "random", "classify", "partial_edit"] as const;
export const SYSTEM_PROMPT_KEYS = ["master_prompt", "image_signal_format", "image_signal_regex"] as const;

export type PromptFile = "grok" | "system";

export async function readPromptFile(file: PromptFile): Promise<Record<string, string>>;
export async function writePromptFile(file: PromptFile, contents: Record<string, string>): Promise<{ backup_path: string }>;

export type LintIssue = { key: string; severity: "warning" | "error"; message: string };
export function lintPlaceholders(value: string): LintIssue[];
export function validatePayload(file: PromptFile, contents: Record<string, string>): LintIssue[];
```

- `readPromptFile`: reads + parses JSON, returns string-valued keys only (e.g. drops `image_signal_regex` if it's a regex object — preserve roundtrip though).
- `writePromptFile`: validates → backup current file → write new content with `JSON.stringify(merged, null, 2)`.
- `validatePayload`: checks required keys, non-empty strings, JSON serializability.
- `lintPlaceholders`: regex scans for `\$\{[A-Za-z_][A-Za-z0-9_]*\}` (good) and flags `\$\{[^}]*$` (unterminated) or `\$\s+\{` (space inside) etc.

The `image_signal_regex` field in `system_prompt.json` is **not** a multi-line prompt — it's a small regex string. Surface it in the editor but with a small `<Input>` rather than Monaco (or skip if PM prefers).

---

## 6. API routes

### `GET /api/prompts/grok`
Returns:
```json
{
  "keys": [
    { "name": "system", "value": "...", "size": 11038 },
    { "name": "video_analyzer", "value": "...", "size": 4510 },
    ...
  ]
}
```

### `PUT /api/prompts/grok`
Body:
```json
{ "updates": { "system": "new content", "random": "new content" } }
```
Validates → backup → write → response:
```json
{ "ok": true, "restart_required": true, "backup_path": "platform/data/backups/grok_prompts.json.20260429-120000.bak", "warnings": [{...}] }
```

### `GET /api/prompts/system`
Returns the 3 string keys (`master_prompt`, `image_signal_format`, `image_signal_regex`).

### `PUT /api/prompts/system`
Same validate → backup → write pattern.

Errors: 400 BAD_REQUEST (malformed JSON), 422 EMPTY_KEY / MISSING_REQUIRED_KEY / INVALID_PAYLOAD, 500 PROMPT_WRITE_FAILED.

---

## 7. UI

### `/prompts` page

```
┌──────────────────────────────────────────────────────┐
│ Prompts                                               │
│ ──────────────────────────────────────────────────── │
│ [ Grok prompting ]  [ System prompt ]                │
│                                                       │
│ Key: [ system ▼ ]   size: 11038 chars  ●dirty       │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Monaco editor — full screen vertical, ~80vh tall │ │
│ │ ...                                              │ │
│ └──────────────────────────────────────────────────┘ │
│ [ Preview diff ]  [ Save ]   warning: ${foo missing │
│                              closing brace at line 4│
└──────────────────────────────────────────────────────┘
```

- Top-level `<Tabs>` choosing file (grok / system).
- Within each file tab, a key selector (`<Tabs>` again, or `<Select>` if 5 is too many).
- `prompt-editor.tsx` mounts Monaco, tracks dirty state, debounce-runs `lintPlaceholders` for warnings.
- `diff-modal.tsx`: opens Radix Dialog on "Preview diff" click. Body uses `react-diff-viewer-continued` showing `original_value` → `current_draft`. "Save" inside modal commits.
- Toast (sonner) on success: "Saved <file>. Restart bot to apply." with Dashboard action.

### Sidebar
Enable `/prompts` link (currently `enabled: false`).

---

## 8. Test scenarios (manual)

1. **Cold load**: `/prompts` → loads `grok_prompts.json` → Monaco editor renders `system` content (~11k chars). No errors.
2. **Edit + dirty indicator**: type one char in `system` → tab marker shows ●dirty. Switch tab to `video_analyzer` → that tab is clean. Switch back → edit preserved.
3. **Lint warning**: insert `${foo` (unterminated) into `random` → warning panel below editor lists "line N: unterminated placeholder". Save still allowed (warning, not error).
4. **Empty key block**: clear `system` → save → 422 EMPTY_KEY → toast error.
5. **Missing required key**: send PUT body without `system` → 422 MISSING_REQUIRED_KEY (curl test).
6. **Diff modal**: dirty `system` → Preview diff → modal shows red/green diff vs disk version. Save inside modal → backup created + toast.
7. **Backup verification**: `ls platform/data/backups/grok_prompts.json.*.bak` → file exists with same length as previous disk content.
8. **System prompt edit**: switch to System prompt tab → edit `master_prompt` → save → toast + backup.
9. **Restart toast action**: after save → toast has "Go to Dashboard" button → click → routes to /dashboard with bot status visible.
10. **Concurrent edit lock (optional)**: skipped for M2 — single-admin assumption (#9.4 127.0.0.1 only).
11. **127.0.0.1 only**: external `curl http://<lan>:9000/api/prompts/grok` rejected.

---

## 9. Risks / decisions deferred

### Risk: Monaco bundle size
- `@monaco-editor/react` lazy-loads Monaco core; bundle size for the prompts page only. Initial load may be slow (~1MB). Mitigated by Next.js code-splitting (Monaco is dynamic-imported).

### Risk: Long string round-trip
- `system` is ~11k chars. JSON.stringify with `null, 2` → multi-line formatting. The bot loader reads via `string.Template` which only cares about `${var}` placeholders, not formatting. Safe.

### Risk: Lint false positives
- `${var}` patterns may legitimately appear in Korean / English text (rare). Lint runs on save preview, warns only. Save allowed.

### Deferred
- Per-prompt audit log in `platform.sqlite` — M5+.
- Hot reload of prompts in running bot — would require IPC or file-watch in `src/grok.py`. Not in scope; bot restart is required.
- Showing "fields used by which call" cross-reference — possibly helpful but extra work.

---

## 10. Commit plan

| # | Message | Content |
|---|---|---|
| 1 | `chore(platform): add Monaco + Dialog + diff-viewer deps` | npm install + package.json |
| 2 | `feat(platform): lib/prompts.ts (read/write/validate/lint)` | lib + tests via smoke |
| 3 | `feat(platform): /api/prompts/{grok,system} routes` | 4 API endpoints |
| 4 | `feat(platform): Dialog primitive` | components/ui/dialog.tsx |
| 5 | `feat(platform): /prompts page + Monaco editor + diff modal` | full UI |
| 6 | `feat(platform): enable /prompts in sidebar + restart toast` | sidebar wiring |
| 7 | `docs(M2): platform/CLAUDE.md + STATUS.md + root CLAUDE.md` | merge prep |

---

## 11. develop merge checklist

- [ ] All test scenarios (§8) PASS.
- [ ] `npx tsc --noEmit` — 0 errors.
- [ ] `STATUS.md` updated (M2 done + M3 next).
- [ ] `platform/CLAUDE.md` table updated, M2 modules + Dialog primitive added.
- [ ] Root `CLAUDE.md` Implementation Status row added.
- [ ] `platform/data/backups/` confirmed to accept new `grok_prompts.json.*.bak` and `system_prompt.json.*.bak` files.
