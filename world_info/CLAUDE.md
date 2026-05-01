# `world_info/` — Per-character lorebook (M6)

Free-form world-knowledge entries that get conditionally spliced into the
character-chat system prompt at runtime. Modeled after SillyTavern's lorebook:
each entry pairs a list of trigger keywords with a content blob; when any
keyword appears in the latest user message + last 4 chat turns, the content
is injected into the prompt.

Loaded by [`src/prompt.py`](../src/prompt.py) — `_load_world_info()` +
`_match_world_info()`. Edit through the platform admin's `/lorebook` page
or by hand on disk; the bot needs a restart for changes to take effect
(the loader caches per-process).

## Files

### `<world_id>.json`
A lorebook file. Filename `<world_id>` (without extension) is the world id used
in the mapping below. Naming convention: `^[a-z][a-z0-9_]*$` (the `mapping`
basename is reserved). Shape:

```json
{
  "_doc": "Optional human-readable note. Underscore-prefixed keys are passthrough metadata; the loader and UI ignore them.",
  "entries": [
    {
      "keywords": ["Director Park", "boss"],
      "content": "Jiwon's boss is Director Park, a senior VP in his early 50s ...",
      "position": "background"
    },
    ...
  ]
}
```

`position` controls **where** the matched content is spliced into the prompt:

| Value | Splice site | Use for |
|---|---|---|
| `background` | Early — right after stats/mood, before chat history (`World setting:` block) | Stable backdrop facts (people, places, habits) |
| `active` | Late — appended to `post_history_instructions`, after chat history | Situational / current-context reminders that should bias the response immediately (LLMs over-weight the tail of the prompt) |

Optional top-level field `active_format_rule` (string) prefixes the active
block with a custom instruction, e.g. `"These are situational facts — weave
them in naturally:"`.

### `mapping.json`
Maps each `char_id` to a `world_id`. Lookup: `world_info/<value>.json`. A
character not present in this mapping falls back to the legacy
`world_info/<char_id>.json` convention, so existing one-to-one setups keep
working unchanged.

```json
{
  "_doc": "Maps each character to its lorebook (world_info file). ...",
  "char05": "char05"
}
```

## Bundled samples

- **`char05.json`** — Sample lorebook for Jiwon Han with 6 entries
  (Director Park, promotion review, hot yoga, restaurant spreadsheet,
  Outlook calendar sync, Bluestone cafe). Mix of `background` and `active`.

The fork ships only `char05` because that's the only sample character. New
characters added through the `/characters` admin start with no lorebook —
operators create a world (or share an existing one) via `/lorebook` and
then map the character to it.

## Editing

- The bot caches lorebook content per-process; restart after edits.
- Platform `/lorebook` page does shape validation (zod) + atomic write +
  automatic `.bak` backup. Direct disk edits skip those guards — verify
  with the platform's Test pane after.
- Worlds in active use cannot be deleted from the platform (`WORLD_IN_USE`).
  Remap the affected characters first.
