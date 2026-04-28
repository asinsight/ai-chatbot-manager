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

**M0 — 골격 + 봇 dashboard + 시작/종료** (`feat/feature_M0_admin_skeleton` 브랜치).

| 페이지 | 상태 |
|---|---|
| `/dashboard` | ✅ 봇 status 카드 + 로그 tail (5초 polling) |
| `/connections` | ⏳ M1 placeholder |
| `/env` | ⏳ M1 placeholder |
| `/prompts` | ⏳ M2 placeholder |
| `/characters` | ⏳ M3 placeholder |
| `/config` | ⏳ M4 placeholder |
| `/workflows` | ⏳ M5 placeholder |
| `/logs` | ⏳ M5 placeholder |

## 디렉터리 구조

```
platform/
├── app/                   # App Router
│   ├── layout.tsx         # Sidebar + Header + Main
│   ├── page.tsx           # → /dashboard 리다이렉트
│   ├── dashboard/         # M0 핵심 페이지
│   ├── (placeholders)/    # connections, env, prompts, characters, config, workflows, logs
│   └── api/bot/           # 5 routes — status, start, stop, restart, logs
├── components/
│   ├── ui/                # shadcn primitives (Button, Card, Badge)
│   ├── sidebar.tsx
│   ├── header.tsx
│   ├── bot-status-card.tsx   # 5초 polling + Start/Stop/Restart
│   └── log-tail.tsx          # logs/bot.log 마지막 200줄 5초 polling
└── lib/
    ├── paths.ts           # REPO_ROOT / RUN_DIR / LOGS_DIR / ENV_FILE 등
    ├── bot-process.ts     # spawn / kill / PID file 관리
    └── utils.ts           # cn() (shadcn util)
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

`logs` route 는 1MB 읽기 창 + 마지막 N줄 (1 ≤ N ≤ 1000, 기본 200) 추출.

## 의존성

- **next 14.2.35** (Tailwind 3.4 + App Router). 14.2.18 의 보안 패치 버전 사용.
- **shadcn/ui** primitives 직접 작성 (CLI 미사용 — components.json 만 두고 필요한 컴포넌트만 수동 추가).
- **lucide-react** 아이콘.
- **class-variance-authority + tailwind-merge + clsx** (shadcn 표준).

## 편집 가이드

1. **타입체크 필수**: `npm run typecheck` (또는 `npx tsc --noEmit`). 매 commit 전 확인.
2. **Server vs Client**: API route 는 Node runtime, UI 컴포넌트는 `"use client"` 선언 (`bot-status-card.tsx`, `log-tail.tsx` 등).
3. **`@/*` import alias** — `tsconfig.json` 에 정의됨. 항상 절대 import (`@/lib/...`, `@/components/...`).
4. **봇 프로세스 외부 영향**: `lib/bot-process.ts` 변경 시 항상 수동 테스트 — start/stop/restart/stale-pid 시나리오. `npm run build` 만으로는 race 검증 안 됨.
5. **새 마일스톤 시작 시**: 새 feature 브랜치 + `docs/features/M<N>_<name>.md` plan + 사인오프 → 구현. 머지 시 `platform/CLAUDE.md` 의 "현재 마일스톤" 표 갱신.

## M0 외 부분 진입 시 주의

`/dashboard` 외 페이지는 모두 placeholder. 함수형 컴포넌트 한 줄짜리 텍스트만 있음. M1+ 에서 실제 UI 채울 때 이 placeholder 들을 직접 교체한다 (별도 routing 변경 불필요).
