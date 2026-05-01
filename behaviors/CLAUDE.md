# `behaviors/` — Per-character behavior tables

JSON tables that hold a character's *behavior branching*. Where
`persona/` carries the character's identity, `behaviors/` carries the
"what changes as the relationship deepens / mood shifts" table. When
[`src/prompt.py`](../src/prompt.py) assembles the system prompt it
reads the active character's behavior file and splices in only the
guideline that matches the current `fixation` band + `mood`.

## File naming

`charNN.json` (`NN` = zero-padded 2-digit). The bundled distribution
ships one sample:

| File | Character | Notes |
|---|---|---|
| `char05.json` | Jiwon Han — 31-year-old executive assistant (responds in English) | Only sample shipped — operators add more via `/characters` or by hand. |

## File shape

A behaviors file holds one or more of the keys below (each character
fills the parts that matter for it):

| Key | Purpose |
|---|---|
| `proactive_behavior` | Per-fixation-band proactive guidelines (array). Each item: `{ "condition": {"fixation": [low, high]}, "prompt": "..." }`. Convention: 4 tiers — `[0,20]` VERY LOW / `[20,50]` LOW / `[50,80]` MEDIUM / `[80,101]` HIGH. |
| `mood_behaviors` | Per-mood guideline (object). Key = mood string, value = short guideline sentence. May overlap with the same field on `persona/` — both are merged at prompt-assembly time. |
| `mood_triggers` | Mood-transition triggers (array): `{ "trigger": "...", "mood": "..." }`. |

`character_card_schema.json` defines the same `proactive_behaviors`,
`mood_behaviors`, `mood_triggers`, `stat_limits` fields, so you can
put them in either `persona/` or `behaviors/`. Convention in this
distribution: short string/object forms live on the persona card; the
wider branching tables (e.g. the 4-tier fixation table) live in
`behaviors/`.

## Adding a new character

1. Pick the next free `charNN` number.
2. Write `behaviors/charNN.json` — at least populate the 4-tier
   `proactive_behavior` table.
3. Add the matching `persona/charNN.json` and `images/charNN.json`.
4. Validate the bundle against `character_card_schema.json` (the
   platform's `/characters` editor does this on save; stand-alone
   syntax check is `python -m json.tool < file`).
5. See [`docs/character_card_instruction.md`](../docs/character_card_instruction.md)
   for an authoring guide.

## Empty template

```json
{
  "proactive_behavior": [
    {"condition": {"fixation": [0, 20]},  "prompt": "VERY LOW: ..."},
    {"condition": {"fixation": [20, 50]}, "prompt": "LOW: ..."},
    {"condition": {"fixation": [50, 80]}, "prompt": "MEDIUM: ..."},
    {"condition": {"fixation": [80, 101]},"prompt": "HIGH: ..."}
  ]
}
```
