# `config/` — JSON configuration (SFW fork)

Runtime configuration for `ella-chat-publish`. All five files in this directory are required at startup; the bot will fail to import `grok.py` if `grok_prompts.json` is missing or invalid.

## Files

### `profile_keys.json`
Whitelist of keys allowed when merging/saving character profiles. Used by `src/profile_keys.py` to drop unknown fields when applying partial edits to a saved character. Schema-style flat list — no NSFW-specific keys (`body_nsfw` is not present).

### `grok_prompts.json`
Externalized system prompts for the Grok API client. Loaded once at `src/grok.py` import time (fail-fast — missing keys or empty strings raise `RuntimeError`; there are no fallback strings). Keys (5):

| Key | Used by | Purpose |
|---|---|---|
| `system` | `generate_image_prompt()` | Danbooru tag generator for character image gen. SFW-only ruleset — clothing always full and intact, mandatory SFW negative block, `BLOCKED` response if minor implied. |
| `video_analyzer` | `analyze_video_scene()` | Decomposes the source image into static_appearance / pose_state / motion_hints / environment for the i2v composer. `safety_level` is hard-coded to `"SFW"` (or `"BLOCKED"` for minor signals). |
| `random` | `/random` button | Generates a SFW scene description. |
| `classify` | `intent_router.py` | Classifies free-text input into 6 intents (NEW / MODIFY / EDIT_SAVED / RECALL / SCENE / RESET). |
| `partial_edit` | character edit flow | Applies partial edits to a saved character profile (clothing swap, hair-color change, etc.). |

The historical `video_system` key is **not** in this JSON — `grok.py` loads the i2v guide separately from `src/wan_i2v_prompting_guide.md`.

Variable interpolation uses `${var}` style placeholders (resolved via `string.Template`), to avoid clashing with literal `{...}` JSON-example fragments in the prompt bodies.

### `system_prompt.json`
Two top-level fields consumed by `src/prompt.py`:
- `master_prompt` — base character-chat system prompt. SFW-only — the original Section 2 (PHOTO SENDING explicit acts), Section 5 (PHYSICAL REALISM NSFW), and Section 5-1 (CLIMAX/RELIEF) are gone. Photo-send guidance covers only daily life / hobby / scenery / expression / style / pose scenarios.
- `image_signal_format` — token format the LLM uses to request an image send (e.g. `[SEND_IMAGE: ...]`). SFW-only signals.

### `sfw_scenes.json`
SFW scene catalog used by `trait_pools.roll_sfw_scene()` (called from `handlers_imagegen.py` for the `/random` SFW button). Each entry holds a `pose_pool`, `camera_pool`, and `scene_tags` block. There is no companion `nsfw_scenes.json` in this fork.

### `pose_motion_presets.json`
Pose-motion presets for video generation, loaded by `src/pose_motion_presets.py`. Flat schema: each entry is `{ pose_key: { motion_text: "..." } }`. The original two-tier structure (`sfw` / `nsfw` / `explicit`) was collapsed to a single text-only motion string per pose. There is no LoRA tier, no `general_nsfw` fallback.

## SFW-fork drops (not present in this directory)

These files were intentionally not carried over from the original `ella-telegram/config/`:

- **`nsfw_scenes.json`** — full NSFW scene catalog (and `.bak`). DROPPED.
- **`lora_presets.json`** — was carried in by C4 audit but every preset was NSFW-tier; the file ended up empty/unused and was DROPPED. Image-gen no longer applies any character LoRA — only the `EMBEDDING_POS_PREFIX`/`EMBEDDING_NEG_PREFIX` defined in `src/comfyui.py`.
- **`dasiwa_aio_defaults.json`** — DaSiWa AIO video workflow defaults. DROPPED by C6 along with the rest of the DaSiWa fallback path; Atlas Cloud handles all video generation now.

## Loading order at boot

1. `grok.py` import → reads `grok_prompts.json` → fails fast on any error.
2. `prompt.py` import → reads `system_prompt.json`.
3. `trait_pools.py` import → reads `sfw_scenes.json`.
4. `pose_motion_presets.py` import → reads `pose_motion_presets.json`.
5. `profile_keys.py` import → reads `profile_keys.json`.

## Editing guidelines

- **Test locally first.** Restart the bot after every JSON change — there is no hot-reload.
- **`grok_prompts.json` is fail-fast.** Validate JSON syntax (`python -m json.tool`) before deploying.
- **Never inline `{var}` curly placeholders into `grok_prompts.json` values** unless the loader is updated. Use `${var}`.
- **Keep SFW invariants in mind.** Adding any prompt fragment that produces nudity / sex / minor content tags violates the fork's contract and the SFW negative block in `system` will partially counteract it but should not be relied on.
