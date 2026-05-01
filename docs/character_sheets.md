# Character sheet authoring guide

> A "character sheet" is a one-page human-readable summary of a
> character — written before the JSON. It exists to force you to
> think through tone, reactions, and constraints before you start
> filling in `persona/charNN.json`.
>
> The actual JSON authoring guide lives in
> [`character_card_instruction.md`](character_card_instruction.md).

---

## How to use this guide

1. When you have a new character idea, copy the **Template** section
   below into a new file (`docs/character_sheets/charNN.md` is the
   recommended path — this file is the guide; the per-character sheets
   are separate).
2. Fill in the seven sections. Then move on to
   [`character_card_instruction.md`](character_card_instruction.md) to
   produce `persona/charNN.json`, `images/charNN.json`, and
   `behaviors/charNN.json`.
3. A sheet should fit in one page (40–80 lines). If it grows past two
   pages, the description and personality sections probably aren't
   separated cleanly.

## House style (applies to every sheet)

- **No explicit sexual descriptions in the sheet.** Tones like
  "shy", "fluttery", "intimate", "mildly teasing" are fine. Action /
  body descriptions like "undresses", "touches", "panting" do not
  belong in the sheet — and would conflict with the bot's safety net
  (`config/sfw_denylist.json`, the Grok system prompt's negative
  block, the image-gen negative embedding).
- **Age**: every character is 19+. The runtime input filter in
  `src/input_filter.py` blocks underage / loli / shota mentions
  outright, so do not write them into the sheet either.
- **Married / forbidden-relationship concepts are fine** as long as
  the tone stays on the emotional axis (loneliness, longing,
  hesitation). Do not script the physical infidelity itself.
- **Yandere / suggestive concepts are fine** when the axis is
  "obsession / jealousy / possessiveness" expressed emotionally — not
  through violence or threat.
- If a concept loses its meaning under those constraints (because its
  core identity depends on explicit content) it is not a fit for this
  project — pick a different concept.

---

## Template

Copy these seven sections into a new sheet. The exact section order
isn't load-bearing — the goal is just to fill all of them.

### 1. One-line introduction (header)

```
# {{name}} (age {{N}}) — {{one-line summary}}
```

Examples (fictional):
- `# Yuna Kim (24) — multi-hobby designer with a free-spirited streak`
- `# Jiwon Park (29) — calm cafe owner who runs a tight ship`

### 2. Basic info

```
## Basics
- Name / Age / Job-or-role
- Appearance: height / build / hair / eyes / fashion sense (no body description; everyday SFW outfit only)
- Hobbies: 3–5 (character-specific; "watches the user" doesn't count)
- Likes: 3–5 (objects / situations / emotions)
- Dislikes: 3–5 (objects / situations / emotions)
```

Notes:
- **Appearance** stays at the level of "designer street-style" /
  "casual" / "tailored office wear". No exposure / underwear /
  body-part detail.
- **Hobbies** are character-specific (psychology, photography,
  baking…) — they pass through to the persona's `interests` array.

### 3. Personality

```
## Personality
- {{Personality keyword 1}}: 1–2 line description
- {{Personality keyword 2}}: 1–2 line description
- {{Inner-vs-outer gap}}: 1–2 lines (optional)
- {{Stance in relationships}}: 1–2 lines
```

- **No behavior descriptions here** — "when the user does X, character
  does Y" belongs in the next section.
- Keep this to 4–6 lines.

### 4. Emotional reactions

```
## Emotional reactions
- {{user}} does {{stimulus 1}} → {{reaction 1}} ("dialogue example")
- {{user}} does {{stimulus 2}} → {{reaction 2}} ("dialogue example")
... (6–8 entries recommended)
```

Suggested stimulus categories:
- Compliment / appearance compliment
- Indifference / a cold reply
- Tenderness / consolation
- Teasing / jokes
- Asking for advice / saying "I'm having a hard time"
- Going silent for a long stretch
- Character-specific trigger (e.g. for an executive-assistant
  character: receiving a "command")

A short one-line dialogue example per item makes the eventual
`mes_example` section easy to write.

### 5. Speech style

```
## Speech
- Default register: formal/casual, tone (bright/quiet/cold/etc), sentence-ending pattern
- Emoji policy: which emojis, how many per response
- Speech changes by mood:
  → When in a good mood: ...
  → When shy: ...
  → When anxious: ...
```

- Per-character emoji volume varies a lot (a bright character: 1–2
  emojis / a quiet character: almost none / an executive-assistant
  character: zero).
- The mood-branching block becomes the source for `mood_behaviors`.

### 6. Tone & atmosphere rules

```
## Tone & atmosphere
- Default tone: ...
- When the user gets romantic: how does the character receive it
  (shy / distant / direct / observing)?
- When the mood deepens: how does it shift (within SFW limits)?
- The character's core gap: how does the inside-vs-outside contrast
  surface naturally?
```

### 7. Absolute rules

```
## Absolute rules
- Always respond in {{language}}.
- Always answer as {{name}}. Never break character.
- Keep responses short and natural (1–3 sentences). No long monologues.
- {{Character-specific absolute rule, if any}}
```

---

## Sheet → JSON mapping cheat-sheet

Where each sheet section ends up in the JSON files:

| Sheet section | `persona/charNN.json` field |
|---|---|
| 1. One-line introduction | `profile_summary_ko` |
| 2. Basics (appearance / background) | `description` |
| 2. Basics (hobbies / likes / dislikes) | `personality` + `interests` |
| 3. Personality | `personality` |
| 4. Emotional reactions | `system_prompt` (Emotional Reactions section) + `mes_example` |
| 5. Speech (default) | `system_prompt` (Tone Guide) |
| 5. Speech (mood branches) | `mood_behaviors` |
| 6. Tone & atmosphere | `system_prompt` (top tone guide) |
| 7. Absolute rules | `system_prompt` (bottom Absolute Rules) |

The image tags (`images/charNN.json`) and the fixation-tier behavior
table (`behaviors/charNN.json`) don't have direct sheet entries — fill
them after the sheet, following Part 2 / Part 3 of
[`character_card_instruction.md`](character_card_instruction.md).

## Self-review checklist

After writing the sheet, verify:

- [ ] Age 19+ stated explicitly.
- [ ] Appearance section has no exposure / underwear / body-part detail.
- [ ] Personality section has no "when the user does X, character does Y"
      patterns (those belong in Section 4).
- [ ] Section 4 has 6+ emotional reactions.
- [ ] Section 5 specifies an emoji policy.
- [ ] Section 7 lists any character-specific absolute rule (or just the
      shared 3 lines).
- [ ] Total length stays within one page (40–80 lines).
- [ ] The concept still has meaning under the SFW constraints — if not,
      redesign before writing the JSON.
