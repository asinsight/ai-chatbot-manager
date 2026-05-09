# AI Chat Manager

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

## Features

### Telegram-side, end-user features

**Character chat**
- Multi-character menu surfaced from the main bot (`/start` lists every
  registered character; tapping one deep-links to that character's
  dedicated bot).
- Per-user, per-character state in SQLite — `fixation` (0–100,
  attachment / interest), `mood` (per-character vocabulary), and
  `location` (snake_case key the LLM keeps in sync). The bot tags every
  reply with a hidden `[STAT: fixation+N, mood:VALUE, location:PLACE]`
  signal which is parsed and persisted, then influences the next turn's
  prompt.
- 4-tier fixation behavior table (`behaviors/charNN.json`) controls how
  proactive / personal the character is at each tier.
- Per-mood behavior guidelines (`mood_behaviors`) and free-text
  triggers (`mood_triggers`) that flip the mood when the user says
  certain things.

**Lorebook (world knowledge)**
- SillyTavern-style keyword-triggered context injection from
  `world_info/<world_id>.json` files. Multiple characters can share one
  world (`world_info/mapping.json`).
- `position: "background"` entries land near the top of the prompt as
  stable backdrop facts; `position: "active"` entries land near the
  user message and bias the immediate response (LLMs over-weight the
  prompt tail).

**Image generation**
- Character-driven autonomy: when the LLM appends a hidden
  `[SEND_IMAGE: short scene description]` signal, the bot generates
  and sends a photo in-character. A `📷 Capture` button is also shown
  on every reply so the user can request a snapshot of the current
  scene on demand.
- `/random` command on the image-gen bot for a SFW scene roll from
  `config/sfw_scenes.json`.
- `/hq on|off` toggle per user — switches between the Standard and HQ
  ComfyUI workflows (see `/workflows` admin page).
- Outfit changes propagate via a hidden `[OUTFIT: tag1, tag2, ...]`
  signal the LLM emits when the character actually changes clothes —
  the bot persists the new outfit and renders subsequent images with it.

**Video generation**
- Image-to-video clips via Atlas Cloud `wan-2.6/image-to-video-flash`.
  Triggered from the inline keyboard the bot shows under generated
  images.
- Pose-motion presets (`config/pose_motion_presets.json`) drive the
  motion prompt sent to the i2v composer; can be overridden per user
  request.

**User profile + memory**
- Free-form profile keys (canonical → aliases) defined in
  `config/profile_keys.json`. The bot extracts user information from
  conversation (name, age, hobby, family, …) and persists it in SQLite,
  then injects it into future prompts.
- `/profile` command — view / set the profile manually.
- `/deletedata` command — wipes all of that user's history + profile.
- Long-running summaries: chat history is compacted into a per-session
  summary that's spliced back into the system prompt to keep the
  context window bounded.

**Web search**
- Grok-backed web search for live information (when the LLM emits a
  `[SEARCH: query]` signal). Results are summarized in 2–3 sentences
  and woven into the response naturally.

**Safety net**
- Regex input filter in `src/input_filter.py` (Korean + English
  patterns) blocks underage / unsafe content before it reaches the
  LLM.
- Optional Prompt Guard sidecar (FastAPI + ProtectAI deberta) for
  prompt-injection detection. See [`deploy/prompt-guard/README.md`](deploy/prompt-guard/README.md).
- SFW outfit denylist (`config/sfw_denylist.json`) silently strips
  banned tokens from any `[OUTFIT: ...]` signal.

### Admin-side features (`/platform`)

- `/dashboard` — bot lifecycle (Start / Stop / Restart), live log tail,
  connection health summary.
- `/connections` — Ping the 4 external endpoints (ComfyUI / OpenWebUI
  / Grok / Prompt Guard); audit log persisted to SQLite.
- `/env` — full `.env` editor with secret masking, per-key validation,
  auto-backup, restart-required toast.
- `/prompts` — Monaco editor for `config/grok_prompts.json` +
  `config/system_prompt.json` + the profile-key alias map. Diff modal
  + per-key save + `${var}` placeholder lint.
- `/characters` — schema-driven character card editor (Form mode for
  22 fields with widget dispatch; Raw JSON mode with 3 Monaco
  editors). Draft auto-save, soft-delete, per-character bot tokens,
  ajv validation.
- `/lorebook` — per-world editor + character→world mapping. Built-in
  Test pane lets you paste a user message and preview which entries
  would fire.
- `/config` — image config editor: SFW scenes / pose-motion presets /
  outfit denylist (all zod-validated).
- `/workflows` — ComfyUI workflow management. Stage assignments
  (Standard / HQ ↔ env), per-file auto-facts (node count / Σ sampler
  steps / refiner detection), Form / Raw JSON / Replace tabs. Replace
  enforces the `%prompt%` + `%negative_prompt%` placeholder
  convention.
- `/logs` — full-page log viewer with file picker (current +
  daily-rotated archives), tail size selector, refresh interval (1s /
  2s / 5s / paused), regex filter, download.

## How image generation works (Danbooru pipeline)

The bot does not render with raw natural-language prompts — every
character image flows through a deterministic Danbooru-tag pipeline
that guarantees outfit / appearance / safety consistency.

### 1. Trigger

Either:
- The LLM emits a hidden `[SEND_IMAGE: short scene description]` token
  at the end of its reply (autonomous), or
- The user taps the `📷 Capture` button on a character's reply
  (manual — the recent chat history is the scene description).

### 2. Scene seed (`config/sfw_scenes.json`)

`src/trait_pools.py:roll_sfw_scene()` picks one entry from the scene
catalog. Each entry pre-defines:

- `pose_pool` — pose tag candidates
- `camera_pool` — camera-angle candidates (`from_front`,
  `over_the_shoulder`, …)
- `location_pool` — location candidates
- `activity_tags` — comma-separated environment / prop tags
- `expression_hint` — emotional baseline

Pre-seeding the scene this way prevents Grok from biasing pose /
camera selection toward whatever the most recent dialogue would
suggest. The `[SEND_IMAGE]` description is added on top of the seed,
not in place of it.

### 3. Compose Danbooru tags via Grok (`config/grok_prompts.json`)

`src/grok.py:generate_image_prompt()` calls the LLM with the `system`
prompt (a strict SFW Danbooru-tag generator). Inputs:

- The scene seed from step 2.
- The character's persona — `image_prompt_prefix` (always-applied
  appearance tags, e.g. `"1girl, brown_hair, brown_eyes, 1boy, ..."`),
  `image_negative_prefix`, current mood, current location.
- The character's body / clothing config (`images/charNN.json`):
  `appearance_tags`, `clothing` / `alt_outfit` / `underwear`,
  `body_shape` (size / build / curve / accent / ass), `breast` (size /
  feature).
- The current outfit state from `[OUTFIT: ...]` history (overrides
  default `clothing` if the character has changed).
- Any user-side overrides parsed from the request (`/random` argument,
  `/edit` partial edits, etc.).

The Grok system prompt enforces a SFW ruleset (clothing always full
and intact, mandatory negative block, `BLOCKED` response when minor
implied) and outputs a comma-separated Danbooru-tag string.

### 4. Outfit-state denylist (`config/sfw_denylist.json`)

If the LLM has just emitted an `[OUTFIT: ...]` change in the same turn,
its tokens are intersected with the denylist (`outfit_state_keywords`)
before persisting. Banned tokens (e.g. `nude`, `topless`,
`underwear_only`, …) are silently dropped — the persisted outfit
always represents a fully-clothed state.

### 5. Embedding prefixes (`src/comfyui.py`)

Every render is wrapped with safety embeddings:

```
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazynsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"
```

`lazynsfw` actively suppresses NSFW visual elements; `lazypos` is a
quality embedding; `lazyneg` and `lazyhand` cover general
quality-and-anatomy issues. These prefixes are concatenated **outside**
the Grok-generated tags so they're invariant per render.

The final positive prompt is:

```
embedding:illustrious/lazypos, <model_pos_prefix>, <character image_prompt_prefix>, <Grok-composed scene tags>
```

### 6. ComfyUI workflow injection

The selected workflow JSON is loaded from `comfyui_workflow/` —
**Standard** (`COMFYUI_WORKFLOW`) by default, **HQ**
(`COMFYUI_WORKFLOW_HQ`) when the user has toggled `/hq on`. The two
workflows correspond to different rendering paths (the HQ workflow
ships with a face/eye/hand/foot Detailer chain on top of the base
KSampler).

`src/comfyui.py:inject_prompts()` performs an in-place string
replacement of two placeholder tokens in the workflow JSON:

- `%prompt%` — replaced with the assembled positive prompt.
- `%negative_prompt%` — replaced with the assembled negative prompt.

These placeholders live in the Positive / Negative `CLIPTextEncode`
nodes (titles `"Positive"` / `"Negative"`). The `/workflows` admin's
Replace tab refuses any pasted workflow that's missing the
placeholders (422 `PLACEHOLDER_MISSING`) — without them, the runtime
substitution silently no-ops and every render uses whatever literal
prompt was in the file.

### 7. Render + send

The patched workflow is POSTed to ComfyUI's `/prompt` endpoint, the
bot polls `/history/<prompt_id>` for completion (up to 360s), the
output PNG is fetched from `/view`, and Telegram receives it as a
photo with an inline keyboard offering follow-up actions (variation,
video generation, etc.).

The full pipeline — scene seed → Grok composition → safety embeddings
→ workflow injection → render — is invariant per render. The only
things that change per turn are the scene seed, the outfit state, and
the per-user mood / location values.

## Quick start

```bash
# 1. Bot
git clone <your-fork> && cd ai-chat-manager
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

MIT License — see [`LICENSE`](LICENSE).

Copyright (c) 2026 Junhee Yoon.
