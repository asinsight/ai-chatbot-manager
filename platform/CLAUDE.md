# `platform/` — Next.js admin webapp

Local admin console. Edits the operating configuration (`.env`, character
cards, prompt JSON, ComfyUI workflows, lorebook) and controls the bot
lifecycle (start / stop / restart). Binds to `127.0.0.1:9000` — never
exposed externally.

Per-milestone feature plans live in [`../docs/features/`](../docs/features/).

## Getting started

```
cd platform
npm install      # first time only
npm run dev      # http://127.0.0.1:9000
```

The Python interpreter used to spawn the bot process is read from the
project-root `.env` as `PYTHON_BIN` (absolute path recommended). Falls
back to `python3` on `PATH` when unset.

## Pages

| Page | Status |
|---|---|
| `/dashboard` | ✅ Bot status card + Connections health card + log tail (5s polling). Shows an amber warning banner with `Start` disabled when `MAIN_BOT_TOKEN` / `MAIN_BOT_USERNAME` are unset, plus a `/env?cat=tokens` deep-link. |
| `/connections` | ✅ 4 endpoint cards (ComfyUI / OpenWebUI / Grok / Prompt Guard) — URL+token edit + Ping + last-ping audit-log entry per endpoint + ping-all. |
| `/env` | ✅ 8 category tabs + per-category description + secret masking + auto-backup + default-value placeholders + Bot tokens grouping (Native / Character read-only with redirect). `MAIN_BOT_*` get a red `required` badge and Save is blocked until they're filled. `?cat=` URL parameter pre-selects the matching tab. Exposes `COMFYUI_WORKFLOW{,_HQ}` for workflow stage assignment. |
| `/prompts` | ✅ 3 outer tabs (Grok prompting / System prompt / Profile keys). Grok+System: Monaco 65vh + react-diff-viewer modal + per-key save + `${var}` placeholder lint + inline metadata. Profile keys: master-detail + chips. |
| `/characters` | ✅ List (cards + create + duplicate + delete with AlertDialog) + `/[charId]` editor (Form mode: Persona / Behaviors / Images / Bot tokens 4 inner tabs; Raw JSON mode: 3 Monaco editors). Draft auto-save (localStorage) + `first_mes` markdown preview + ajv validation + soft-delete. Read-only "View schema" Dialog mounts `character_card_schema.json` as a reference. |
| `/lorebook` | ✅ Mapping card (per-character dropdown ↔ `world_info/mapping.json`, "(legacy fallback)" option) + World list (Add / Duplicate / Delete with `WORLD_IN_USE` pre-warning) + World editor (Test pane mirrors `src/prompt.py _match_world_info()` + entry CRUD: keywords chips / content textarea / position background\|active select). |
| `/config` | ✅ 3 inner tabs (SFW scenes / Pose-motion presets / SFW denylist) — master-detail + chips + Raw JSON fallback + zod validation + auto-backup. |
| `/workflows` | ✅ Stage assignments (Standard / HQ ↔ `COMFYUI_WORKFLOW{,_HQ}` env) + per-workflow auto-facts (node count / Σ steps / refiner+detailer / size) + admin description (`config/workflow_descriptions.json`) + Form / Raw JSON / Replace 3 inner tabs. Replace enforces `%prompt%` + `%negative_prompt%` placeholder presence. |
| `/logs` | ✅ File picker (current + dated archives) + tail 200-5000 + 1s/2s/5s/Paused refresh + regex filter (case-insensitive) + auto-scroll + download. |

## Directory layout

```
platform/
├── app/                                # App Router
│   ├── layout.tsx                      # Sidebar + Header + Main + Toaster
│   ├── page.tsx                        # → redirects to /dashboard
│   ├── dashboard/                      # Bot status card + log tail + connections health card
│   ├── env/                            # /env editor — categories + secret masking + descriptions
│   ├── connections/                    # /connections — 4 endpoint Ping cards
│   ├── prompts/                        # /prompts — Monaco + diff modal
│   ├── characters/                     # /characters — CRUD + read-only schema viewer
│   │   ├── {page,characters-list,schema-viewer}.tsx
│   │   └── [charId]/{page,character-editor,persona-form,behaviors-form,images-form,bot-tokens-form,preview-panel,raw-tab,widgets}.tsx
│   ├── config/                         # /config — image config editor (3 tabs)
│   │   └── {page,config-page,master-detail,raw-json-pane,tab-header,use-config-file,sfw-scenes-tab,pose-motion-presets-tab,sfw-denylist-tab,profile-keys-tab}.tsx
│   ├── workflows/                      # /workflows — ComfyUI workflow management
│   │   └── {page,workflows-page,stage-assignments,workflow-tab,workflow-form,workflow-raw,workflow-replace,workflow-facts}.tsx
│   ├── logs/                           # /logs — full-page log viewer
│   │   └── {page,logs-page}.tsx
│   ├── lorebook/                       # /lorebook — per-character world knowledge editor
│   │   └── {page,lorebook-page,world-list,world-editor,entry-form,test-pane,mapping-card}.tsx
│   └── api/
│       ├── bot/                        # 5 routes: status / start / stop / restart / logs (logs accepts ?file= + ?listFiles=1)
│       ├── env/                        # GET / PUT
│       ├── connections/                # GET, [id] PUT, [id]/ping POST, ping-all POST
│       ├── prompts/{grok,system}/      # GET / PUT
│       ├── characters/                 # list / create + [charId] CRUD + [charId]/env (token+username) + [charId]/duplicate
│       ├── character-schema/           # GET-only read-only schema fetch
│       ├── config/[fileKey]/           # GET / PUT for sfw_scenes / pose_motion_presets / sfw_denylist / profile_keys
│       ├── workflows/                  # list / [name] (safe_fields | replace) / assignments (env-backed) / descriptions
│       ├── comfyui/                    # checkpoints proxy → ComfyUI /object_info/CheckpointLoaderSimple
│       └── lorebook/                   # worlds list/CRUD/duplicate + char→world mapping
├── components/
│   ├── ui/                             # shadcn primitives (Button, Card, Badge, Input, Label, Tabs, Sonner, Dialog, AlertDialog, Select, Textarea)
│   ├── sidebar.tsx                     # 9 nav items
│   ├── header.tsx
│   ├── monaco-client.tsx               # dynamic import Monaco (SSR off)
│   ├── bot-status-card.tsx             # 5s polling + Start/Stop/Restart + main-bot warning banner
│   ├── connections-health-card.tsx     # 30s polling, 4 dot summary
│   └── log-tail.tsx                    # logs/bot.log last 200 lines
├── lib/
│   ├── paths.ts                        # REPO_ROOT / RUN_DIR / LOGS_DIR / ENV_FILE / ENV_EXAMPLE_FILE / SQLITE_FILE
│   ├── bot-process.ts                  # spawn / kill / PID file. Pre-flight check refuses to start when MAIN_BOT_* missing.
│   ├── env-parser.ts                   # line-preserving .env parser + applyUpdates + parseExampleComments
│   ├── env-categories.ts               # 8 category mapping (LLM / Grok / ComfyUI / Video / Prompt Guard / Operations / Tokens / Platform)
│   ├── secrets.ts                      # *_API_KEY / *_BOT_TOKEN / CHAR_BOT_<id> patterns + maskValue
│   ├── backup.ts                       # KST-timestamped .env backup (unbounded rotation)
│   ├── db.ts                           # better-sqlite3 + connection_check table
│   ├── connections.ts                  # 4 endpoint definitions
│   ├── env-read.ts                     # .env value-read helper (used by status route + bot-process pre-flight)
│   ├── ping.ts                         # 4-endpoint ping (10s timeout, AbortController)
│   ├── prompts.ts                      # read/write/validate/lint config/grok_prompts.json + system_prompt.json
│   ├── characters.ts                   # 3-file bundle CRUD + soft-delete + nextFreeCharId
│   ├── char-schema.ts                  # PERSONA_FIELDS / IMAGES_FIELDS metadata + BLANK_* templates
│   ├── ajv.ts                          # Ajv2020 + validatePersona (draft-2020-12 schema)
│   ├── config-files.ts                 # server-side read/write/backup for the 4 config files
│   ├── config-files-meta.ts            # client-safe metadata (keys + display paths + tab titles)
│   ├── config-schemas.ts               # zod schemas for sfw_scenes / pose_motion_presets / sfw_denylist / profile_keys
│   ├── workflows.ts                    # read/write/backup for comfyui_workflow/*.json + auto facts + safe-fields + Replace validation + stage assignments (.env-backed) + descriptions
│   ├── workflows-meta.ts               # client-safe types
│   ├── log-files.ts                    # list bot.log + dated archives + path-traversal whitelist
│   ├── comfyui-client.ts               # fetchCheckpoints() proxy → ComfyUI /object_info/CheckpointLoaderSimple
│   ├── lorebook.ts                     # server-side read/write/backup + zod-validated CRUD for world_info/*.json + mapping
│   ├── lorebook-meta.ts                # client-safe types + previewMatches() (mirrors src/prompt.py _match_world_info)
│   └── utils.ts                        # cn() (shadcn util)
└── data/                               # gitignored — platform.sqlite + backups/.env.*.bak
```

## `lib/bot-process.ts` — bot lifecycle source of truth

| Export | Behavior |
|---|---|
| `getStatus()` | Returns `running` / `stopped` / `unknown`. PID file + `process.kill(pid, 0)` liveness check. Stale PIDs auto-cleaned. |
| `start()` | Pre-flight refuses to start when `MAIN_BOT_TOKEN` or `MAIN_BOT_USERNAME` is empty (throws `MAIN_BOT_NOT_CONFIGURED`). Otherwise `child_process.spawn(PYTHON_BIN, ['-m', 'src.bot'], { detached: true })` + `unref()` so the bot survives Next.js exits. 250ms post-spawn alive check (catches ImportError immediately). Throws `ALREADY_RUNNING` when a live PID is found. |
| `stop()` | `SIGTERM` → 100ms × 50 retries = 5s grace → `SIGKILL`. Removes the PID file. Throws `NOT_RUNNING` when nothing is running. |
| `restart()` | `stop()` (best-effort) + `start()`. |

**Concurrency**: every export is serialized through a module-level mutex
(Promise chain). Double-clicks don't race.

**PID tracking**: `run/bot.pid` (numeric PID) + `run/bot.meta.json`
(`{startedAt, command}`). The `run/` directory is auto-created and is in
the project-root `.gitignore`.

**Log pipe**: `logs/bot.log` is opened with `fs.openSync(..., 'a')` and
the child's stdout + stderr are redirected to that fd. The fd is
inherited by the child, so the child keeps appending after Next.js
exits.

## API routes

All Node runtime (`export const runtime = 'nodejs'`), `dynamic = 'force-dynamic'` (no caching).

| Route | Method | Response | Errors |
|---|---|---|---|
| `/api/bot/status` | GET | `{state, ..., main_bot: {token_set, username_set}}` | 500 STATUS_FAILED |
| `/api/bot/start` | POST | `{ pid }` | 422 MAIN_BOT_NOT_CONFIGURED / 409 ALREADY_RUNNING / 500 START_FAILED |
| `/api/bot/stop` | POST | `{ ok: true }` | 409 NOT_RUNNING / 500 STOP_FAILED |
| `/api/bot/restart` | POST | `{ pid }` | 500 RESTART_FAILED |
| `/api/bot/logs` | GET `?file=&tail=&listFiles=` | `{ lines, note? }` \| `{ files }` | 422 INVALID_FILE / 500 LOGS_FAILED |
| `/api/env` | GET | 8 categories + variables list | 500 ENV_READ_FAILED |
| `/api/env` | PUT `{updates}` | `{ok, restart_required, backup_path}` | 422 READ_ONLY_KEY / UNKNOWN_KEY / INVALID_VALUE |
| `/api/connections` | GET | 4 endpoints + last_ping | 500 |
| `/api/connections/[id]` | PUT `{url, token}` | `{ok, backup_path}` | 422 TOKEN_REQUIRED / TOKEN_NOT_SUPPORTED |
| `/api/connections/[id]/ping` | POST | `{ok, status_code, duration_ms, message}` | — (failures inline with `ok=false`) |
| `/api/connections/ping-all` | POST | `{results: {id: PingResult}}` | — |
| `/api/prompts/grok` | GET | `{file, keys: [{name, value, size}]}` | 500 PROMPT_READ_FAILED |
| `/api/prompts/grok` | PUT `{updates}` | `{ok, backup_path, warnings}` | 422 INVALID_PAYLOAD / MISSING_REQUIRED_KEY |
| `/api/prompts/system` | GET / PUT | (same as grok) | (same as grok) |
| `/api/characters` | GET | `{characters: [{charId, name, profile_summary_ko, mtime}]}` | 500 |
| `/api/characters` | POST `{from?}` | `{ok, charId}` | 409 NO_FREE_SLOT / 422 INVALID_CHAR_ID |
| `/api/characters/[charId]` | GET | `{charId, persona, behaviors, images}` | 404 UNKNOWN_CHARACTER |
| `/api/characters/[charId]` | PUT `{persona, behaviors, images}` | `{ok, backup_paths, warnings}` | 422 INVALID_CARD / INCOMPLETE_BUNDLE |
| `/api/characters/[charId]` | DELETE | `{ok, backup_dir}` (soft-delete) | 422 INVALID_CHAR_ID |
| `/api/characters/[charId]/env` | GET | `{fields: {token, username}, keys}` | 422 INVALID_CHAR_ID |
| `/api/characters/[charId]/env` | PUT `{token?, username?}` | `{ok, backup_path, updated_keys}` | 422 INVALID_VALUE |
| `/api/characters/[charId]/duplicate` | POST | `{ok, charId}` (next-free) | 404 UNKNOWN_CHARACTER |
| `/api/character-schema` | GET | `{file_path, content}` (read-only) | 500 SCHEMA_READ_FAILED |
| `/api/config/[fileKey]` | GET | `{key, content, mtime}` | 404 UNKNOWN_FILE_KEY / 500 |
| `/api/config/[fileKey]` | PUT `{content}` | `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / MISSING_GENERIC / 500 SAVE_FAILED |
| `/api/workflows` | GET | `{ workflows: [{name, mtime_ms, size_bytes, facts, description, stage_badges, assignable}] }` | 500 |
| `/api/workflows/[name]` | GET | `{ name, content, mtime_ms, size_bytes, facts, safe_fields }` | 404 UNKNOWN_WORKFLOW / 422 |
| `/api/workflows/[name]` | PUT `{kind: "safe_fields"\|"replace", ...}` | `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / NO_CHECKPOINT_LOADER / PLACEHOLDER_MISSING |
| `/api/workflows/assignments` | GET / PUT `{standard?, hq?}` | `{standard, hq, options}` / `{ok, backup_path}` | 422 UNKNOWN_FILE |
| `/api/workflows/descriptions` | GET / PUT `{filename, description}` | `{content}` / `{ok, backup_path}` | 422 UNKNOWN_FILE |
| `/api/comfyui/checkpoints` | GET | `{ok, comfyui_url, checkpoints}` \| `{ok: false, reason, message, checkpoints: []}` | 200 always (failures inline) |
| `/api/lorebook/worlds` | GET / POST `{name}` | `{worlds: [...]}` / `{ok, name}` | 422 INVALID_NAME / 409 ALREADY_EXISTS |
| `/api/lorebook/worlds/[name]` | GET / PUT `{content}` / DELETE | `{name, content, mtime_ms, size_bytes, mapped_chars}` / `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / WORLD_IN_USE / 404 UNKNOWN_WORLD |
| `/api/lorebook/worlds/[name]/duplicate` | POST | `{ok, name}` | 404 UNKNOWN_WORLD |
| `/api/lorebook/mapping` | GET / PUT `{mapping}` | `{mapping, characters, worlds}` / `{ok, restart_required, backup_path}` | 422 UNKNOWN_WORLD / UNKNOWN_CHARACTER |

The logs route uses a 1MB read window and clamps the tail to 1 ≤ N ≤ 5000 (default 200).

## SQLite

`platform/data/platform.sqlite` (gitignored). WAL mode. `lib/db.ts`
lazy-initializes + runs idempotent migrations.

Tables:

- `connection_check` — `(id, endpoint_id, ts, ok, status_code, duration_ms, message)` + index `(endpoint_id, ts DESC)`. `recordPing` / `getLastPing` / `getLastPingsAll` helpers.

## Dependencies

- **next 14.2.35** (Tailwind 3.4 + App Router). Pinned to a security-patched 14.2.x.
- **shadcn/ui** primitives — written by hand (no `shadcn` CLI). Only `components.json` + the components actually used.
- **lucide-react** — icons.
- **class-variance-authority + tailwind-merge + clsx** — shadcn standard utility deps.
- **better-sqlite3** — single-file SQLite. Native binding, prebuilt arm64 downloads cleanly.
- **@radix-ui/react-tabs / react-label** — env tabs / form labels.
- **sonner** — toast UI.
- **@monaco-editor/react** — VS Code-equivalent editor (dynamic import, SSR off).
- **@radix-ui/react-dialog** — shadcn Dialog primitive (diff modal + view-schema modal).
- **react-diff-viewer-continued** — split-view diff (active React 18 fork).
- **ajv** + **ajv/dist/2020** — JSON Schema validator (draft-2020-12) for character cards.
- **@radix-ui/react-alert-dialog** — destructive-action confirmations.
- **react-markdown** + **remark-gfm** — first_mes preview rendering.
- **zod** — shape validation for the 4 image-config files + lorebook entries.
- **@radix-ui/react-select** — `anchor_risk` (pose presets), `position` (lorebook entries), workflow stage assignments.

## Editing guidelines

1. **Type-check**: `npx tsc --noEmit`. Run before every commit.
2. **Server vs client**: API routes use Node runtime; UI components must declare `"use client"`. Server-only modules (`node:fs` / `node:path`) must NOT be imported from client components — keep client-safe types in a `*-meta.ts` companion (the M4 + M6 pattern).
3. **`@/*` import alias** — defined in `tsconfig.json`. Always absolute (`@/lib/...`, `@/components/...`).
4. **Bot-process changes**: when touching `lib/bot-process.ts`, manual-test start / stop / restart / stale-PID scenarios. `npm run build` does not exercise the race paths.
5. **New milestones**: open a feature branch + write `docs/features/M<N>_<name>.md` with PM decisions + sign-off → implement. On merge, refresh the "Pages" table above.

## Adding a new page

1. Add an item to the sidebar (`components/sidebar.tsx`'s `items` array).
2. Follow the existing folder pattern: `app/<page>/page.tsx` (server entry) + `<page>-page.tsx` (client) + helper components.
3. Split server lib from client lib (`lib/<x>.ts` + `lib/<x>-meta.ts`) — importing `node:fs` / `node:path` from a client component breaks the webpack build (we hit this in M4 and M6).
4. API routes: `runtime = 'nodejs'` + `dynamic = 'force-dynamic'`.
5. Reuse the KST-timestamp backup pattern in `lib/backup.ts` for any save path.

`character_card_schema.json` is exposed only as a read-only viewer
(M4) — direct edits bypass the platform UI. After hand-editing, run a
round-trip ajv validation against the live persona files (e.g. via the
schema viewer's API) before restarting the bot.
