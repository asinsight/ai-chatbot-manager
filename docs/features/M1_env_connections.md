# M1 — `.env` editor + Connections page

> **Branch**: `feat/feature_M1_env_connections`
> **Status**: ✅ Shipped (`09334db`); polish in `b1fa27f`
> **Estimate**: 2–2.5 days
> **Current state**: see [`platform/CLAUDE.md`](../../platform/CLAUDE.md) — this document is preserved as historical context.

---

## Goal

Make the bot's runtime configuration editable from the browser:

- `/env` page — every variable in the project-root `.env`, grouped into
  8 categories. Saves write to disk atomically + drop a `.bak` next to
  the live file.
- `/connections` page — the four external endpoints (ComfyUI, OpenWebUI,
  Grok, Prompt Guard) with URL+token edit, a Ping button, and a
  per-endpoint history log.
- Dashboard health card — 4-dot summary (🟢 / 🔴) sourced from the same
  ping route.

### Done criteria

1. `/env` lists every key in root `.env`, grouped by category, with
   per-category description + per-key inline help sourced from the
   matching `.env.example` comment.
2. Secret detection — `*_API_KEY` / `*_BOT_TOKEN` / `*_API_TOKEN`
   patterns get masked (`••••••<last4>`) with a 👁 reveal toggle.
3. Save → `.env` rewritten in place + `platform/data/backups/.env.<KST>.bak` written.
4. Toast after every save: `"Saved · restart bot to load"` with a
   Dashboard deep-link to the Restart button.
5. `/connections` shows 4 endpoint cards. Each card: URL input + token
   input (where applicable) + `Ping` button. Ping result rendered
   inline (status code, ms, message).
6. SQLite (`platform/data/platform.sqlite`, WAL) records every ping into
   a `connection_check` table; the most-recent ping per endpoint is
   surfaced on the card and the Dashboard health summary.
7. Bot is bound to `127.0.0.1` only; no auth in v1.

### Out of scope (deferred)

- Prompt editing (M2).
- Character CRUD (M3).
- Image config / workflows (M4–M5).
- Auto-restart on save — only the toast prompt.
- Backup rotation — v1 keeps everything; pruning policy is a follow-up.
- Auth / external exposure — v1 binds to localhost only.

---

## PM decisions (resolved)

### #1 — Grok base URL env var

Original state: `src/grok.py` had `base_url="https://api.x.ai/v1"`
hardcoded in five callsites. **Decision: B** — add `GROK_BASE_URL` env
(default `https://api.x.ai/v1`), route all callsites through it. The
`/connections` Grok card is fully editable (URL + token).

Implemented in M1 + finalized in the post-M5 cleanup
(commit `661092a` collapsed the 5 callsites into a single module-level
constant).

### #2 — Prompt Guard card visibility

Current state: `PROMPT_GUARD_URL` is read in `src/input_filter.py` as
`os.getenv("PROMPT_GUARD_URL", "")` — empty disables the remote call,
the regex filter still runs. **Decision: A** — the card is shown on
`/connections`. Setup instructions for the standalone server live in
[`deploy/prompt-guard/README.md`](../../deploy/prompt-guard/README.md).

### #3 — `platform.sqlite` location

**Decision: `platform/data/platform.sqlite` + `platform/data/backups/`**.
`platform/.gitignore` excludes the entire `data/` directory.

### #4 — `better-sqlite3` dependency

**Decision: add it.** Synchronous API is the right fit for a server
that only ever runs locally; the prebuilt arm64 binary downloads
cleanly so install time is fine.

---

## Outcome

Implemented as planned. 12 manual smoke-test scenarios passed. Two
follow-up items shipped in `b1fa27f` (M1 polish):

1. Renamed every Grok env var to the `GROK_PROMPTING_*` namespace so
   the model-selector keys can't be confused with the Grok image API
   that the bot does not use.
2. Exposed `VIDEO_COMPOSER_MODEL` (was hidden because the platform
   didn't recognize the variable name).
3. Fixed the `/env` UI's secret-mask display (the masked value would
   briefly flash the cleartext on save).
4. Added default-value placeholders in `.env.example`.
5. Corrected the OpenWebUI label (Gemma → llama-cpp-python).

The current shape of `/env` + `/connections` lives in
[`platform/CLAUDE.md`](../../platform/CLAUDE.md).
