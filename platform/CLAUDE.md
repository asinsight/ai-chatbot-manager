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

**M6 완료 (develop 머지 대기)** — Lorebook editor + char→world mapping.

| 페이지 | 상태 |
|---|---|
| `/dashboard` | ✅ Bot status card + Connections health card + log tail (5s polling). M5 에서 메인 봇 미설정 시 경고 배너 + Start 비활성, `/env?cat=tokens` 링크. |
| `/connections` | ✅ 4 endpoint cards (ComfyUI / OpenWebUI / Grok / Prompt Guard) — URL+token 편집 + Ping + last_ping SQLite 기록 + 전체 Ping |
| `/env` | ✅ 8 카테고리 tabs + 카테고리 description + 시크릿 마스킹 + 자동 백업 + default placeholder + Bot tokens 탭 grouping (Native / Character read-only with redirect). M5: `MAIN_BOT_*` 빨간 required 배지 + 빈 값 시 Save 차단, `?cat=` URL 파라미터로 탭 자동 선택, `COMFYUI_WORKFLOW{,_HQ}` 노출. |
| `/prompts` | ✅ 3 outer tabs (Grok prompting / System prompt / Profile keys). Grok+System: Monaco 65vh + react-diff-viewer modal + per-key save + ${var} lint + 인라인 metadata. Profile keys: master-detail + chips (M4) |
| `/characters` | ✅ list (cards + create + duplicate + delete with AlertDialog) + /[charId] (Form 모드: Persona/Behaviors/Images/Bot tokens 4 탭, Raw JSON 모드: 3 Monaco). draft auto-save (localStorage) + first_mes markdown preview + ajv validation + soft-delete. M4: read-only "View schema" Dialog (`character_card_schema.json` 참고용) |
| `/lorebook` | ✅ Mapping card (per-char dropdown ↔ `world_info/mapping.json`, "(legacy fallback)" 옵션) + World list (Add/Duplicate/Delete with WORLD_IN_USE 안내) + World editor (Test pane mirrors `src/prompt.py _match_world_info()` + entry CRUD: keywords chips / content textarea / position background\|active select). |
| `/config` | ✅ 3 탭 (SFW scenes / Pose motion presets / SFW denylist) — master-detail + chips + Raw JSON fallback + zod 검증 + 자동 백업 |
| `/workflows` | ✅ Stage assignments (Standard / HQ ↔ `COMFYUI_WORKFLOW{,_HQ}` env) + 워크플로우별 auto facts (node count / Σ steps / refiner+detailer / size) + admin description (`config/workflow_descriptions.json`) + Form / Raw JSON / Replace 3 탭. Replace 시 `%prompt%` + `%negative_prompt%` placeholder 검증 강제. |
| `/logs` | ✅ file picker (bot.log + dated archives) + tail 200-5000 + refresh 1s/2s/5s/Paused + regex filter (case-insensitive) + auto-scroll + download. |

> M1 단계에서 코드/UI 전체가 영어로 통일됐다 (PM 결정 D). Markdown 문서 (이 파일 포함) 만 한국어 유지. `lib/env-categories.ts` 의 카테고리 라벨, toast 메시지, 컴포넌트 텍스트 모두 영어.

> M3 단계에서 **TEST_/PROD_ 분리 제거** — 오픈소스 단일 deployment 라 `MAIN_BOT_TOKEN` / `CHAR_BOT_<id>` 단일 namespace 만 사용. `src/bot.py` 의 env-prefix 매핑 코드 삭제됨.

> M4 단계에서 `character_card_schema.json` 의 description 필드를 한국어 → 영어로 번역. /characters 의 read-only schema viewer 가 i18n 본 그대로 노출.

> M5 단계에서 사이드바 / browser title 을 "Chatbot Manager" 로 rename. `--popover` CSS 변수 + tailwind `popover` 토큰 추가 (shadcn Select 투명 fix). `src/logging_config.py` 의 StreamHandler 제거 — Python 의 file handler 와 platform stdout redirect 가 같은 `bot.log` 에 중복 기록하던 문제 해결. 메인 봇 strict: `bot.py` 가 `MAIN_BOT_TOKEN` / `MAIN_BOT_USERNAME` 비어있으면 SystemExit, platform 도 spawn 전 pre-flight 422 으로 차단.

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
│   ├── characters/                     # M3 — CRUD UI + M4 schema viewer
│   │   ├── {page,characters-list,schema-viewer}.tsx  # list + actions + read-only schema Dialog
│   │   └── [charId]/{page,character-editor,persona-form,behaviors-form,images-form,bot-tokens-form,preview-panel,raw-tab,widgets}.tsx
│   ├── config/                         # M4 — Image config editor (3 tabs)
│   │   └── {page,config-page,master-detail,raw-json-pane,tab-header,use-config-file,sfw-scenes-tab,pose-motion-presets-tab,sfw-denylist-tab,profile-keys-tab}.tsx
│   ├── workflows/                      # M5 — ComfyUI workflow management
│   │   └── {page,workflows-page,stage-assignments,workflow-tab,workflow-form,workflow-raw,workflow-replace,workflow-facts}.tsx
│   ├── logs/                           # M5 — full-page log viewer
│   │   └── {page,logs-page}.tsx
│   ├── lorebook/                       # M6 — per-character world knowledge editor
│   │   └── {page,lorebook-page,world-list,world-editor,entry-form,test-pane,mapping-card}.tsx
│   └── api/
│       ├── bot/                        # M0 — 5 routes (status/start/stop/restart/logs). M5: status returns main_bot.{token_set,username_set}; start returns 422 MAIN_BOT_NOT_CONFIGURED; logs route accepts ?file= + ?listFiles=1.
│       ├── env/                        # M1 — GET / PUT
│       ├── connections/                # M1 — GET, [id] PUT, [id]/ping POST, ping-all POST
│       ├── prompts/{grok,system}/      # M2 — GET / PUT
│       ├── characters/                 # M3 — list/create + [charId] CRUD + [charId]/env (token+username) + [charId]/duplicate
│       ├── character-schema/           # M4 — GET-only read-only schema fetch
│       ├── config/[fileKey]/           # M4 — GET / PUT for sfw_scenes / pose_motion_presets / sfw_denylist / profile_keys
│       ├── workflows/                  # M5 — list / [name] (safe_fields|replace) / assignments (env-backed) / descriptions
│       └── lorebook/                   # M6 — worlds list/CRUD/duplicate + char→world mapping
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
│   ├── characters.ts                   # M3 — 3-file bundle CRUD + soft-delete + nextFreeCharId
│   ├── char-schema.ts                  # M3 — PERSONA_FIELDS / IMAGES_FIELDS metadata + BLANK_* templates
│   ├── ajv.ts                          # M3 — Ajv2020 + validatePersona (draft-2020-12 schema)
│   ├── config-files.ts                 # M4 — server-side read/write/backup for the 4 config files
│   ├── config-files-meta.ts            # M4 — client-safe metadata (keys + display paths + tab titles)
│   ├── config-schemas.ts               # M4 — zod schemas for sfw_scenes / pose_motion_presets / sfw_denylist / profile_keys
│   ├── workflows.ts                    # M5 — read/write/backup for comfyui_workflow/*.json + auto facts + safe-fields + Replace validation + stage assignments (.env-backed) + descriptions
│   ├── workflows-meta.ts               # M5 — client-safe types
│   ├── log-files.ts                    # M5 — list bot.log + dated archives + path-traversal whitelist
│   ├── comfyui-client.ts               # post-M5 — fetchCheckpoints() proxy → ComfyUI /object_info/CheckpointLoaderSimple
│   ├── lorebook.ts                     # M6 — server-side read/write/backup + zod-validated CRUD for world_info/*.json + mapping
│   ├── lorebook-meta.ts                # M6 — client-safe types + previewMatches() (mirrors src/prompt.py _match_world_info)
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
| `/api/characters` | GET | `{characters: [{charId,name,profile_summary_ko,mtime}]}` | 500 |
| `/api/characters` | POST `{from?}` | `{ok, charId}` | 409 NO_FREE_SLOT / 422 INVALID_CHAR_ID |
| `/api/characters/[charId]` | GET | `{charId, persona, behaviors, images}` | 404 UNKNOWN_CHARACTER |
| `/api/characters/[charId]` | PUT `{persona,behaviors,images}` | `{ok, backup_paths, warnings}` | 422 INVALID_CARD / INCOMPLETE_BUNDLE |
| `/api/characters/[charId]` | DELETE | `{ok, backup_dir}` (soft-delete) | 422 INVALID_CHAR_ID |
| `/api/characters/[charId]/env` | GET | `{fields:{token,username}, keys}` | 422 INVALID_CHAR_ID |
| `/api/characters/[charId]/env` | PUT `{token?,username?}` | `{ok, backup_path, updated_keys}` | 422 INVALID_VALUE |
| `/api/characters/[charId]/duplicate` | POST | `{ok, charId}` (next-free) | 404 UNKNOWN_CHARACTER |
| `/api/character-schema` | GET | `{file_path, content}` (read-only) | 500 SCHEMA_READ_FAILED |
| `/api/config/[fileKey]` | GET | `{key, content, mtime}` | 404 UNKNOWN_FILE_KEY / 500 |
| `/api/config/[fileKey]` | PUT `{content}` | `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / MISSING_GENERIC / 500 SAVE_FAILED |
| `/api/workflows` | GET | `{ workflows: [{name, mtime_ms, size_bytes, facts, description, stage_badges, assignable}] }` | 500 |
| `/api/workflows/[name]` | GET | `{ name, content, mtime_ms, size_bytes, facts, safe_fields }` | 404 UNKNOWN_WORKFLOW / 422 |
| `/api/workflows/[name]` | PUT `{kind: "safe_fields"|"replace", ...}` | `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / NO_CHECKPOINT_LOADER / PLACEHOLDER_MISSING |
| `/api/workflows/assignments` | GET / PUT `{standard?,hq?}` | `{standard, hq, options}` / `{ok, backup_path}` | 422 UNKNOWN_FILE |
| `/api/workflows/descriptions` | GET / PUT `{filename, description}` | `{content}` / `{ok, backup_path}` | 422 UNKNOWN_FILE |
| `/api/bot/status` | GET | (existing) + `main_bot: {token_set, username_set}` | 500 |
| `/api/bot/start` | POST | `{ pid }` | 422 MAIN_BOT_NOT_CONFIGURED / 409 ALREADY_RUNNING / 500 START_FAILED |
| `/api/bot/logs` | GET `?file=&tail=&listFiles=` | `{lines, note?}` \| `{files}` | 422 INVALID_FILE / 500 LOGS_FAILED |
| `/api/comfyui/checkpoints` | GET | `{ok, comfyui_url, checkpoints}` \| `{ok:false, reason, message, checkpoints:[]}` | 200 always (failures inline) |
| `/api/lorebook/worlds` | GET / POST `{name}` | `{worlds: [...]}` / `{ok, name}` | 422 INVALID_NAME / 409 ALREADY_EXISTS |
| `/api/lorebook/worlds/[name]` | GET / PUT `{content}` / DELETE | `{name, content, mtime_ms, size_bytes, mapped_chars}` / `{ok, restart_required, backup_path}` | 422 INVALID_SHAPE / WORLD_IN_USE / 404 UNKNOWN_WORLD |
| `/api/lorebook/worlds/[name]/duplicate` | POST | `{ok, name}` | 404 UNKNOWN_WORLD |
| `/api/lorebook/mapping` | GET / PUT `{mapping}` | `{mapping, characters, worlds}` / `{ok, restart_required, backup_path}` | 422 UNKNOWN_WORLD / UNKNOWN_CHARACTER |

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
- **ajv** + **ajv/dist/2020** (M3) — JSON Schema validator (draft-2020-12).
- **@radix-ui/react-alert-dialog** (M3) — delete-character confirmation.
- **react-markdown** + **remark-gfm** (M3) — first_mes preview rendering.
- **zod** (M4) — shape validation for the 4 config files in `/config` + `/prompts` profile_keys.
- **@radix-ui/react-select** (M4) — anchor_risk select widget on pose_motion_presets entries.

## 편집 가이드

1. **타입체크 필수**: `npm run typecheck` (또는 `npx tsc --noEmit`). 매 commit 전 확인.
2. **Server vs Client**: API route 는 Node runtime, UI 컴포넌트는 `"use client"` 선언 (`bot-status-card.tsx`, `log-tail.tsx` 등).
3. **`@/*` import alias** — `tsconfig.json` 에 정의됨. 항상 절대 import (`@/lib/...`, `@/components/...`).
4. **봇 프로세스 외부 영향**: `lib/bot-process.ts` 변경 시 항상 수동 테스트 — start/stop/restart/stale-pid 시나리오. `npm run build` 만으로는 race 검증 안 됨.
5. **새 마일스톤 시작 시**: 새 feature 브랜치 + `docs/features/M<N>_<name>.md` plan + 사인오프 → 구현. 머지 시 `platform/CLAUDE.md` 의 "현재 마일스톤" 표 갱신.

## Post-M6 시작 시 주의

핵심 8 페이지가 모두 활성. 새 페이지를 추가할 땐:
- 사이드바 ([components/sidebar.tsx](components/sidebar.tsx)) `items` 배열에 항목 추가
- 같은 폴더 패턴 따르기: `app/<page>/page.tsx` (서버 entry) + `<page>-page.tsx` (클라이언트) + 보조 컴포넌트들
- 서버 lib 와 클라이언트 lib 분리 (`*.ts` 와 `*-meta.ts`) — 클라이언트에서 `node:fs`/`node:path`를 import 하면 webpack build 가 깨짐 (M4 / M6 에서 모두 겪음)
- API route 는 `runtime = 'nodejs'` + `dynamic = 'force-dynamic'`
- 자동 backup 은 `lib/backup.ts` 의 KST timestamp 패턴 재사용

`character_card_schema.json` 은 read-only viewer 만 노출 (M4). 직접 편집 시 platform UI 우회 — 변경 시 char05 round-trip ajv 검증 필요.
