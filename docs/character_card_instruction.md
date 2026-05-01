# Character card authoring guide

This guide walks through every JSON file that defines a character. The
schema lives in `character_card_schema.json` at the repo root; the
platform admin's `/characters` page validates against it on save.

When you add a character you write at minimum:

| File | Role | Used for |
|---|---|---|
| `persona/charNN.json` | Identity + dialogue rules | LLM prompt assembly |
| `images/charNN.json` | Image-tag config | Hints fed to the Danbooru-tag composer |

Optional:

| File | Role |
|---|---|
| `behaviors/charNN.json` | Per-fixation-band action / question patterns |
| `world_info/charNN.json` | Lorebook (keyword-triggered context) |
| `jobs/<key>.json` | Profession-specific facts / vocabulary / routines |
| `images/<charId>.png` | ComfyUI IPAdapter FaceID anchor |
| `images/profile/<charId>.png` | Avatar shown on the main bot's `/start` cards |

Authoring tip: write a one-page sheet first (see
[`character_sheets.md`](character_sheets.md)) and only then start
filling in JSON.

---

## Part 1 — `persona/charNN.json`

### Field-role separation

Each field owns *one* concern. Don't repeat the same content across
fields.

| Field | Role | Don't put here |
|---|---|---|
| `description` | Appearance, background, world, daily life | Personality / behavior |
| `personality` | Personality traits, hobbies, likes / dislikes | Per-fixation behavior or per-stimulus reactions |
| `scenario` | Relationship to `{{user}}`, story premise | Repeating personality |
| `system_prompt` | Speech / tone rules, emoji policy, safety guardrails | Per-fixation behavior (use `stat_personality` / `proactive_behaviors`) |
| `post_history_instructions` | Reminder injected after the chat history | Re-stating personality from `system_prompt` |
| `stat_personality` | What `fixation` means + per-tier tone | Per-tier action patterns (use `proactive_behaviors`) |
| `proactive_behaviors` | Per-tier proactive action patterns | Restating `personality` / `stat_personality` |
| `mood_behaviors` | Per-mood action guideline (only the active one is injected) | Restating `system_prompt` Emotional Reactions |
| `interests` | The character's own topics (hobbies, fields of study) | Anything that's about the user |

### Field reference

#### 1. `name` (required)
Display name. Substituted into prompts via `{{char}}`.

```json
"name": "Yerin Kang"
```

#### 1-1. `profile_summary_ko` (optional, recommended)
A short summary shown on the main bot's `/start` and `/char` UI (2-3
lines). Not injected into prompts. Originally Korean; can be any
language.

```json
"profile_summary_ko": "Yerin Kang (21) — psychology student\nBright, friendly, easy to talk to."
```

#### 1-2. `jobs` (optional)
Job / academic-key list. Each key resolves to `jobs/<key>.json` and
loads `facts_*` / `vocabulary` / `daily_routines` for that profession
into the prompt. Multi-job allowed.

```json
"jobs": ["psychology_student"]
```

#### 2. `description` (required)
**Appearance and background.** Inserted near the top of the prompt.
Age, role, daily-life snapshots, physical description. No personality
or behavior.

```json
"description": "You are Yerin Kang, a 21-year-old psychology student. You have long wavy brown hair…"
```

#### 3. `personality` (required)
**Personality traits only.** No behavior descriptions, no fixation
references.

```json
// Good
"personality": "Outwardly bright and friendly. Curious by nature. Hobbies: psychology, photography. Likes: thoughtful conversations. Dislikes: being ignored."

// Bad — behavior description belongs in proactive_behaviors
"personality": "You become anxious when {{user}} ignores you and demand they pay attention."
```

#### 4. `scenario`
Relationship to the user, story premise.

```json
"scenario": "{{char}} met {{user}} through a mutual friend. They've been chatting casually…"
```

#### 5. `first_mes` (required)
The first message the character sends when a new conversation starts.

#### 6. `mes_example`
Few-shot dialogue, separated by `<START>` blocks. Use the `{{user}}` /
`{{char}}` macros.

- 2–5 blocks recommended.
- The most direct way to shape the LLM's tone — the bot weighs these
  examples heavily.
- Include proactive patterns (the character carrying the conversation
  when the user gives short replies).
- Include any special-trigger reactions (e.g. specific keyword → strong
  emotional response).

#### 7. `system_prompt` (required)
The character's **rules**. Inserted second in the prompt.

Include:
- Speech / tone rules (formal / casual register, accent, sentence-end
  pattern).
- Emotional Reactions (stimulus → reaction mapping).
- **Safety guardrails** — short, in-character ways to deflect
  inappropriate requests. The global safety net is
  `src/input_filter.py` + `config/sfw_denylist.json`, but a 1–2 line
  per-character guideline keeps responses consistent in tone.
- Emoji rules.
- Tone guide.
- Any character-specific rule.
- Special-trigger reactions for specific input patterns.
- Optional `# Comfort Style` section — how this character listens / consoles.

Don't include:
- Per-fixation behavior — that's `stat_personality` + `proactive_behaviors`.
- Hard sentence-count limits — `max_tokens` already bounds responses.
- Location format rules — handled by the global master prompt.

#### 8. `post_history_instructions`
Inserted after the chat history, just before the user message. The
**most influential** slot.

Include:
- Stat (fixation) reflection reminder.
- Sentence-variety rule ("never reuse the sentence structure from the
  last 3 responses").
- Discovery hint (injected dynamically by the runtime when relevant).

Don't include:
- Personality / tone rules already in `system_prompt`.
- Hard sentence-count limits.

```json
"post_history_instructions": "Ensure responses reflect current fixation level accurately. Never reuse the same sentence structure or question from your last 3 responses. Vary your expressions."
```

#### 9. `creator_notes`
Memo for the card author. Not injected into prompts.

#### 10. `anchor_image`
ComfyUI IPAdapter FaceID reference image filename. Place the file in
the ComfyUI `input/` directory. Empty string → FaceID is bypassed.

#### 11. `image_prompt_prefix`
Positive Danbooru-tag prefix prepended to every image render for this
character. Use it for appearance + quality tags only.

- Don't include framing / gaze tags (`looking_at_viewer`, `upper_body`,
  etc.) — let the composer decide those.

#### 12. `image_negative_prefix`
Negative Danbooru-tag prefix. The bot's
`comfyui.py:EMBEDDING_NEG_PREFIX` already prepends
`embedding:illustrious/lazy-nsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand`
to every render — you don't need to repeat those embeddings here.

#### 13. `stat_moods` (required)
List of moods this character can express. Used as the `mood:` value of
the runtime `[STAT:]` signal. 5–7 moods recommended (e.g. `happy`,
`shy`, `angry`, `sad`, `playful`, `serious`, `tired`).

#### 14. `proactive_behaviors` (required)
**Per-fixation-band** proactive action patterns. Injected into the
prompt verbatim.

```json
"proactive_behaviors": "VERY LOW (<20): … LOW (<30): … MID (30-60): … HIGH (>60): …"
```

#### 15. `interests`
Topics the character actively explores. Empty array disables the
discovery DEEPEN_TEMPLATE.

```json
// Good
"interests": ["psychology", "indie music"]

// Bad — interests are about the character, not the user
"interests": ["{{user}}'s daily schedule", "{{user}}'s social circle"]
```

#### 16. `stat_personality` (required)
What `fixation` means for this character + the conditions that raise /
lower it + the per-tier tone matrix.

Include:
- What `fixation` represents for this character (attachment, interest,
  intimacy…).
- Triggers (rises when … / falls when …).
- Per-tier tone guide (LOW / MID / HIGH speech and demeanor).

Don't include:
- Per-tier action patterns — those go in `proactive_behaviors`.

#### 17. `discovery_hint_template`
User-profile discovery hint template. `{topic}` is substituted with
the unfamiliar topic name. Empty string falls back to the default.

```json
// Curious character
"discovery_hint_template": "You don't know {{user}}'s {topic} and you're curious. Ask casually."

// Reserved character
"discovery_hint_template": "If {{user}} mentions {topic}, show interest and follow up."

// Executive-assistant character
"discovery_hint_template": "Note: {{user}}'s {topic} is unknown. If relevant to serving them, inquire formally."
```

#### 18. `mood_behaviors` (required)
Per-mood action guideline. Only the matching entry is injected into the
prompt at any one time. Define one per `stat_moods` entry.

```json
"mood_behaviors": {
  "happy": "Action description",
  "angry": "Action description"
}
```

#### 19. `stat_limits` (optional)
Per-character cap on per-turn fixation deltas. Defaults to ±5 globally.

```json
"stat_limits": {
  "fixation": {"up": 2, "down": -3}
}
```

---

## Part 2 — `images/charNN.json`

Image-tag config used as a hint by the Danbooru-tag composer. Each
field is forwarded to the composer with a label so it can prioritize
identity-critical tags.

### Schema

```json
{
  "clothing": "...",
  "underwear": "...",
  "body_shape": {
    "size": "",          // BODY_SIZE — height
    "build": "",         // BODY_BUILD — frame / muscle / mass
    "curve": "",         // BODY_CURVE — silhouette
    "accent": ""         // BODY_ACCENT — collarbone, etc.
  },
  "expressions": { /* optional */ },
  "mood_triggers": { /* optional */ }
}
```

### Per-category guide

| Category | Type | Meaning | Notes |
|---|---|---|---|
| `clothing` | string | Default outfit Danbooru tags | E.g. `"white crop top, blue denim shorts"` — always a full set (top + bottom or dress only) |
| `underwear` | string | Underwear set | Only used as a layer when the outfit allows visibility (e.g. a strap glimpse). Not a standalone exposure context. |
| `body_shape.*` | identity | Silhouette identity | **Always include** — what's visible while clothed |
| `expressions` | optional | Per-mood expression preset | Composer applies when the active mood matches |
| `mood_triggers` | optional | Keyword → mood lock | Forces a mood transition when a keyword is detected |

### Tag vocabulary source

`src/trait_pools.py` is the canonical pool. Per-category lists:
`BODY_SIZE`, `BODY_BUILD`, `BODY_CURVE`, `BODY_ACCENT`.

### Example — bright character

```json
{
  "clothing": "white crop top, blue denim shorts",
  "underwear": "",
  "body_shape": {
    "size": "medium_height",
    "build": "slim",
    "curve": "narrow_waist",
    "accent": "collarbone"
  }
}
```

### `expressions` (optional)

Mood key → Danbooru expression tags. The composer applies the matching
preset when it sees the current mood.

```json
"expressions": {
  "shy": "blush, parted lips, looking_away",
  "happy": "smile, closed_eyes, :d"
}
```

### `mood_triggers` (optional)

Keyword detection → forced mood lock. Reinforces character voice.

```json
"mood_triggers": {
  "shy": ["compliment", "pretty"],
  "playful": ["let's play", "I'm bored"]
}
```

### Compound tag pitfall

3-segment compound tags (color + length + item, etc.) usually weren't
in the SDXL Illustrious training set and produce off-target results.
Split into individual tags following Danbooru convention.

**Bad** (3-segment compound):
- `beige_knee_length_skirt`
- `short_black_pleated_skirt`

**Good** (split):
- `beige_skirt, midi_skirt`
- `black_skirt, pleated_skirt, short_skirt`

2-segment compounds are usually fine (`black_lace_panties`,
`pencil_skirt`). Fantasy outfits (`full_plate_armor`, `gothic_dress`)
have less training coverage and may distort — consider alternatives.

### Pitfalls / dos & don'ts

1. **Don't duplicate body / appearance tags.** Hair / eye / skin tags
   live in `persona.image_prompt_prefix` only. Don't repeat them in
   `images/charNN.json`'s body fields.
2. **Weight syntax is supported.** `(blush:1.2)` and similar SDXL
   weight syntax work fine.
3. **Empty fields use `""`.** No tag → empty string. The composer
   skips empty values automatically.

---

## Part 3 — `behaviors/charNN.json`

Per-fixation-band action / question patterns. `src/prompt.py` loads
this file and injects only the matching tier into the prompt every turn.

### Schema

```json
{
  "proactive_behavior": [
    { "condition": { "fixation": [0, 40] },   "prompt": "Light interest: ... CARETAKER QUESTIONS: ..." },
    { "condition": { "fixation": [40, 80] },  "prompt": "Engaged: ... EMOTIONAL CHECK-INS: ..." },
    { "condition": { "fixation": [80, 101] }, "prompt": "Devoted: ... PERSONAL QUESTIONS: ..." }
  ]
}
```

### Design notes

- **Tier count**: 3 tiers recommended for `proactive_behavior`.
- **Range**: `[min, max)` — upper bound exclusive. Don't overlap.
- **Top tier should be `[X, 101]`** — `fixation` maxes at 100, so 101
  ensures 100 is included.
- **Include question patterns**: 2–5 example questions per tier so the
  character actively pulls the user's information out.

### Notes

- **Don't duplicate `mood`** — `mood_behaviors` is per-emotion;
  `proactive_behavior` is per-fixation-tier. Different axes.
- **Role split with `persona.proactive_behaviors`** — the persona
  field carries a one-line summary of "this character is roughly this
  proactive"; `behaviors/` carries the per-tier detail.
- **The bot still runs without this file** but responses become flat —
  recommended for every character.

---

## Part 4 — `world_info/charNN.json` (lorebook)

Keyword-triggered context entries (life history, past events,
background facts). SillyTavern lorebook style. `src/prompt.py`'s
`_load_world_info()` (M6) consults `world_info/mapping.json` first to
pick the right file (one `world_id` can be shared by multiple
characters), falling back to the legacy `world_info/<char_id>.json`
when the character isn't in the mapping.

### Schema

```json
{
  "entries": [
    {
      "keywords": ["high school friend", "old friend"],
      "content": "Lost touch with their closest high-school friend after graduation…",
      "position": "background"
    },
    {
      "keywords": ["mother", "mom"],
      "content": "...",
      "position": "background"
    }
  ]
}
```

`position` controls **where** matched content is spliced into the
prompt:

- `background` → injected early, before the chat history (`World
  setting:` block). Good for stable backdrop facts.
- `active` → appended to `post_history_instructions`, after the chat
  history. Good for situational reminders that should bias the
  immediate response (the LLM weights the prompt tail more heavily).

### Recommended categories (7–10 entries per character)

1. **past_friendships** — past friend / acquaintance relationships
2. **family** — parents / siblings
3. **younger_days** — school years, childhood
4. **career_origin** — what led to the current job
5. **funny_anecdotes** — funny / cute past events
6. **origin_event** — the event that shaped the core personality
7. **hidden_contrast** — facets that contradict or hide behind the current persona

### Keyword strategy

- **Don't pick keywords that are too broad.** "Old", "before" match
  almost anything → noise. Use specific phrases like "high school
  friend", "first job".
- **`origin_event` should be especially tight.** If it triggers too
  often the character keeps reciting the same backstory — keep
  keywords ≤ 13 specific phrases.

### Notes

- Without this file the bot still runs — the character just answers
  past-event questions generically. Worth adding for immersion.

### Mapping (M6)

Edit `world_info/mapping.json` (via the platform's `/lorebook` page or
by hand) to point a character at a specific world file. The mapping
allows multiple characters to share one world (e.g. coworkers in the
same office sharing an `office_world.json`).

---

## Part 5 — `jobs/<key>.json` (optional)

Per-profession facts / vocabulary / daily-routines that get injected
when the character has the matching `persona.jobs` key. Lets you
sprinkle profession-specific detail into the dialogue.

### Schema

`jobs/_schema.json` is the source of truth. Core fields:

- `facts_ko` / `facts_en` — profession facts.
- `vocabulary` — domain vocabulary.
- `daily_routines` — daily-routine patterns.

### Reuse vs. create

- If an existing job key fits, just add it to `persona.jobs` — no need
  to create a new file.
- For a new profession, create `jobs/<new_key>.json` (English authoring
  recommended for token economy).

The `jobs/` folder ships empty in this distribution.

---

## Part 6 — Adding a character: full checklist

### Required files

- [ ] `persona/charNN.json` — character card (Part 1).
- [ ] `images/charNN.json` — image-tag config (Part 2).
- [ ] `behaviors/charNN.json` — fixation-tier proactive_behavior (Part 3). Without this, responses are flat.

### Optional files

- [ ] `world_info/<world_id>.json` — lorebook (Part 4).
- [ ] Add a row to `world_info/mapping.json` mapping `charNN` → that world id, if you want a non-legacy world.
- [ ] `jobs/<new_key>.json` — only if introducing a new profession (Part 5).
- [ ] `images/<charNN>.png` — IPAdapter FaceID anchor (FaceID is bypassed when missing).
- [ ] `images/profile/<charNN>.png` — main-bot card thumbnail (text fallback when missing).

### Bot-side configuration

These are auto-handled when you create the character through the
platform's `/characters` page. If editing by hand:

- [ ] `src/history.py` `INITIAL_STATS` — initial fixation / mood. (Defaults are usually fine.)
- [ ] `src/history.py` `DISCOVERY_ALLOWED_MOODS` — moods that may be paired with discovery hints.
- [ ] `src/handlers_main.py` `_CHAR_ORDER` — display order on the main bot's `/start` / `/char` UI.
- [ ] `src/handlers_imagegen.py` `CHAR_NAME_MAP` (optional) — alias → char_id for the imagegen bot.

### Environment variables (`.env`)

- [ ] `CHAR_BOT_<charId>` — Telegram bot token from `@BotFather`.
- [ ] `CHAR_USERNAME_<charId>` — bot username (no `@`).

The main bot only lists a character on its menu when **both** the
token and the username are set.

### Auto-handled (no manual work)

- Bot registration: `bot.py` auto-loads any `behaviors/charNN.json`.
- Stat system: works as soon as `INITIAL_STATS` has the row.
- Discovery hints: active when `discovery_hint_template` is non-empty.
- Mood behaviors: active when `mood_behaviors` is non-empty.
- Job knowledge: auto-loads any `persona.jobs` keys via `jobs/<key>.json`.
- Lorebook: auto-loads via `world_info/mapping.json` + matching world file.
- Behaviors: auto-loads `behaviors/charNN.json` when present.

---

## Common mistakes

### `persona/charNN.json`

1. **Putting behaviors in `personality`** — "you become anxious and
   demand…" goes in `proactive_behaviors`.
2. **Restating system_prompt rules in `post_history_instructions`** —
   tone / personality belong in `system_prompt` only.
3. **Putting user actions in `interests`** — `"{{user}}'s schedule"`
   isn't an interest.
4. **Putting per-fixation behaviors in `stat_personality`** — that's
   `proactive_behaviors`'s job.
5. **Putting framing tags in `image_prompt_prefix`** — let the
   composer decide gaze / framing.
6. **Hard sentence-count limits** — `max_tokens` 500 caps the response
   naturally; an explicit limit usually hurts.
7. **One-tone `mes_example`** — the LLM converges on whatever tone the
   examples set. Mix across fixation tiers.

### `images/charNN.json`

8. **Hair / eye / skin tags in body fields** — appearance lives in
   `persona.image_prompt_prefix` only.
9. **`body` as a flat string** — old schema. Use the structured
   `body_shape` object.
10. **Space-separated tags** — Danbooru convention is underscore
    (`large_breasts`, NOT `large breasts`).
11. **3-segment compound tags** — split them (see Part 2).

### `behaviors/charNN.json`

12. **Skipping the file** — bot runs but responses are flat. Always create.
13. **No questions in `proactive_behavior`** — the character can't
    pull info from the user. Include 2–5 example questions per tier.
14. **Top tier `[80, 100]`** — `100` isn't included. Use `[80, 101]`.
