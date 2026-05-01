# Telegram Chatbot Manager

A self-hosted admin platform for running Telegram character chatbots.

Pair a Python bot runtime with a Next.js admin web app: spin up multiple
character bots, tune their personas / prompts / lorebooks from a browser,
and let each character render images via ComfyUI and short clips via
Atlas Cloud — all without editing JSON or Python by hand once it's set up.

```
┌──────────────────────────────────────────────────────────┐
│  Operator's browser ──▶  /platform (Next.js admin)       │
│                              │                           │
│                              │ spawn / kill              │
│                              ▼                           │
│  Telegram users   ──▶  /src/bot.py (Python runtime)      │
│                              │                           │
│                    ┌─────────┼─────────────┐             │
│                    ▼         ▼             ▼             │
│                 ComfyUI   Atlas Cloud   Grok / OpenAI    │
└──────────────────────────────────────────────────────────┘
```

## Highlights

- **Multi-bot host.** One main bot for onboarding + N character bots,
  each with its own Telegram token, persona, behaviors, lorebook, and
  optional image-gen pipeline.
- **Browser admin.** 9 pages (`Dashboard / Connections / Env / Prompts /
  Characters / Lorebook / Image Config / Workflows / Logs`) with editor,
  validation, auto-backup, and a live log viewer.
- **Stateful character chat.** Per-user "fixation" + mood + location
  carried in SQLite; lorebook entries fire on keyword match and are
  spliced into the prompt at the right place.
- **Schema-validated everything.** ajv (character cards, draft-2020-12)
  + zod (image config, lorebook). All saves are atomic and produce a
  `.bak` next to the live file.
- **Self-hosted by design.** Bot runs on your box; admin binds to
  `127.0.0.1`; image-gen can be local ComfyUI or remote (RunPod
  serverless).

## Quick start

```bash
# 1. Bot
git clone <your-fork> && cd telegram-chatbot-manager
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill MAIN_BOT_TOKEN + MAIN_BOT_USERNAME

# 2. Admin webapp
cd platform
npm install
npm run dev                # opens http://127.0.0.1:9000
```

From the admin you can `Start` the bot, edit `.env`, manage character
cards, edit prompts, etc. without touching the shell again.

Minimum env vars to send the first message:

| Variable | Required | Notes |
|---|---|---|
| `MAIN_BOT_TOKEN` | ✅ | From `@BotFather`. Bot refuses to start without `MAIN_BOT_TOKEN` + `MAIN_BOT_USERNAME`. |
| `MAIN_BOT_USERNAME` | ✅ | Bot username (no `@`). |
| `GROK_API_KEY` | ✅ | Or any OpenAI-compatible key with `GROK_BASE_URL` overridden. |
| `OPENWEBUI_URL` | ✅ | Local LLM endpoint for chat completions (e.g. llama.cpp's OpenAI-compat server). |
| `COMFYUI_URL` | ⚪ | Required only for image generation. |
| `ATLASCLOUD_API_KEY` | ⚪ | Required only for video generation. |
| `CHAR_BOT_<id>` + `CHAR_USERNAME_<id>` | ⚪ | One pair per character bot. |

`.env.example` documents every variable. The admin's `/env` page is the
recommended editor — it categorizes the keys, masks secrets, validates
required fields, and writes an automatic `.bak` on every save.

## Stack

- Python 3.10+ · `python-telegram-bot` · SQLite (stdlib) · `httpx`
- Next.js 14.2 (App Router) · Tailwind 3.4 · shadcn/ui
- TypeScript 5 (strict) · Monaco editor · ajv (draft-2020-12) · zod
- ComfyUI (self-hosted or RunPod serverless) for image generation
- Atlas Cloud `wan-2.6/image-to-video-flash` for video
- Grok / X.AI API (or any OpenAI-compatible endpoint) for the LLM

## Repository layout

```
src/                   Python bot runtime
platform/              Next.js admin webapp
persona/               Character persona JSONs
behaviors/             Per-character behavior tables
images/                Per-character image-prompt config
world_info/            Per-character lorebooks + mapping.json
comfyui_workflow/      ComfyUI workflow JSONs
config/                Externalized prompts + scene catalog + denylist + profile keys
deploy/                prompt-guard/ + runpod/ deployment helpers
docs/                  Operator guides + per-milestone feature plans
.env.example           Documented env-var template
CLAUDE.md              Project overview for contributors / AI assistants
STATUS.md              Active milestone tracker
```

Each subdirectory has its own `CLAUDE.md` describing what's inside.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — full project overview, architecture, and
  development workflow.
- [`STATUS.md`](STATUS.md) — current milestone state.
- [`docs/character_card_instruction.md`](docs/character_card_instruction.md)
  — how to write a character card (persona / behaviors / images).
- [`docs/features/`](docs/features/) — historical per-milestone feature
  plans (M0 – M6).
- [`deploy/prompt-guard/README.md`](deploy/prompt-guard/README.md) —
  optional prompt-injection-detection sidecar (FastAPI + ProtectAI deberta).

## License

This project ships without an explicit license at the moment. Until a
`LICENSE` file is added, treat all rights as reserved by the original
author.
