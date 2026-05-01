# Telegram Chatbot Manager

A self-hosted admin platform for running Telegram character chatbots.

## What this project is

This repository pairs:

- **A Telegram bot runtime** (`src/`) that can host one **main bot** (onboarding,
  profile, admin commands) plus an arbitrary number of **character bots** —
  each character is its own Telegram bot with its own token, persona,
  behaviors, lorebook, and image-generation pipeline.
- **A Next.js admin web app** (`platform/`) that runs on `127.0.0.1` and lets
  you manage the entire setup from a browser without editing JSON / Python by
  hand. Add a character, edit its prompts, swap a ComfyUI workflow, watch the
  bot logs — all through the UI.

The bot is opinionated: the chat layer is built around **stateful character
state** (per-user "fixation" + mood + location), **conditional lorebook
injection** (SillyTavern-style entries that fire on keyword match), **image
generation through ComfyUI**, and **video generation through Atlas Cloud**.
Image- and video-generation are optional — characters can run as
text-only bots.

## Architecture at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│  Operator's browser ──HTTP──▶ Next.js admin (platform/)         │
│                                  │                              │
│                                  │  spawn / kill                │
│                                  ▼                              │
│  Telegram users ──Telegram API──▶ Python bot (src/bot.py)       │
│                                  │                              │
│                       ┌──────────┼─────────────┐                │
│                       ▼          ▼             ▼                │
│                    ComfyUI    Atlas Cloud   LLM API             │
│                  (image gen) (video gen)  (Grok / OpenAI-       │
│                                            compatible)          │
└─────────────────────────────────────────────────────────────────┘
```

| Component | Path | Role |
|---|---|---|
| Bot runtime | `src/` | Python 3, `python-telegram-bot`. Hosts main + character + image-gen bots. |
| Admin webapp | `platform/` | Next.js 14 (App Router), runs on 127.0.0.1:9000. |
| Character cards | `persona/` `behaviors/` `images/` | Per-character JSON bundles (one file per kind). |
| Lorebook | `world_info/` | Per-character world-knowledge entries with `mapping.json`. |
| Image workflows | `comfyui_workflow/` | ComfyUI workflow JSON used for image rendering. |
| Static config | `config/` | Externalized prompts, scene catalog, denylist, profile keys. |
| Deploy helpers | `deploy/` | `prompt-guard/` server + `runpod/` serverless image-gen. |
| Persistent data | `data/` (gitignored) | `chat.db` SQLite — created automatically on first bot start. |

## Tech stack

- **Python 3.10+** — `python-telegram-bot`, `httpx`, `boto3`, SQLite (stdlib)
- **Next.js 14.2** (App Router) + **Tailwind 3.4** + **shadcn/ui** primitives
- **TypeScript 5** with strict checks
- **Monaco editor** for JSON / prompt editing in the admin
- **better-sqlite3** for the platform's own audit log
- **ajv** + **zod** for schema validation
- **ComfyUI** (self-hosted or RunPod serverless) for image generation
- **Atlas Cloud `wan-2.6/image-to-video-flash`** for video generation
- **Grok / X.AI API** (or any OpenAI-compatible endpoint) for the language model

## Quick start

```bash
# 1. Bot
git clone <your-fork> && cd telegram-chatbot-manager
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill MAIN_BOT_TOKEN + MAIN_BOT_USERNAME at minimum

# 2. Admin webapp
cd platform
npm install
npm run dev                # opens http://127.0.0.1:9000
```

The admin is the recommended entry point — it can start / stop the bot
process, edit `.env`, manage character cards, edit prompts, etc. without
shell access.

Minimum env vars to send the first message:

| Variable | Required | Notes |
|---|---|---|
| `MAIN_BOT_TOKEN` | ✅ | From `@BotFather`. Bot refuses to start without this + `MAIN_BOT_USERNAME`. |
| `MAIN_BOT_USERNAME` | ✅ | Username (no `@`) of the main bot. |
| `GROK_API_KEY` | ✅ | Or another OpenAI-compatible LLM key with `GROK_BASE_URL` overridden. |
| `OPENWEBUI_URL` | ✅ | Local LLM endpoint for chat completions (e.g. `llama.cpp`'s OpenAI-compat server). |
| `COMFYUI_URL` | ⚪ | Required only if you enable image generation. |
| `ATLASCLOUD_API_KEY` | ⚪ | Required only if you enable video generation. |
| `CHAR_BOT_<id>` + `CHAR_USERNAME_<id>` | ⚪ | One pair per character bot you want to run. |

`.env.example` documents every variable.

## Repository layout

```
.
├── src/                      # Python bot runtime
├── platform/                 # Next.js admin webapp
├── persona/                  # Character persona JSONs (one per character)
├── behaviors/                # Per-character behavior tables
├── images/                   # Per-character image-prompt config
├── world_info/               # Per-character lorebooks + mapping.json
├── comfyui_workflow/         # ComfyUI workflow JSON files
├── config/                   # Static config (externalized prompts, scene catalog, ...)
├── deploy/                   # prompt-guard/ + runpod/ deployment helpers
├── docs/                     # Operator guides + per-milestone feature plans
├── tools/                    # Misc operational scripts (ad-hoc)
├── scripts/                  # Migration / maintenance scripts
├── jobs/                     # Per-job background knowledge (currently empty)
├── .env.example              # Documented env-var template
├── CLAUDE.md                 # This file
├── README.md                 # GitHub-front-page summary
└── STATUS.md                 # Active milestone tracker
```

Each subdirectory has its own `CLAUDE.md` with that folder's specifics.

## Implementation status (milestones)

| Milestone | Commit | Highlights |
|---|---|---|
| M0 — Admin skeleton | `7804ea1` | Next.js scaffold, sidebar, bot lifecycle (`bot-process.ts`), 5 API routes, Dashboard. |
| M1 — Env + Connections | `09334db` | `/env` editor (8 categories, secret masking, auto-backup), `/connections` (4 endpoints with ping + audit log). Codebase i18n to English. |
| M1 polish | `b1fa27f` | `GROK_PROMPTING_*` env namespace, secret-mask UI fix, `.env.example` defaults. |
| M2 — Prompt editor | `4823d44` | `/prompts` page: Monaco + diff modal + per-key save + `${var}` placeholder lint. |
| M3 — Character CRUD | `6fb059a` | `/characters` list + form + Raw JSON editor + draft auto-save + soft-delete + per-character bot tokens. |
| M4 — Image config | `4621d27` | `/config` (3 tabs: SFW scenes / pose-motion presets / outfit denylist) + `/prompts` profile-keys tab + `/characters` schema viewer. |
| M5 — Workflows + Logs | `b36338b` | `/workflows` (stage assignments, auto-facts, Form/Raw/Replace) + `/logs` (file picker, regex filter, polling). Strict main-bot. UX polish (Chatbot Manager rename, Select transparency fix, log dedup). |
| Post-M5 cleanup | `d1be949` + `aea64a4` | Security (private IP scrubbed, `GROK_BASE_URL` consolidation), deploy folder cleanup, bot UX strip (no TOS / privacy / consent), workflow cleanup (NSFW node strip + checkpoint dropdown auto-populate). |
| M6 — Lorebook | `f49f2fb` | `/lorebook` page + `world_info/mapping.json` (char → world). Sample `world_info/char05.json`. Test-pane mirrors `_match_world_info()`. |

The full per-milestone plan documents live under
[`docs/features/`](docs/features/). The per-folder `CLAUDE.md` files
describe the *current* code, not the history — read the matching one
before editing.

## Development workflow

### Branch strategy

```
main         ◄─ Stable. Always working. All CLAUDE.md files current.
  └ develop  ◄─ Integration branch. Feature branches merge here.
      └ feat/feature_<name>   ◄─ Single feature / milestone.
```

### Per-feature procedure

1. Branch off `develop`: `git checkout -b feat/feature_<name>`.
2. Write a plan MD in `docs/features/M<N>_<name>.md` (PM sign-off before
   implementation — see existing examples).
3. Implement following the plan. Commit incrementally.
4. Smoke test (`npm run build` clean + manual UI test).
5. Merge to `develop` with `--no-ff`. Include a docs-update commit on the
   feature branch:
   - Root `CLAUDE.md` (Implementation Status row)
   - `STATUS.md` (current state)
   - Each touched folder's `CLAUDE.md`
6. Promote `develop` → `main` when a milestone bundle is stable.

### Doc invariants

The per-folder `CLAUDE.md` files describe the **current code**, not history.
When you change behavior in a folder, update its `CLAUDE.md` in the same
commit (or in the docs-update commit on the feature branch). Historical
context belongs in `docs/features/M*.md`.

## Conventions

- Python: type hints where they help, no `from __future__ import annotations`,
  fail-fast on missing required config (no silent fallbacks for things like
  Grok prompts).
- TypeScript: strict mode, `import type` for type-only imports, server-only
  modules use `node:fs` / `node:path` and must NOT be imported from client
  components — keep client-safe types in a `*-meta.ts` companion.
- API routes: `runtime = 'nodejs'` + `dynamic = 'force-dynamic'`. 422 for
  validation errors, 404 for missing entities, 409 for conflicts, 500 for
  unexpected failures.
- File writes: atomic (write to `.partial`, rename) + automatic `.bak`
  copy in `platform/data/backups/` on every save.
- Logging: Python's `TimedRotatingFileHandler` writes `logs/bot.log`. The
  admin's bot lifecycle redirects child stdout / stderr to the same file.
  Do NOT add a Python `StreamHandler` — it would duplicate every record.

## License

This project ships without an explicit license at the moment. Until a
LICENSE file is added, treat all rights as reserved by the original
author.
