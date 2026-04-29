# `platform/` — Next.js admin webapp

로컬 admin 콘솔. ella-chat-publish 의 운영 구성(.env, 캐릭터 카드, prompt JSON, ComfyUI 워크플로우)을 편집·관리하고 봇 라이프사이클(start/stop/restart)을 제어한다. 외부 노출 없이 `127.0.0.1:9000` 에 바인딩.

자세한 plan 은 [../plan.md](../plan.md), 마일스톤별 feature plan 은 [../docs/features/](../docs/features/) 에서 관리.

## 시작법

```
cd platform
npm install      # 첫 실행 시
npm run dev      # http://127.0.0.1:9000
```

봇 프로세스를 spawn 할 Python 인터프리터는 루트 `.env` 의 `PYTHON_BIN` 변수로 지정 (절대 경로 권장). 미설정 시 PATH 의 `python3` 사용.

## 현재 마일스톤

**M2 완료 (develop 머지 대기)** — `/prompts` 편집기 + Monaco + diff modal.

| 페이지 | 상태 |
|---|---|
| `/dashboard` | ✅ Bot status card + Connections health card + log tail (5s polling) |
| `/connections` | ✅ 4 endpoint cards (ComfyUI / OpenWebUI / Grok / Prompt Guard) — URL+token 편집 + Ping + last_ping SQLite 기록 + 전체 Ping |
| `/env` | ✅ 8 카테고리 tabs + 카테고리 description + 시크릿 마스킹 + 자동 백업 + default placeholder |
| `/prompts` | ✅ Outer tabs (Grok prompting / System prompt) × inner tabs (5+3 keys), Monaco 65vh + react-diff-viewer modal + per-key save + ${var} placeholder lint + 인라인 metadata |
| `/characters` | ⏳ M3 placeholder |
| `/config` | ⏳ M4 placeholder |
| `/workflows` | ⏳ M5 placeholder |
| `/logs` | ⏳ M5 placeholder |

> M1 단계에서 코드/UI 전체가 영어로 통일됐다 (PM 결정 D). Markdown 문서 (이 파일 포함) 만 한국어 유지. `lib/env-categories.ts` 의 카테고리 라벨, toast 메시지, 컴포넌트 텍스트 모두 영어.

## 디렉터리 구조

```
platform/
├── app/                                # App Router
│   ├── layout.tsx                      # Sidebar + Header + Main + Toaster
│   ├── page.tsx                        # → /dashboard 리다이렉트
│   ├── dashboard/                      # M0 (status + log tail) + M1 (health card)
│   ├── env/{page,env-form}.tsx         # M1 — 카테고리 tabs + 시크릿 마스킹 + description
│   ├── connections/{page,connections-page,connection-card}.tsx  # M1 — 4 endpoint
│   ├── prompts/{page,prompts-page,prompt-editor,lint,metadata}.tsx  # M2 — Monaco + diff modal
│   ├── (placeholders)/                 # characters, config, workflows, logs
│   └── api/
│       ├── bot/                        # M0 — 5 routes (status/start/stop/restart/logs)
│       ├── env/                        # M1 — GET / PUT
│       ├── connections/                # M1 — GET, [id] PUT, [id]/ping POST, ping-all POST
│       └── prompts/{grok,system}/      # M2 — GET / PUT
├── components/
│   ├── ui/                             # shadcn primitives (Button, Card, Badge, Input, Label, Tabs, Sonner, Dialog)
│   ├── sidebar.tsx                     # 8 nav items
│   ├── header.tsx
│   ├── monaco-client.tsx               # M2 — dynamic import Monaco (SSR off)
│   ├── bot-status-card.tsx             # M0 — 5s polling + Start/Stop/Restart
│   ├── connections-health-card.tsx     # M1 — 30s polling, 4 dot summary
│   └── log-tail.tsx                    # M0 — logs/bot.log 마지막 200 줄
├── lib/
│   ├── paths.ts                        # REPO_ROOT / RUN_DIR / LOGS_DIR / ENV_FILE / ENV_EXAMPLE_FILE / SQLITE_FILE
│   ├── bot-process.ts                  # M0 — spawn / kill / PID file
│   ├── env-parser.ts                   # M1 — 라인 보존 .env 파서 + applyUpdates + parseExampleComments
│   ├── env-categories.ts               # M1 — 8 카테고리 mapping (LLM/Grok/ComfyUI/Video/Prompt Guard/Operations/Tokens/Platform)
│   ├── secrets.ts                      # M1 — *_API_KEY / *_BOT_TOKEN 패턴 + maskValue
│   ├── backup.ts                       # M1 — KST timestamp .env 백업 (무제한 회전)
│   ├── db.ts                           # M1 — better-sqlite3 + connection_check 테이블
│   ├── connections.ts                  # M1 — 4 endpoint 정의
│   ├── env-read.ts                     # M1 — .env 값 읽기 helper
│   ├── ping.ts                         # M1 — 4 endpoint ping (10s timeout, AbortController)
│   ├── prompts.ts                      # M2 — read/write/validate/lint config/grok_prompts.json + system_prompt.json
│   └── utils.ts                        # cn() (shadcn util)
└── data/                               # gitignored — platform.sqlite + backups/.env.*.bak
```

## `lib/bot-process.ts` — 봇 라이프사이클 SOT

| Export | 동작 |
|---|---|
| `getStatus()` | `running` / `stopped` / `unknown` 반환. PID 파일 + `process.kill(pid, 0)` 으로 alive 확인. stale PID 자동 정리. |
| `start()` | `child_process.spawn(PYTHON_BIN, ['-m', 'src.bot'], { detached: true })` + `unref()` → Next.js 종료해도 봇 생존. 250ms 후 alive 확인 (ImportError 즉시 감지). 이미 실행 중이면 `ALREADY_RUNNING` throw. |
| `stop()` | `SIGTERM` → 100ms × 50회 = 5초 grace → `SIGKILL`. PID 파일 삭제. 실행 중 아니면 `NOT_RUNNING` throw. |
| `restart()` | `stop()` (best-effort) + `start()`. |

**동시성**: 모든 함수는 module-level mutex (Promise chain) 로 직렬화. 더블-클릭으로 race 안 일어남.

**PID 추적**: `run/bot.pid` (PID 숫자) + `run/bot.meta.json` (`{startedAt, command}`). `run/` 디렉터리는 자동 생성, 루트 `.gitignore` 의 `/run/` 으로 제외.

**로그 파이프**: `logs/bot.log` 를 `fs.openSync(..., 'a')` 로 append-mode 로 열어 자식 프로세스의 stdout+stderr 둘 다 같은 fd 로 redirect. Next.js 가 종료돼도 fd 가 자식에게 inherit 되어 계속 append.

## API Routes

전부 Node runtime (`export const runtime = 'nodejs'`), `dynamic = 'force-dynamic'` (캐시 X).

| Route | Method | 응답 | 에러 |
|---|---|---|---|
| `/api/bot/status` | GET | `BotStatus` | 500 STATUS_FAILED |
| `/api/bot/start` | POST | `{ pid }` | 409 ALREADY_RUNNING / 500 START_FAILED |
| `/api/bot/stop` | POST | `{ ok: true }` | 409 NOT_RUNNING / 500 STOP_FAILED |
| `/api/bot/restart` | POST | `{ pid }` | 500 RESTART_FAILED |
| `/api/bot/logs?tail=N` | GET | `{ lines: string[], note? }` | 500 LOGS_FAILED |
| `/api/env` | GET | 8 카테고리 + 변수 list | 500 ENV_READ_FAILED |
| `/api/env` | PUT `{updates}` | `{ok, restart_required, backup_path}` | 422 READ_ONLY_KEY / UNKNOWN_KEY / INVALID_VALUE |
| `/api/connections` | GET | 4 endpoint + last_ping | 500 |
| `/api/connections/[id]` | PUT `{url, token}` | `{ok, backup_path}` | 422 TOKEN_REQUIRED / TOKEN_NOT_SUPPORTED |
| `/api/connections/[id]/ping` | POST | `{ok, status_code, duration_ms, message}` | — (failure body 안에 ok=false) |
| `/api/connections/ping-all` | POST | `{results: {id: PingResult}}` | — |
| `/api/prompts/grok` | GET | `{file, keys: [{name, value, size}]}` | 500 PROMPT_READ_FAILED |
| `/api/prompts/grok` | PUT `{updates}` | `{ok, backup_path, warnings}` | 422 INVALID_PAYLOAD / MISSING_REQUIRED_KEY |
| `/api/prompts/system` | GET / PUT | (grok 동일) | (grok 동일) |

`logs` route 는 1MB 읽기 창 + 마지막 N줄 (1 ≤ N ≤ 1000, 기본 200) 추출.

## SQLite (M1)

`platform/data/platform.sqlite` (gitignored). WAL mode. `lib/db.ts` 가 lazy-init + idempotent migration.

테이블:
- `connection_check` — `(id, endpoint_id, ts, ok, status_code, duration_ms, message)` + index `(endpoint_id, ts DESC)`. recordPing / getLastPing / getLastPingsAll 헬퍼.

향후 마일스톤 (M2-M5) 에서 audit log / character snapshot 등 테이블이 추가될 수 있다.

## 의존성

- **next 14.2.35** (Tailwind 3.4 + App Router). 14.2.18 의 보안 패치 버전 사용.
- **shadcn/ui** primitives 직접 작성 (CLI 미사용 — components.json 만 두고 필요한 컴포넌트만 수동 추가).
- **lucide-react** 아이콘.
- **class-variance-authority + tailwind-merge + clsx** (shadcn 표준).
- **better-sqlite3** (M1) — `platform.sqlite` 단일 파일 SQLite. native binding, prebuilt arm64 정상 다운로드.
- **@radix-ui/react-tabs / react-label** (M1) — env tabs / form labels.
- **sonner** (M1) — toast UI.
- **@monaco-editor/react** (M2) — VS Code-equivalent editor (dynamic import, SSR off).
- **@radix-ui/react-dialog** (M2) — shadcn Dialog primitive (diff modal).
- **react-diff-viewer-continued** (M2) — split-view diff (active React 18 fork).

## 편집 가이드

1. **타입체크 필수**: `npm run typecheck` (또는 `npx tsc --noEmit`). 매 commit 전 확인.
2. **Server vs Client**: API route 는 Node runtime, UI 컴포넌트는 `"use client"` 선언 (`bot-status-card.tsx`, `log-tail.tsx` 등).
3. **`@/*` import alias** — `tsconfig.json` 에 정의됨. 항상 절대 import (`@/lib/...`, `@/components/...`).
4. **봇 프로세스 외부 영향**: `lib/bot-process.ts` 변경 시 항상 수동 테스트 — start/stop/restart/stale-pid 시나리오. `npm run build` 만으로는 race 검증 안 됨.
5. **새 마일스톤 시작 시**: 새 feature 브랜치 + `docs/features/M<N>_<name>.md` plan + 사인오프 → 구현. 머지 시 `platform/CLAUDE.md` 의 "현재 마일스톤" 표 갱신.

## M3+ 시작 시 주의

`/characters` (M3), `/config` (M4), `/workflows` + `/logs` (M5) 페이지는 placeholder 만 있음. 새 마일스톤에서는 placeholder 를 실제 UI 로 교체하면 된다 — routing 변경 불필요.
