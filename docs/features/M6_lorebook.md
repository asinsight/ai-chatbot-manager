# M6 — Lorebook (per-character world knowledge) editor + char→world mapping

> **Branch**: `feat/feature_M6_lorebook`
> **Status**: Plan only — awaiting PM sign-off.
> **Estimate**: 1.5–2 days

---

## 1. Goals

### 1a. Bot-side
1. Ship a sample `world_info/char05.json` (Jiwon Han's lorebook — 4–6 entries) so the existing `_load_world_info()` / `_match_world_info()` path in [src/prompt.py](src/prompt.py) actually fires for the only sample character.
2. Introduce `world_info/mapping.json` so the world file a character uses is no longer hardcoded to `<char_id>.json`. Multiple characters can share the same world; one character maps to exactly one world.
3. Update `_load_world_info(char_id)` to consult the mapping first, falling back to the legacy `<char_id>.json` lookup when the mapping has no entry — preserves backward compatibility for any existing operator.

### 1b. Platform-side
1. New `/lorebook` page on the admin (sidebar item between Characters and Image Config).
2. Master-detail UI: list of world files on the left, per-world entries editor on the right.
3. Per-entry form: keyword chips + content textarea + position select (`background` / `active`).
4. Mapping card on the same page: list of all characters with a per-character dropdown picking from available worlds. Save → writes `mapping.json`.
5. CRUD on world files (create / duplicate / delete). Delete blocked when any character is currently mapped to the target world.
6. Auto-backup on every save (M2/M3/M4 pattern).
7. Restart-required toast.

### Done criteria
- `world_info/char05.json` exists with 4+ entries and renders into char05's prompts when keywords match.
- `world_info/mapping.json` exists with at least `char05 → char05`.
- `/lorebook` page lists worlds, lets the operator edit entries, and saves with a backup.
- Mapping card lets the operator switch char05 → some other world and verify via Raw JSON or by inspecting the file on disk.
- Bot restart picks up changes.

### Out-of-scope
- "Test pane" that pastes a user message and previews which entries fire. (Could be M6.5.)
- Per-entry priority / activation order weighting (current loader is a simple substring match; entries are appended in order).
- Multi-world per character (one char → many worlds). Single-world simpler; matches the user's example.
- Schema migration for legacy worlds keyed by char_id. They keep working through the fallback.

---

## 2. ★ PM decisions (answer before implementation)

### #1 — World filename convention
- **A (recommended)**: free-form `<world_id>.json`, regex `^[a-z][a-z0-9_]*$`. UI seeds defaults like `world1`, `jiwon_office`, etc.
- **B**: prefix `world_<id>.json`. Slight visual hint that the file is a world. Also slightly noisier filenames.
- **C**: stick with the legacy `<char_id>.json` convention; operators just rename files when they want to share. No mapping file; characters always look at their own. (Drops the user's ask.)

Recommend A — gives operators free naming, reads cleanly in the UI.

### #2 — `mapping.json` location
- **A (recommended)**: `world_info/mapping.json` — sits next to the world files.
- **B**: `config/lorebook_mapping.json` — sits with other config-y stuff.

Recommend A — co-locating with the world files keeps lorebook-related state in one folder.

### #3 — Mapping fallback when char absent
- **A (recommended)**: fall back to `<char_id>.json` (legacy behavior). Quietly empty when neither exists.
- **B**: refuse / log a warning when a character is missing from the mapping. Forces operators to declare every char.

Recommend A — keeps existing setups working; UI surfaces the implicit mapping with a "(legacy fallback)" badge.

### #4 — Delete-world cascade
- **A (recommended)**: refuse delete when any character is currently mapped to the world (422 `WORLD_IN_USE`). UI lists the offending characters.
- **B**: delete + auto-clear mapping entries pointing at the deleted world.

Recommend A — explicit > implicit; the operator should consciously remap before deleting.

### #5 — UI placement
- **A (recommended)**: dedicated sidebar item "Lorebook" + dedicated `/lorebook` page.
- **B**: tab inside `/characters` / `/config`. More compact but worsens navigation when an operator is editing a shared world that touches multiple characters.

Recommend A — sidebar item, matches the user's brief (a separate Lorebook tab).

### #6 — Sample char05 lorebook content
- Will seed 4–6 short entries plausible for Jiwon Han (Korean R&D office worker — see her persona). Examples: her boss, her commute, her favorite cafe, her current project. Keywords in English (matches the rest of the SFW fork's i18n).
- Confirm: ship as part of the same commit as the bot-side mapping change.

---

## 3. Data shapes

### `world_info/<world_id>.json`
```json
{
  "_doc": "Lorebook for <Jiwon Han / shared world / etc.>. Used by src/prompt.py's _match_world_info() — substring match against the user message + last 4 turns.",
  "entries": [
    {
      "keywords": ["Cole", "team lead"],
      "content": "Cole is Jiwon's strict but fair team lead. He pushed her for a promotion last quarter and tracks her project deadlines closely.",
      "position": "background"
    },
    {
      "keywords": ["promotion", "raise"],
      "content": "Jiwon's promotion review is scheduled for next month; she's anxious about presenting her quarterly results to the executive panel.",
      "position": "active"
    }
  ]
}
```

`position` semantics (current loader):
- `background` → injected into the prompt as long-term backdrop facts.
- everything else (default `active`) → injected as situational/active context.

`_doc` and any other underscore-prefixed top-level keys are passed through but ignored by the loader. The platform UI hides them.

### `world_info/mapping.json`
```json
{
  "_doc": "Maps each character to a world_info file. Lookup: world_info/<value>.json. Missing characters fall back to world_info/<char_id>.json (legacy).",
  "char05": "char05"
}
```

Values must reference an existing world file (validated on save).

---

## 4. Bot-side change — `src/prompt.py`

```python
def _load_mapping() -> dict:
    """Cached read of world_info/mapping.json (returns {} if absent)."""
    ...

def _load_world_info(char_id: str) -> dict:
    if char_id in _world_info_cache:
        return _world_info_cache[char_id]
    mapping = _load_mapping()
    world_id = mapping.get(char_id, char_id)
    path = .../world_info/<world_id>.json
    ...  # same as before
```

Cache invalidation strategy: process-lifetime cache, same as today. Operators restart the bot after edits — matches the existing toast.

---

## 5. Directory structure (M6 additions)

```
world_info/
├── char05.json                    # ★ new — Jiwon Han sample lorebook
└── mapping.json                   # ★ new — char→world map

src/
└── prompt.py                      # patched — _load_mapping() + _load_world_info() lookup

platform/
├── app/
│   ├── lorebook/
│   │   ├── page.tsx               # server entry
│   │   ├── lorebook-page.tsx      # client outer layout
│   │   ├── world-list.tsx         # left pane — list + create/duplicate/delete
│   │   ├── world-editor.tsx       # right pane — entries master-detail
│   │   ├── entry-form.tsx         # keywords chips + content + position select
│   │   └── mapping-card.tsx       # bottom card — char↔world dropdowns
│   └── api/
│       └── lorebook/
│           ├── worlds/route.ts                  # GET list + POST create
│           ├── worlds/[name]/route.ts           # GET / PUT / DELETE
│           ├── worlds/[name]/duplicate/route.ts # POST
│           └── mapping/route.ts                 # GET / PUT
└── lib/
    ├── lorebook.ts                # server — read/write/backup + zod
    └── lorebook-meta.ts           # client-safe types
```

---

## 6. API contracts

| Route | Method | Body / params | Response | Errors |
|---|---|---|---|---|
| `/api/lorebook/worlds` | GET | — | `{ worlds: [{ name, entry_count, mapped_chars: string[], mtime_ms }] }` | 500 |
| `/api/lorebook/worlds` | POST | `{ name }` | `{ ok, name }` | 422 INVALID_NAME / 409 ALREADY_EXISTS |
| `/api/lorebook/worlds/[name]` | GET | — | `{ name, content, mapped_chars: string[] }` | 404 UNKNOWN_WORLD |
| `/api/lorebook/worlds/[name]` | PUT | `{ content }` | `{ ok, backup_path }` | 422 INVALID_SHAPE |
| `/api/lorebook/worlds/[name]` | DELETE | — | `{ ok, backup_path }` | 422 WORLD_IN_USE / 404 |
| `/api/lorebook/worlds/[name]/duplicate` | POST | — | `{ ok, name: <new_name> }` | 404 |
| `/api/lorebook/mapping` | GET | — | `{ mapping: {char_id: world_id}, characters: string[], worlds: string[] }` | 500 |
| `/api/lorebook/mapping` | PUT | `{ mapping: {char_id: world_id} }` | `{ ok, backup_path }` | 422 UNKNOWN_WORLD / UNKNOWN_CHARACTER |

---

## 7. UI sketch

```
┌─ Lorebook
│ Manage per-character world knowledge (lorebook entries). Each
│ entry's keywords are matched (substring, case-insensitive) against
│ the latest user message + last 4 chat turns; matches are injected
│ into the system prompt. Bot restart required after save.
├─ Stage assignments (matching the /workflows pattern):
│  ┌─────────────────────────────────────────────────────┐
│  │ Character mapping                                   │
│  ├─────────────────────────────────────────────────────┤
│  │ char05  [ char05  ▾ ]   ← world dropdown            │
│  │ char06  [ —        ▾ ]   (legacy fallback notice)   │
│  │ ...                                                 │
│  │                                       [Save]        │
│  └─────────────────────────────────────────────────────┘
└─
   ┌─ Worlds ─────────┬─ Selected: char05 ────────────────┐
   │ + Add world      │ World file: world_info/char05.json│
   │                  │                                   │
   │ • char05 (4)     │ Entries:                          │
   │   shared (3)     │ ┌─────────────────────────────┐   │
   │   ...            │ │ keywords: [Cole][team lead] │   │
   │                  │ │ content: textarea           │   │
   │                  │ │ position: [background ▾]    │   │
   │                  │ │              [Delete entry] │   │
   │                  │ └─────────────────────────────┘   │
   │                  │ [+ Add entry]   [Save world]      │
   └──────────────────┴───────────────────────────────────┘
```

---

## 8. Test scenarios (8)

1. **List worlds** — fresh repo: `/lorebook` shows `char05` with 4 entries + mapping card with `char05 → char05`.
2. **Edit + save entry** — open char05 world, change a keyword → Save → file on disk reflects the change; backup `.bak` written.
3. **Add new world** — "+ Add world" → name `shared_world` → seed entry stub → Save. New file appears in `world_info/`.
4. **Mapping change** — set `char05 → shared_world` → Save → `mapping.json` updated.
5. **Bot integration** — after #4 + bot restart: `python -c "from src.prompt import _load_world_info; print(_load_world_info('char05'))"` returns the `shared_world` content.
6. **Delete with mapping** — try deleting `char05` while it's mapped → 422 `WORLD_IN_USE`; UI lists `char05`.
7. **Delete after remap** — set mapping back to legacy fallback → delete `shared_world` → 200 + backup written.
8. **Legacy fallback** — remove `char05` from mapping entirely → loader still finds `world_info/char05.json` (legacy convention preserved).

---

## 9. Open questions

1. **#1 — world filename convention**: A / B / C? (recommend A)
2. **#2 — mapping.json location**: A / B? (recommend A — `world_info/mapping.json`)
3. **#3 — fallback when char missing from mapping**: A / B? (recommend A — `<char_id>.json` legacy fallback)
4. **#4 — delete-world cascade**: A / B? (recommend A — refuse with `WORLD_IN_USE`)
5. **#5 — UI placement**: A / B? (recommend A — dedicated `/lorebook` page)
6. **Test pane** — leave for M6.5 follow-up?
7. Anything else before sign-off?
