# M0 — Admin 웹앱 골격 + 봇 라이프사이클

> **브랜치**: `feat/feature_M0_admin_skeleton`
> **상태**: Plan only — PM 사인오프 후 구현 시작.
> **상위 plan**: [plan.md §8 M0](../../plan.md)
> **예상 소요**: 1.5–2일

---

## 1. 목표 (M0 Scope)

이번 마일스톤은 **"띄우고 끄는 것"** 까지만 한다. UI 편집기 / 캐릭터 CRUD / Connections / 워크플로우는 모두 후속 M1–M5.

### Done 조건
1. `platform/` 에 Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui 프로젝트가 초기화되고 `npm run dev` 로 http://127.0.0.1:9000 접근.
2. 좌측 Sidebar 에 향후 페이지 placeholder (`Dashboard`, `Connections`, `Env`, `Prompts`, `Characters`, `Image Config`, `Workflows`, `Logs`) — Dashboard 만 활성, 나머지는 빈 페이지.
3. **Dashboard** 페이지에:
   - 봇 status 카드 (running / stopped / unknown, PID, uptime, started_at).
   - **Start / Stop / Restart** 버튼 — 클릭 → 5초 안에 status 갱신.
   - 최근 로그 tail (최근 200줄, 5초 polling).
4. 봇 프로세스 라이프사이클: Node `child_process.spawn` 으로 `python -m src.bot` 실행, PID 파일 추적, SIGTERM → 5초 grace → SIGKILL.
5. 모든 API route 는 `127.0.0.1` 바인딩 (외부 접근 차단 — plan §9.4).

### Out-of-scope (이번 M0 에서 안 함)
- `.env` / 캐릭터 / 프롬프트 / 워크플로우 편집 UI (M1–M5).
- Connections ping (M1).
- WebSocket 로그 stream — polling 으로 대체 (M5 에서 업그레이드).
- 백업 회전, git 자동 commit, 인증, HTTPS.
- 봇 자동 재시작 / health check / 자동 롤백.

---

## 2. 디렉터리 구조 (신설)

```
platform/                              # Next.js 14 App Router
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.mjs                    # hostname 127.0.0.1 고정
├── components.json                    # shadcn/ui
├── postcss.config.mjs
├── .gitignore                         # node_modules, .next, *.log
├── README.md                          # M0 단일 페이지 안내 (간단)
├── app/
│   ├── layout.tsx                     # Sidebar + Header + Main
│   ├── page.tsx                       # → /dashboard 로 리다이렉트
│   ├── globals.css
│   ├── dashboard/
│   │   └── page.tsx                   # M0 핵심
│   ├── connections/page.tsx           # M1 자리 — 빈 placeholder
│   ├── env/page.tsx                   # M1 자리
│   ├── prompts/page.tsx               # M2 자리
│   ├── characters/page.tsx            # M3 자리
│   ├── config/page.tsx                # M4 자리
│   ├── workflows/page.tsx             # M5 자리
│   ├── logs/page.tsx                  # M5 자리
│   └── api/
│       └── bot/
│           ├── status/route.ts        # GET
│           ├── start/route.ts         # POST
│           ├── stop/route.ts          # POST
│           ├── restart/route.ts       # POST
│           └── logs/route.ts          # GET ?tail=N
├── components/
│   ├── ui/                            # shadcn 컴포넌트 (button, card, badge, sidebar 등)
│   ├── sidebar.tsx
│   ├── header.tsx
│   ├── bot-status-card.tsx
│   └── log-tail.tsx
└── lib/
    ├── bot-process.ts                 # spawn / kill / status
    ├── paths.ts                       # repo root, logs/, run/, .env 경로 상수
    └── utils.ts                       # cn() 등 shadcn util
```

추가:
- `run/` — repo 루트에 신설. `bot.pid` 와 `bot.meta.json` (started_at, command) 저장. `.gitignore` 에 추가.
- `logs/bot.log` — 기존 위치 그대로. 봇 stdout/stderr 가 append 됨.

---

## 3. `lib/bot-process.ts` 설계

**책임**: 봇 프로세스의 단일 시점(SOT). PID 파일과 실제 프로세스 존재 여부를 동기화.

### API
```ts
type BotStatus =
  | { state: 'running'; pid: number; startedAt: string; uptimeSec: number }
  | { state: 'stopped' }
  | { state: 'unknown'; reason: string };

export async function getStatus(): Promise<BotStatus>;
export async function start(): Promise<{ pid: number }>;     // 이미 실행 중이면 throw
export async function stop(): Promise<void>;                  // SIGTERM → 5s grace → SIGKILL
export async function restart(): Promise<{ pid: number }>;   // stop() then start()
```

### 핵심 동작
- **start**:
  1. `getStatus()` → `running` 이면 `Error('bot is already running')`.
  2. `child_process.spawn('python', ['-m', 'src.bot'], { cwd: repoRoot, detached: true, stdio: ['ignore', logFd, logFd] })`.
  3. `unref()` 로 부모(Next.js) 종료해도 봇은 계속 실행.
  4. `run/bot.pid` 에 `child.pid` 기록, `run/bot.meta.json` 에 `{ startedAt, command }` 기록.
  5. 200ms 후 PID 가 살아있는지 확인 (`process.kill(pid, 0)`) — 죽었으면 PID 파일 삭제 후 throw.
- **stop**:
  1. PID 읽음 → `process.kill(pid, 0)` 으로 alive 확인.
  2. `process.kill(pid, 'SIGTERM')` → 100ms 간격으로 5초간 polling.
  3. 5초 내 종료 안 되면 `SIGKILL`.
  4. `run/bot.pid` 와 `run/bot.meta.json` 삭제.
- **getStatus**:
  - `run/bot.pid` 없음 → `stopped`.
  - 있음 + `process.kill(pid, 0)` 성공 → `running` (uptime = now − startedAt).
  - 있음 + `process.kill(pid, 0)` 실패 (ESRCH) → stale PID 파일 삭제 후 `stopped`.
  - 권한 에러 (EPERM) → `unknown`.
- **restart**: 단순히 `await stop(); return await start();`.

### 동시성
- 모든 함수는 **module-level `Mutex`** (간단한 Promise chain) 로 직렬화. start/stop/restart 가 동시에 호출돼도 race 없게.

### 로그 파이프
- `logs/bot.log` 를 `fs.openSync(..., 'a')` 로 열고 stdout/stderr 둘 다 같은 fd 로 redirect. Next.js 가 종료돼도 fd 가 자식에게 inherit 되어 계속 append.

### Python 인터프리터
- 일단 **시스템 `python`** 사용 (PATH 의존). venv 활성화는 M0 가정에서 사용자가 `npm run dev` 전에 venv 활성화하거나 `.env` 에 `PYTHON_BIN` 추가한 후 사용. → **★ 결정 필요 #1** 참조.

---

## 4. API Routes

모두 Node runtime (`export const runtime = 'nodejs'`), `127.0.0.1` 바인딩, 인증 없음.

| Route | Method | 응답 |
|---|---|---|
| `/api/bot/status` | GET | `BotStatus` JSON |
| `/api/bot/start` | POST | `{ pid }` 또는 409 (이미 실행 중) |
| `/api/bot/stop` | POST | `{ ok: true }` 또는 409 (실행 중 아님) |
| `/api/bot/restart` | POST | `{ pid }` |
| `/api/bot/logs?tail=N` | GET | `{ lines: string[] }` (N ≤ 1000, 기본 200) |

에러는 모두 `{ error: string, code: string }` + 적절한 HTTP status.

---

## 5. UI (Dashboard)

shadcn 컴포넌트 만 사용. 디자인 미니멀.

```
┌────────────────────────────────────────────┐
│  [Sidebar]  Dashboard                      │
│             ─────────────                  │
│             ┌──────────────────────────┐  │
│             │ Bot Status               │  │
│             │  ● Running               │  │
│             │  PID 12345               │  │
│             │  Uptime 00:15:42         │  │
│             │  Started 14:23:11        │  │
│             │                          │  │
│             │  [ Stop ] [ Restart ]    │  │
│             └──────────────────────────┘  │
│                                            │
│             Recent Logs (200 lines)        │
│             ┌──────────────────────────┐  │
│             │ [scroll, monospace]      │  │
│             │ ...                      │  │
│             └──────────────────────────┘  │
└────────────────────────────────────────────┘
```

- `BotStatusCard` — 5초 polling (`useSWR` 또는 단순 `setInterval`).
- 버튼 클릭 시 즉시 disabled 처리, optimistic toast, status 카드 즉시 refetch.
- `LogTail` — 5초 polling, auto-scroll to bottom (사용자가 위로 스크롤하면 자동 정지 — M0 기본은 단순 `<pre>` 로 시작, 정교화는 M5).

---

## 6. 테스트 시나리오

수동 테스트 (M0 에는 자동화 X — M1+ 에서 vitest 도입).

1. **Cold start**: `cd platform && npm install && npm run dev` → http://127.0.0.1:9000 → `/dashboard` 자동 이동 → 카드 `● Stopped`.
2. **Start**: 버튼 → 2초 안에 `● Running` 으로 전환, PID 표시. 텔레그램 봇 (EllaSFWTestBot) 에서 `/start` → 응답 확인.
3. **Stop**: 버튼 → 6초 안에 `● Stopped` 로 전환. PID 파일 삭제 확인 (`ls run/bot.pid` → no such file).
4. **Restart**: Running 상태에서 버튼 → 약 6–8초 후 새 PID 로 `● Running`.
5. **Logs**: Running 중 봇이 메시지 처리 → 로그 카드에 새 라인 등장 (5초 안에).
6. **Stale PID**: 봇을 Next.js 모르게 외부에서 `kill -9` → 5초 polling 후 카드 `● Stopped` (stale PID 파일 자동 정리됨).
7. **Double start**: Running 중 Start 버튼 클릭 → `409` 응답, toast `bot is already running`.
8. **External access blocked**: 다른 머신에서 `curl http://<lan-ip>:9000/api/bot/status` → 거부 (127.0.0.1 바인딩).
9. **Next.js 종료 후 봇 생존**: `npm run dev` Ctrl-C → 봇 PID 살아있음 (`ps aux | grep src.bot`) — 재시동 후 dashboard 가 동일 PID 인식.

---

## 7. 의존성 (package.json)

```json
{
  "dependencies": {
    "next": "14.x",
    "react": "18.x",
    "react-dom": "18.x",
    "@radix-ui/react-slot": "*",
    "class-variance-authority": "*",
    "clsx": "*",
    "lucide-react": "*",
    "tailwind-merge": "*",
    "tailwindcss-animate": "*"
  },
  "devDependencies": {
    "typescript": "5.x",
    "@types/node": "*",
    "@types/react": "*",
    "tailwindcss": "*",
    "postcss": "*",
    "autoprefixer": "*",
    "eslint": "*",
    "eslint-config-next": "*"
  }
}
```

shadcn 컴포넌트는 `npx shadcn@latest add button card badge sidebar` 로 추가 (lock 파일에 의존성 자동 갱신).

`npm run dev -- -H 127.0.0.1 -p 9000` 으로 시작.

---

## 8. 위험 / 결정 필요

### ★ 결정 필요 #1 — Python 인터프리터 경로
- **A**: 시스템 `python` (PATH). M0 단순. venv 활성화 책임은 사용자.
- **B**: `.env` 에 `PYTHON_BIN=/path/to/venv/bin/python` 추가, `bot-process.ts` 가 사용. M0 부터 안정.
- **권장**: B. 이미 venv 사용 중이며 PATH 에 leak 안 시키는 게 깔끔.

### ★ 결정 필요 #2 — 포트
- plan §3.1 에서 9000 으로 적었음. **9000 그대로 진행** 가정.

### ★ 결정 필요 #3 — 로그 파일 회전
- M0 에서는 회전 X (단순 append). 대용량 logs/bot.log 를 그냥 두는 위험 있음. M5 에서 회전 정책 도입 가정.
- M0 에서는 `npm run dev` 시작 시 메시지로만 안내.

### ★ 결정 필요 #4 — 봇 자동 시작
- Next.js dev 서버 시작 시 봇을 자동 start? **No.** 사용자가 명시적 Start 버튼 클릭. 안전.

### 위험: 좀비 프로세스
- `child.unref()` + `detached: true` 로 분리. Next.js 가 이상 종료해도 봇은 살아남음. 다시 띄울 때 PID 파일로 인식.

### 위험: 동일 텔레그램 token 으로 동시에 두 인스턴스
- Telegram getUpdates polling 충돌 → `Conflict` 에러. M0 에서는 더블-start 차단으로 방지. 외부에서 직접 `python -m src.bot` 실행한 경우는 사용자 책임.

---

## 9. 커밋 계획

| # | 메시지 | 내용 |
|---|---|---|
| 1 | `chore: scaffold platform/ Next.js app` | `create-next-app` 결과물 + tailwind/shadcn 초기화 |
| 2 | `feat(platform): sidebar layout + page placeholders` | layout.tsx + 8개 page.tsx (placeholder) |
| 3 | `feat(platform): bot-process.ts (spawn/stop/status)` | lib/bot-process.ts + run/ 디렉터리 .gitignore |
| 4 | `feat(platform): /api/bot/{status,start,stop,restart,logs}` | 5개 API route |
| 5 | `feat(platform): dashboard UI (status card + log tail)` | Dashboard 페이지 + 컴포넌트 |
| 6 | `docs: M0 done — STATUS.md / CLAUDE.md / platform/CLAUDE.md` | 문서 갱신, develop 머지 직전 |

---

## 10. develop 머지 체크리스트

- [ ] 모든 테스트 시나리오 (§6) 수동 통과.
- [ ] `STATUS.md` 갱신 (M0 완료 표시).
- [ ] `platform/CLAUDE.md` 신규 작성.
- [ ] 루트 `CLAUDE.md` Implementation Status 표 업데이트.
- [ ] `.gitignore` 에 `run/`, `platform/node_modules/`, `platform/.next/` 포함.
- [ ] `README.md` 또는 루트 README 에 "로컬 admin 시작법" 한 단락.
