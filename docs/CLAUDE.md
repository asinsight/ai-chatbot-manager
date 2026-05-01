# `docs/` — Project documentation

Operator-facing guides + per-milestone feature plans.

## Files

- **`character_card_instruction.md`** — How to author a character card
  bundle (`persona/` + `behaviors/` + `images/`). Field-by-field
  reference; tracks `character_card_schema.json` at the repo root.
- **`character_sheets.md`** — Template / checklist for sketching a new
  character before writing the JSON.
- **`features/`** — Per-milestone feature plan MDs (one per `feat/feature_*`
  branch). Written before implementation as a PM-decision document and
  kept on disk afterwards as historical context. Current: `M0_admin_skeleton.md`,
  `M1_env_connections.md`, `M2_prompt_editor.md`, `M3_character_crud.md`,
  `M4_image_config.md`, `M5_workflows_logs.md`, `M6_lorebook.md`.

## Invariants

- `character_card_instruction.md` field list must stay in sync with
  `character_card_schema.json`. Update both in the same commit when the
  schema changes.
- Feature plans (`features/M*.md`) describe the *plan* — they are not
  rewritten as implementation drifts. The current code is described in
  the per-folder `CLAUDE.md` files.
