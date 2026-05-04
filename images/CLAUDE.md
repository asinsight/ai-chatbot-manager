# `images/` — Per-character image-config cards

JSON cards that describe each character's appearance / body type as
Danbooru-tag pools. When the bot renders an image,
[`src/handlers_imagegen.py`](../src/handlers_imagegen.py) →
[`src/grok.py`](../src/grok.py) reads this file and splices the tags
into the positive prompt so the character's look stays consistent
across renders.

## File naming

`charNN.json` (numbering is shared with `persona/` and `behaviors/`).

| File | Character | Notes |
|---|---|---|
| `char05.json` | Jiwon Han — 31-year-old executive assistant (responds in English) | Only sample shipped. |

## Fields (Danbooru-tag format)

| Field | Meaning |
|---|---|
| `char_id` | Self-identifier (`charNN`). |
| `appearance_tags` | Always-applied face / hair / skin tags. Comma-separated Danbooru-tag string. |
| `clothing` | Default outfit set (top / bottom / outerwear / shoes). |
| `alt_outfit` | Alternate outfit set (work-mode, off-day, etc). |
| `underwear` | Underwear set. Only used as a layer when the outfit allows visibility — not visible under e.g. a full-length gown. |
| `body_shape.size` | Height / build keyword (e.g. `average_height`, `slim`). |
| `body_shape.build` | Mass / muscle keyword. |
| `body_shape.curve` | Waist line keyword. |
| `body_shape.accent` | Optional accent tag (e.g. `collarbone`) — framing-conditional. |
| `body_shape.ass` | Hip / silhouette tag — framing-conditional. |
| `breast.size` | E.g. `medium_breasts`. |
| `breast.feature` | Optional detail tag — framing-conditional. |

`body_shape.accent` / `body_shape.ass` / `breast.feature` are applied
conditionally based on the camera angle (framing). The exact rules
live in `config/grok_prompts.json` under the `system` / `random`
prompts (the Danbooru-tag composer).

## Empty template

```json
{
  "char_id": "charNN",
  "appearance_tags": "1girl, solo, adult, ...",
  "clothing": "...",
  "alt_outfit": "...",
  "underwear": "...",
  "body_shape": {
    "size": "average_height",
    "build": "slim",
    "curve": "natural_waist",
    "accent": "",
    "ass": ""
  },
  "breast": {
    "size": "medium_breasts",
    "feature": ""
  }
}
```

## Editing through the admin

The `/characters/[charId]` editor's "Images" tab edits this file
through schema-driven widgets. Saves are atomic + auto-backed up next
to the live file.

## Profile thumbnails

`images/profile/<char_id>.png` (if present) is the small avatar shown
on the main bot's `/start` character cards. Drop the PNG in by hand —
there is no upload UI.
