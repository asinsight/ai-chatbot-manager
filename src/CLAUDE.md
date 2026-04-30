# `src/` — Module organization (SFW fork)

This directory holds the runtime Python modules for `ella-chat-publish`. The fork is a SFW-only descendant of `ella-telegram` — all NSFW pathways were removed at fork time.

## Entry point

- **`bot.py`** — Telegram bot entry. Wires up handlers (main / char / imagegen / common), starts the LLM queue, watchdog, and rate limiter, then enters polling. **Main bot is required** — `bot.py` raises `SystemExit` when `MAIN_BOT_TOKEN` or `MAIN_BOT_USERNAME` is empty (M5 strict-main change). The earlier "warn-and-skip-main" behavior was dropped because character / imagegen handlers assume the main bot is alive (deep-link handoffs, onboarding redirects). The platform admin (`platform/lib/bot-process.ts`) mirrors this with a pre-flight 422 (`MAIN_BOT_NOT_CONFIGURED`) before spawn.

## Telegram handlers

- **`handlers_main.py`** — Top-level commands (`/start`, `/help`, `/scene` admin, character selection menu). Routes free-text input to `handlers_char.py` or `handlers_imagegen.py` via `intent_router.py`.
- **`handlers_char.py`** — Character chat loop. Builds the system prompt from `prompt.py`, calls `llm.py`, parses `[STAT:]` tokens to update fixation/mood/location through `history.py`, and exposes the 📷 send-photo button when fixation crosses the threshold (the original arousal gate has been rebound to fixation; arousal does not exist in this fork).
- **`handlers_imagegen.py`** — Image-generation flows: `/random` SFW scene roll, `/edit` partial edits, character-card image rendering. Calls `grok.py` to compose Danbooru tags, then `comfyui.py` to render. There is no `/random NSFW`, no `body_nsfw` merge, and no NSFW LoRA override. The HQ workflow path is read from `os.getenv("COMFYUI_WORKFLOW_HQ", "comfyui_workflow/main_character_build_highqual.json")` (M5) — the platform admin's `/workflows` Stage assignments card writes this env var.
- **`handlers_common.py`** — Shared button/callback helpers used by both char and imagegen handlers (image-action keyboards, message edits, error replies).

## Generation backends

- **`grok.py`** — Grok API client. The five system prompts (`system`, `video_analyzer`, `random`, `classify`, `partial_edit`) are externalized to `config/grok_prompts.json` and loaded at module import (fail-fast — no fallback strings). The video system prompt is loaded separately from `wan_i2v_prompting_guide.md` and exposed as `VIDEO_SYSTEM_PROMPT`.
- **`grok_search.py`** — Grok web-search wrapper used for live-info questions in chat.
- **`llm.py`** / **`llm_queue.py`** — LLM API call layer plus a per-process queue that serializes outbound LLM requests for backpressure / rate control.
- **`comfyui.py`** — ComfyUI image-gen client. Talks to RunPod serverless (production) and a local ComfyUI server (dev). Defines the embedding prefixes:
  - `EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"`
  - `EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazynsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"`
  - `lazynsfw` was moved from positive to negative at fork time so every render actively suppresses NSFW visual elements.
- **`video.py`** — Atlas Cloud video-gen client. Single backend: `alibaba/wan-2.6/image-to-video-flash`. The DaSiWa/RunPod LoRA fallback path was removed; there is no `lora_config` parameter, no `_prepare_loras()`, no `CIVITAI_API_TOKEN`.
- **`video_context.py`** — Short-lived per-call video context (pose hint, motion seed). Trimmed of the original `lora_preset` mapping.

## Data layer

- **`history.py`** — SQLite layer. Owns three tables of interest:
  - `chat_history` / `user_settings` / `usage` — Telegram chat history and onboarding/usage tracking. There is **no** tier column, no `payments` table, no `coupons` table — the open-source build has no billing.
  - `character_stats` — per-(user, character) state. Columns are **`fixation INTEGER`**, **`mood TEXT`**, **`location TEXT`**. There is **no** `arousal`, no `body_nsfw_json`, no `heat_active`, no decay job.
  - `saved_characters` — user-customized character snapshots.
  - `STAT_DELTAS` only includes `{"fixation": {"up": 5, "down": -5}}`.
- **`profile_keys.py`** — Whitelist of allowed keys when persisting/merging character profiles. Mirrors `config/profile_keys.json`.

## Prompt assembly

- **`prompt.py`** — System prompt assembly for character chat. Reads `config/system_prompt.json` master_prompt + the active character card (from `behaviors/`, `persona/`, `images/`) and weaves in fixation/mood/location into a single prompt. The original "Layered Lust" 3-tier structure and arousal-gated speech/response branching are gone — the SFW build has a single fixation-driven IMAGE_AUTONOMY decision.
- **`trait_pools.py`** — Trait pools for character generation (clothing, underwear, hair, eye color, build, scenes). SFW-only: the `BODY_NSFW_*` constants and `roll_nsfw_scene()` / `FORCE_NSFW_SCENE` were removed. `roll_sfw_scene()` reads `config/sfw_scenes.json`.
- **`pose_motion_presets.py`** — Pose-motion preset registry for video generation. Single tier — text-only motion strings keyed by pose. There is no LoRA tier, no `general_nsfw` fallback. Reads `config/pose_motion_presets.json`.

## Routing & safety

- **`intent_router.py`** — Classifies free-text input into 6 intents: `NEW`, `MODIFY`, `EDIT_SAVED`, `RECALL`, `SCENE`, `RESET`. Calls Grok with `CLASSIFY_SYSTEM_PROMPT` (sourced from `grok_prompts.json["classify"]`).
- **`input_filter.py`** — Minor / CSAM safety net. Korean and English regexes that reject any input mentioning underage characters before it reaches the LLM. Carried over verbatim from the original; this is the one place where blocked-content terms are present by design.

## Memory & summarization

- **`summary.py`** — Compacts long chat histories into per-session running summaries that are spliced back into the system prompt.
- **`token_counter.py`** — Cheap tiktoken-based token estimate used to decide when to trigger summarization.

## Operational

- **`watchdog.py`** — Health monitor that pings the LLM queue and ComfyUI/Atlas backends, surfacing failures to logs and (when configured) admin Telegram chat.
- **`rate_limiter.py`** — Per-user sliding-window rate limit (chat messages and image generations counted separately).
- **`logging_config.py`** — Logger setup. Uses a single `TimedRotatingFileHandler` writing to `logs/bot.log` (daily rotation, 30-day retention). The previous `StreamHandler` was removed in M5 — when the bot runs under the platform admin (`platform/lib/bot-process.ts` redirects child stdout+stderr to the same `bot.log`), having both a `StreamHandler` and the `TimedRotatingFileHandler` produced duplicate lines. Stray prints / uncaught tracebacks still land in `bot.log` via the platform's stdout redirect — that's the intended path.

## Reference files

- **`wan_i2v_prompting_guide.md`** — i2v motion-prompt authoring guide. Loaded by `grok.py` as `VIDEO_SYSTEM_PROMPT`. Renamed from the original `wan_nsfw_i2v_prompting_guide.md`; the three NSFW sections (`## NSFW Levels`, `### Composer level selection`, `## AHEGAO VERBATIM`) were stripped. The `### Vulgar anatomy terms — AVOID in motion_prompt` section is intentionally retained as a SFW safety net so the composer never emits vulgar anatomy in motion prompts.

## SFW-fork specifics (vs original `ella-telegram`)

1. **No arousal stat.** Only `fixation`, `mood`, `location` are tracked per character.
2. **No NSFW classifier.** `pose_scene_classifier.py` was not carried into the fork; nothing imports it.
3. **No NSFW scene catalog.** `nsfw_scenes.json` and the NSFW scene roller were dropped.
4. **No LoRA in pose presets.** `pose_motion_presets.py` has a single text-only tier.
5. **Grok prompts externalized.** All five system prompts live in `config/grok_prompts.json`; `grok.py` is pure code with no hard-coded prompt strings.
6. **Single video backend.** Atlas Cloud `wan-2.6/image-to-video-flash` only — the DaSiWa LoRA path is gone.
7. **Embedding prefix re-assigned.** `lazynsfw` is in the negative prefix to suppress NSFW visuals on every render.
