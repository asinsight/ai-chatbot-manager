# STATUS

> Live milestone tracker. Update on every meaningful step.
> Architecture / conventions live in [CLAUDE.md](CLAUDE.md).

**Last updated**: 2026-05-01 (M6 merged into develop)

---

## Current state

- **Branch**: `develop`
- **Next**: candidate follow-up PRs (see "Backlog" below)
- **Blocker**: none

---

## Completed milestones (newest first)

| Date | Milestone | Branch | Merge commit | Highlights |
|---|---|---|---|---|
| 2026-05-01 | M6 — Lorebook editor + char→world mapping | `feat/feature_M6_lorebook` | `f49f2fb` | `world_info/char05.json` (sample lorebook, 6 entries) + `world_info/mapping.json` (`char_id → world_id`). `src/prompt.py` consults the mapping first and falls back to the legacy `<char_id>.json` convention. New `/lorebook` page: Mapping card (per-char dropdown + "(legacy fallback)" option) + World list (Add / Duplicate / Delete with `WORLD_IN_USE` pre-warning) + World editor (Test pane that mirrors `_match_world_info()` + entry CRUD: chips / textarea / position select). 4 new API routes + `lib/lorebook.ts` (zod) + `lib/lorebook-meta.ts` (client-safe). Zero new dependencies. |
| 2026-04-30 | Post-M5 cleanup — security + deploy + onboarding strip + workflows polish | `feat/feature_M5_polish_cleanup` + `feat/feature_M5_polish_workflow_cleanup` | `d1be949` + `aea64a4` | Security: stripped 192.168.86.250 private IP fallback; routed 3 hard-coded `https://api.x.ai/v1` callsites through `GROK_BASE_URL`; collapsed 5 `grok.py` callsites into a single module-level constant. Deploy: removed all systemd `.service` files + `install.sh` + `backup_db.sh` (this isn't a managed service); translated all Korean comments / log messages to English; added self-contained `deploy/prompt-guard/` (FastAPI server + README). Bot UX: removed TOS / privacy / consent dialog from `/start`, removed `/privacy` command, renamed welcome header to "Telegram Chatbot Manager", removed `fixation > 50` gate so the 📷 Capture button shows on every reply. Workflows: stripped 4 NSFW nodes from `main_character_build_highqual.json`; bundled workflows now ship with `PLACEHOLDER_CHECKPOINT.safetensors`; `/workflows` Form replaces the checkpoint text input with a Select auto-populated from ComfyUI's `/object_info`. |
| 2026-04-30 | M5 — Workflows + Logs + strict main bot + UX polish | `feat/feature_M5_workflows_logs` | `b36338b` | `/workflows`: Stage assignments (Standard / HQ dropdown ↔ `COMFYUI_WORKFLOW{,_HQ}` env), per-workflow auto-facts (node count / Σ KSampler steps / refiner+detailer detection / size) + admin description (`config/workflow_descriptions.json`), Form / Raw JSON / Replace 3 inner tabs. Replace enforces `%prompt%` + `%negative_prompt%` placeholder validation. `/logs`: file picker (current + dated archives) + tail 200-5000 + 1s/2s/5s/Paused refresh + regex filter + auto-scroll + download (`/api/bot/logs` extended with `?file=` + `?listFiles=1`). Strict main bot: `bot.py` raises `SystemExit` if `MAIN_BOT_TOKEN` / `MAIN_BOT_USERNAME` is empty; platform `start()` does the same pre-flight check (422 `MAIN_BOT_NOT_CONFIGURED`); dashboard shows an amber warning banner + Start button disabled; `/env` marks the keys as required and blocks Save until they're filled. UX: sidebar / browser title renamed to "Chatbot Manager"; shadcn Select transparency fix (`--popover` CSS var added); `bot.log` line-duplication fix (Python `StreamHandler` removed). Zero new dependencies. |
| 2026-04-30 | M4 — Image config editor + Character schema viewer | `feat/feature_M4_image_config` | `4621d27` | `/config` 3 tabs (`sfw_scenes` / `pose_motion_presets` / `sfw_denylist`) — master-detail + chips form + Raw JSON fallback + zod validation + auto-backup + restart-required toast. `profile_keys` moved to `/prompts` as a 3rd outer tab (it controls LLM canonicalization, not image config). `character_card_schema` moved to `/characters` as a read-only "View schema" Dialog (editing it through the UI was a foot-gun) + descriptions translated to English. Bonus: fixed 4 pre-existing `react/no-unescaped-entities` lint errors that were blocking `npm run build` on develop. Added `zod` + `@radix-ui/react-select`. |
| 2026-04-30 | M3 — Character CRUD + single bot-token namespace | `feat/feature_M3_character_crud` | `6fb059a` | `/characters` list (Edit / Duplicate / Delete with AlertDialog) + `/characters/[charId]` editor (Form mode: Persona / Behaviors / Images / Bot tokens 4 tabs; Raw JSON mode: 3 Monaco editors). 22 persona fields are schema-driven (chips / kv / trigger-list / stat-limits widgets) + behaviors as a 4-tier fixation table + nested images object. `first_mes` markdown preview with `{{user}}` / `{{char}}` macro substitution. Soft-delete + draft auto-save + ajv validation + empty-required rejection. Dropped the `TEST_` / `PROD_` env namespace split — single namespace is enough for an open-source single-deployment build. `/env` Bot tokens tab groups Native (`MAIN_BOT_*`, `CHAR_BOT_imagegen`) vs Character (read-only with redirect link). The bot only lists a character on the main bot's menu when both `CHAR_BOT_<id>` AND `CHAR_USERNAME_<id>` are set. |
| 2026-04-29 | M2 — Prompt editor | `feat/feature_M2_prompt_editor` | `4823d44` | `/prompts` page: outer tabs (Grok prompting / System prompt) × inner tabs (5+3 keys), Monaco 65vh editor, react-diff-viewer modal, `${var}` placeholder lint (warn-not-block), per-key save with auto-backup, inline metadata (title / summary / used-by) per key. |
| 2026-04-28 | M1 polish | `feat/feature_M1_polish` | `b1fa27f` | Renamed Grok env vars to `GROK_PROMPTING_*`, exposed `VIDEO_COMPOSER_MODEL`, fixed `/env` UI secret-mask display, added default-value placeholders in `.env.example`, corrected the OpenWebUI label (Gemma → llama-cpp-python). |
| 2026-04-28 | M1 — Env + Connections + i18n + sample character | `feat/feature_M1_env_connections` | `09334db` | `/env` (8 categories + secret masking + auto-backup + restart-required toast) + `/connections` (4 endpoint cards with Ping + SQLite audit log + Dashboard health card). Added `GROK_BASE_URL` env var as a prerequisite. Codebase i18n: every code / config / character file translated to English (markdown excluded). Trimmed sample characters down to one (`char05` — Jiwon Han). |
| 2026-04-27 | M0 — Admin skeleton | `feat/feature_M0_admin_skeleton` | `7804ea1` | Next.js 14 scaffold + sidebar + `bot-process.ts` (spawn / kill / PID file / log redirect) + 5 API routes (status / start / stop / restart / logs) + Dashboard UI. 9 manual smoke-test scenarios passed. |

---

## Backlog (candidate follow-up PRs)

- `config/video_models.json` catalog + dropdown in `/env` for `VIDEO_MODEL`
- Prompt Guard authentication (when the server adds an auth layer)
- SSE-based live log streaming on `/logs` (currently 1s polling)
- Workflow versioning page (browse the `.bak` snapshots in `platform/data/backups/`)
- Title-based prompt injection in `src/comfyui.py` — find Positive / Negative
  `CLIPTextEncode` nodes by `_meta.title` and assign directly, dropping the
  `%prompt%` / `%negative_prompt%` placeholder convention. Risk: changes
  render semantics, do as its own PR.
- License file (`MIT` or similar) once the maintainer picks one.

---

## Per-folder `CLAUDE.md` status

Updated whenever a feature touches a folder. All files describe the
current code, not history (history goes in `docs/features/M*.md`).

| Folder | `CLAUDE.md` |
|---|---|
| (root) | ✅ |
| `src/` | ✅ |
| `platform/` | ✅ |
| `config/` | ✅ |
| `deploy/` | ✅ |
| `comfyui_workflow/` | ✅ |
| `behaviors/` | ✅ |
| `persona/` | ✅ |
| `images/` | ✅ |
| `world_info/` | ✅ |
| `docs/` | ✅ |
| `scripts/` | ✅ |
| `tools/` | ✅ |
| `jobs/` | — (folder is empty in this distribution) |

---

## Update conventions

- Update this file on every meaningful step (feature merge, blocker, decision).
- Move "in progress" → "completed" with the merge commit hash.
- Drop "decision pending" entries as soon as they are resolved.
- Always include the absolute date on the top line.
- A feature merge to `develop` ships a docs-update commit on the same branch.
- A `develop` → `main` promotion ships every `CLAUDE.md` updated for the
  changes in the bundle (see workflow rules in [CLAUDE.md](CLAUDE.md)).
