# `tools/` — Developer tooling

Place for developer-side helper scripts (prompt comparison, scene
description generation, ad-hoc validation runners, etc). **Currently
empty in this distribution** — only a `.gitkeep` to preserve the
folder.

## Conventions

- Tools must not affect the bot runtime — keep them in their own venv /
  entry-point.
- Tools that hit a paid LLM API should default to dry-run / a small
  sampled batch and require an explicit flag to spend tokens at scale.
