# `persona/` — Per-character persona cards

JSON cards that hold each character's *identity*. The schema is a
SillyTavern V2-style character card defined in
`character_card_schema.json` at the repo root. At runtime
[`src/prompt.py`](../src/prompt.py) reads the active character's persona
card and splices `description` / `personality` / `scenario` /
`mes_example` / `system_prompt` etc. into the system prompt that is
sent to the LLM.

## File naming

`charNN.json` (numbering is shared with `behaviors/` and `images/`).
The bundled distribution ships with one sample:

| File | Character | Notes |
|---|---|---|
| `char05.json` | Jiwon Han — 31-year-old executive assistant (responds in English) | The only sample shipped — operators add more via the platform's `/characters` page or by hand. |

## Required + optional fields

Defined by `character_card_schema.json`. Required: `name`, `description`,
`first_mes`, `system_prompt`. Everything else is optional.

| Field | Meaning |
|---|---|
| `name` | Display name. Substituted into prompts via the `{{char}}` macro. |
| `profile_summary_ko` | One-line summary shown in the admin list (originally Korean; can be any language). |
| `description` | Free-form description — appearance, background, personality. |
| `personality` | Personality keywords / short sentences. |
| `scenario` | Current RP situation. |
| `first_mes` | Opening message sent on a fresh conversation. |
| `mes_example` | Few-shot dialogue separated by `<START>` blocks. |
| `system_prompt` | Speech style / response rules / tone guide / emoji rules — the character's core directive. |
| `post_history_instructions` | Reminder injected after the chat history. |
| `creator_notes` | Card-author memo (not injected into prompts). |
| `anchor_image` | ComfyUI IPAdapter FaceID reference image filename (must already be uploaded to the ComfyUI input directory). |
| `image_prompt_prefix` / `image_negative_prefix` | Positive / negative Danbooru-tag prefix prepended to every image render for this character. |
| `stat_personality` | Per-character description of what `fixation` means and what raises / lowers it. Injected into the prompt. |
| `stat_moods` | Allowed mood strings (the `mood:` value of the `[STAT:]` signal). |
| `mood_behaviors` / `mood_triggers` | Same shape as in `behaviors/`. Use the persona variant when the table is short and you want it inline. |
| `proactive_behaviors` | Short summary of the character's self-driven behaviors (often `"Follows behaviors/ rules based on fixation level."`). |
| `interests` | Topics the character actively explores. |
| `discovery_hint_template` | Hint template for unfamiliar topics. Empty string falls back to the default `DISCOVERY_TOPICS` template. |
| `jobs` | Job-key list. Each key matches `jobs/<key>.json` for background-knowledge injection. The bundled `jobs/` folder is empty in this distribution. |
| `stat_limits` | `{ "fixation": { "up": N, "down": -N } }` — per-character cap on per-turn fixation deltas. |

## Macros

- `{{user}}` — replaced at runtime with the chatting user's name.
- `{{char}}` — replaced with the persona card's `name` field.

Both macros work in `description`, `scenario`, `first_mes`, `mes_example`,
`system_prompt`, `proactive_behaviors`, `mood_behaviors`, `interests`, etc.

## Adding a new character

1. Pick a `charNN` number (shared with `behaviors/` and `images/`).
2. Write `persona/charNN.json` — fill the 4 required fields at minimum.
   Recommended baseline: 3+ `<START>`-separated blocks in `mes_example`,
   4–5 entries in `stat_moods`, 3+ entries in `interests`.
3. The platform's `/characters` page validates the file against
   `character_card_schema.json` before saving — field-name typos and
   type mismatches surface as ajv errors. The same validation runs
   when you create the character through the admin in the first place.
4. See [`docs/character_card_instruction.md`](../docs/character_card_instruction.md)
   for an authoring guide.

## Editing through the admin

The `/characters` page in the platform admin gives you a schema-driven
form (22 fields with widget dispatch: text / textarea / Monaco / chips
/ kv / trigger-list / stat-limits) plus a Raw JSON mode that mounts
each of the three files (`persona/` + `behaviors/` + `images/`) in
its own Monaco editor. Saves are atomic, write a `.bak` next to each
file, and validate against `character_card_schema.json` before writing.
