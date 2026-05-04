# `scripts/` — Operational scripts

Place for one-shot operational scripts (bulk character import, DB
migration helpers, data seeders, etc). **Currently empty in this
distribution** — only a `.gitkeep` to preserve the folder.

## Conventions

- Use absolute paths and write idempotent scripts (re-running has no
  side effects).
- DB-touching scripts should snapshot the SQLite file first or expose
  a `--dry-run` mode.
