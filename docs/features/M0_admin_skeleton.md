# M0 — Admin webapp skeleton + bot lifecycle

> **Branch**: `feat/feature_M0_admin_skeleton`
> **Status**: ✅ Shipped (`7804ea1`)
> **Estimate**: 1.5–2 days
> **Current state**: see [`platform/CLAUDE.md`](../../platform/CLAUDE.md) — this document is preserved as historical context.

---

## Goal

Bring up the admin webapp shell + bot start/stop loop. UI editors and
CRUD pages came in M1–M6; this milestone was just enough to launch a
browser, click `Start`, and see a running PID.

### Done criteria

1. `platform/` initialized as Next.js 14 (App Router) + TypeScript +
   Tailwind + shadcn/ui. `npm run dev` opens http://127.0.0.1:9000.
2. Left sidebar lists every planned page (`Dashboard / Connections /
   Env / Prompts / Characters / Image Config / Workflows / Logs`). Only
   Dashboard is wired up — everything else is a placeholder.
3. Dashboard shows:
   - Bot status card (`running` / `stopped` / `unknown`, PID, uptime, start time).
   - `Start` / `Stop` / `Restart` buttons. Clicking refreshes status within 5s.
   - Last 200 log lines (5s polling).
4. Bot lifecycle: Node `child_process.spawn` runs `python -m src.bot`,
   PID tracked in `run/bot.pid`, `SIGTERM` → 5s grace → `SIGKILL`.
5. Every API route binds to `127.0.0.1` (no external exposure).

### Out of scope (deferred to later milestones)

- `.env` / character / prompt / workflow editors (M1–M5).
- Connections ping (M1).
- WebSocket log streaming — polling is fine.
- Backup rotation, automated git commit, auth, HTTPS.
- Bot auto-restart / health check / rollback.

---

## Outcome

Implemented as planned. 9 manual smoke-test scenarios passed:

1. Fresh repo → `npm install` + `npm run dev` → browser shows Dashboard.
2. `Start` button → PID returned + status flips to running within 5s.
3. `Stop` button → status flips to stopped within 5s.
4. `Restart` button → new PID, uptime resets.
5. Stale PID file (kill -9 the process out-of-band) → status detects and self-cleans.
6. Double-click `Start` → second click refused with `ALREADY_RUNNING`.
7. Bot import error → spawn returns immediately + status surfaces the failure.
8. Log tail shows recent lines + scrolls.
9. All 7 placeholder pages return 200 with "(M1+ placeholder)" copy.

The current shape of the bot-lifecycle SOT lives in
[`platform/lib/bot-process.ts`](../../platform/lib/bot-process.ts);
behavior is documented in [`platform/CLAUDE.md`](../../platform/CLAUDE.md).
