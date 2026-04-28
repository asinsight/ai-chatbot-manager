# ella-chat-publish — 로컬 Admin 웹앱 Plan (v2 / Next.js 풀스택)

> **목적**: ella-chat-publish (SFW Telegram 봇) 의 모든 운영 구성 요소(.env, 캐릭터 카드, prompt JSON, 이미지/비디오 generator config, ComfyUI 워크플로우)를 편집·관리하고 봇 라이프사이클(start/stop/restart)을 제어하는 **로컬 Next.js admin 콘솔**.
>
> **상태**: Plan only. 사인오프 후 M0 시작.
>
> **버전**: v2 — Next.js 풀스택 단일 프로세스로 단순화 (v1의 FastAPI + Vite 분리 안 함).

---

## 1. 목표와 비목표

### 목표 (In-scope)
1. fork repo 모든 운영 구성 요소를 **로컬 웹 UI** 로 편집·관리.
2. 편집 대상:
   - `.env` 변수 (LLM 백엔드 4개 변수 — `OPENWEBUI_URL`, `OPENWEBUI_API_KEY`, `MODEL_NAME`, `LLM_API_PATH` — 제외)
   - 캐릭터 카드 (`behaviors/charNN.json` + `persona/charNN.json` + `images/charNN.json`)
   - Prompt JSON (`config/grok_prompts.json`, `config/system_prompt.json`)
   - 이미지 생성기 config (`config/sfw_scenes.json`, `config/pose_motion_presets.json`, `config/profile_keys.json`, `config/sfw_denylist.json`, `character_card_schema.json`)
   - ComfyUI 워크플로우 (`comfyui_workflow/*.json`)
3. **봇 라이프사이클**: start / stop / restart / 상태 / 로그 tail.
4. **새 캐릭터 추가**: charNN 자동 할당 → 3-파일 빈 템플릿 + .env 라인 자동 추가 → 봇 재시작 후 자동 로드.
5. **ComfyUI 워크플로우 업로드/삭제 + 활성 지정**.
6. **이미지 생성**: Danbooru 태그만 (자연어 입력 X).
7. **비디오 생성**: Atlas Cloud `wan-2.6/image-to-video-flash` 만 (초기).
8. SillyTavern 컨셉(character card / world info / quick reply) 차용. LLM 채팅 콘솔은 X.

### 비목표 (Out-of-scope)
- LLM 백엔드 라우팅 변경 / 모델 swap.
- NSFW 가능 토글 / NSFW 분기 재도입.
- 텔레그램 메시지 송수신 / 사용자 차단 / 봇 DB 직접 편집.
- 멀티유저 / RBAC.
- 모바일 반응형.
- ComfyUI 노드 그래프 시각 편집.
- 자동 마이그레이션.

---

## 2. 아키텍처 (단순화)

```
┌──────────────────────────────────────────┐
│     Browser (http://127.0.0.1:9000)      │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Next.js (단일 프로세스, npm run start)            │
│  ┌────────────────────┐  ┌────────────────────┐  │
│  │  app/ pages        │  │  app/api routes    │  │
│  │  (React + shadcn)  │  │  (REST + WS)       │  │
│  └────────────────────┘  └─────────┬──────────┘  │
└────────────────────────────────────┼─────────────┘
                                     │
        ┌────────────────────────────┼─────────────────────────┐
        │                            │                          │
        ▼                            ▼                          ▼
┌──────────────────┐     ┌──────────────────────┐    ┌──────────────────┐
│ ella-chat-pub/   │     │ Python 봇 subprocess │    │ platform.sqlite  │
│ - .env           │     │ child_process.spawn  │    │ (audit log only) │
│ - behaviors/     │     │ ("python3 -m         │    │                  │
│ - persona/       │     │   src.bot")          │    │                  │
│ - images/        │     │ PID file 추적        │    │                  │
│ - config/*.json  │     │ stdout → log file    │    │                  │
│ - comfyui_wf/    │     │                      │    │                  │
└──────────────────┘     └──────────────────────┘    └──────────────────┘
```

### 데이터 흐름
1. **편집**: Browser → Next.js API route → 백업(`data/backups/<file>.<ts>.bak`) → JSON/.env 검증 → 원본 갱신 → 응답에 "재시작 필요" 플래그
2. **봇 제어**: Browser → API route → `child_process.spawn` / `process.kill(SIGTERM)` → PID 갱신 → 응답
3. **로그 tail**: 봇 stdout → `logs/bot.log` → Next.js API route fs.watch → WebSocket → Browser

### 핵심 단순화 포인트
- **단일 프로세스**: Next.js 가 페이지 + API + 정적 파일 모두 처리. 별도 backend 미존재.
- **단일 언어 (TypeScript)**: 프론트엔드 + API 모두 TS. Python 의존성 제로 (봇 빼고).
- **봇은 subprocess**: Next.js API route가 `child_process.spawn(["python3", "-m", "src.bot"])` 으로 띄움. PID file 만 관리.
- **빌드/배포 단순**: `npm install && npm run build && npm run start` — 끝.

---

## 3. 기술 스택 (확정)

| 항목 | 선택 | 비고 |
|---|---|---|
| Framework | **Next.js 15+ (App Router)** | 풀스택. SSR 안 쓰고 client-side render 위주, API routes로 backend 처리 |
| 언어 | **TypeScript** | 풀스택 단일 언어 |
| UI | **shadcn/ui (Radix + Tailwind)** | 폼/다이얼로그/테이블 빠르게 |
| JSON Editor | **Monaco Editor** (`@monaco-editor/react`) | grok_prompts 같은 큰 텍스트용 |
| JSON Schema | **ajv** | character_card_schema.json 검증 |
| .env 파서 | **`dotenv` + 자체 라인 보존 파서** | 주석/순서 보존 — `dotenv` 는 파싱만, 쓰기는 자체 구현 |
| 봇 subprocess | **Node `child_process`** | spawn / kill / signal handling |
| WebSocket | **`ws` 라이브러리** + Next.js custom server (또는 `socket.io`) | 로그 tail |
| DB (audit) | **`better-sqlite3`** | 동기 API, 단순 |
| Diff viewer | **`react-diff-viewer-continued`** | 저장 전/후 비교 |
| 디렉터리 | **`/Users/junheeyoon/Code/ella-chat-publish/platform/`** | fork 안 서브디렉터리 |

### 결정 이유 요약
- Next.js 풀스택: 단일 프로세스 / 단일 빌드 / 단일 배포. PM 명시 단순화.
- TypeScript: 타입 안전, IDE 지원, frontend-backend 같은 모델 공유.
- shadcn/ui: 코드 자체를 복사해 가져오는 형식 — 디자인 커스텀 자유롭고 의존성 가벼움.
- Monaco: 큰 prompt 텍스트 편집에 VSCode 동급 UX (라인 번호, 검색, 멀티 커서).
- ajv: 사실상 표준 JSON schema validator.

---

## 4. 기능 명세 (MVP)

### 4.1 .env 편집기
- **편집 가능 (모든 변수)**:
  - Connections (별도 §4.8 섹션 참조 — Connections 페이지에서도 동일 변수 편집): `OPENWEBUI_URL`, `OPENWEBUI_API_KEY`, `MODEL_NAME`, `LLM_API_PATH`, `GROK_API_KEY`, `GROK_MODEL_NAME`, `COMFYUI_URL`, `PROMPT_GUARD_URL`, `PROMPT_GUARD_THRESHOLD`, `PROMPT_GUARD_TIMEOUT`, `ATLASCLOUD_API_KEY`
  - 운영: `IMAGE_AUTONOMY`, `FORCE_SFW_SCENE`, `ENV`, `ADMIN_USER_IDS`, `ADMIN_NOTIFY`, `LOG_LEVEL`
  - LLM 큐: `LLM_MAX_CONCURRENT`, `LLM_MAX_QUEUE_SIZE`, `LLM_QUEUE_TIMEOUT`
  - 메모리/요약: `SUMMARY_THRESHOLD`, `RECENT_MESSAGES_KEEP`
  - 봇 토큰: `TEST_*_BOT_TOKEN`, `TEST_*_BOT_USERNAME`, `PROD_*` (캐릭터별 동적)
  - RunPod (이미지): `RUNPOD_ENDPOINT_ID`
  - ComfyUI 부수: `COMFYUI_MAX_QUEUE`, `COMFYUI_STUCK_TIMEOUT`, `COMFYUI_VRAM_MIN_MB`
- **편집 불가 (read-only 표시)**: `VIDEO_MODEL` (★ #9.5 — wan-2.6-flash 고정)
- **저장 동작**:
  - .env 파일을 라인 단위 파싱 (주석/순서/빈 줄 보존)
  - 변경 전 백업
  - 시크릿 마스킹 (`••••••<last4>` + reveal toggle) — `*_API_KEY` / `*_BOT_TOKEN` 패턴 자동 마스킹
  - 응답에 `restart_required: true`
- **API**:
  - `GET /api/env` → `{ vars: [{ key, value, masked, comment, editable, category }] }`
  - `PUT /api/env` body `{ updates: { key: value } }` → `{ ok, restart_required, backup_path }`

### 4.2 캐릭터 카드 편집기
- **3-파일 묶음** (behaviors/persona/images) 단일 form 으로 편집.
- **CRUD**:
  - List (카드뷰 — name, profile_summary_ko, mtime)
  - Create: charNN 자동 할당 (현재 char01–char09 → 다음 char10) + 빈 템플릿 + `TEST_/PROD_CHAR_BOT_<charNN>` .env 라인 자동 추가
  - Edit: 통합 form (탭: Persona / Behaviors / Images)
  - Duplicate: 다음 빈 charNN 으로 복제 (이름에 `(copy)` prefix)
  - Delete: 3 파일 백업 후 삭제 + .env 라인도 제거 옵션
- **편집 모드**: Form (schema 기반) + Raw JSON (Monaco) 토글 — ★ #9.1
- **미리보기**: `first_mes` / `description` 마크다운 렌더, `{{user}}` / `{{char}}` 매크로 dummy 치환
- **API**:
  - `GET /api/characters`
  - `GET /api/characters/[charId]`
  - `POST /api/characters` `{ name, base_template? }`
  - `PUT /api/characters/[charId]` `{ persona, behaviors, images }`
  - `POST /api/characters/[charId]/duplicate`
  - `DELETE /api/characters/[charId]`

### 4.3 Prompt 편집기
- **`config/grok_prompts.json`** 5 키: `system`, `video_analyzer`, `random`, `classify`, `partial_edit`
  - 각 Monaco textarea
  - 길이 카운터
  - JSON parse fail-fast
  - 빈 문자열 거부 (CLAUDE.md 원칙)
  - `${var}` placeholder lint
- **`config/system_prompt.json`** 2 키: `master_prompt`, `image_signal_format`
- Diff viewer (저장 전/후)
- **API**:
  - `GET /api/prompts/grok` / `PUT /api/prompts/grok`
  - `GET /api/prompts/system` / `PUT /api/prompts/system`

### 4.4 이미지 생성기 config 편집기
별도 탭 또는 페이지:
- **sfw_scenes.json** — scene 카드뷰 + chip input (pose_pool / camera_pool / scene_tags)
- **pose_motion_presets.json** — pose entry 추가/편집
- **sfw_denylist.json** — keyword chip input
- **profile_keys.json** — key 화이트리스트 chip input
- **character_card_schema.json** — Monaco raw JSON + 저장 전 모든 캐릭터 dry-run validate
- **API 패턴**: `GET /api/config/[fileKey]` / `PUT /api/config/[fileKey]`
  - fileKey: `sfw_scenes` | `pose_motion_presets` | `sfw_denylist` | `profile_keys` | `character_card_schema`

### 4.5 ComfyUI 워크플로우 관리 (PM 결정 반영 — 단순화)
- **List**: `comfyui_workflow/*.json` 모든 파일 listing (filename, size, mtime, status). 봇 코드(`src/comfyui.py`)는 기존처럼 `main_character_build.json`(또는 그 이름) 을 직접 사용 — **별도 활성 메커니즘 없음**. 워크플로우 파일명 자체가 contract.
- **Edit (JSON viewer)**: 각 워크플로우를 Monaco JSON editor 로 직접 편집. 저장 시:
  - JSON syntax 검증 (parse 통과 필수)
  - **placeholder 존재 검증** (필수): 워크플로우 노드 중에 `%prompt%` (positive) + `%negative_prompt%` (negative) placeholder 가 둘 다 존재해야 함. 누락 시 **save 거부 + error 표시**:
    - `Positive prompt placeholder (%prompt%) not found` 또는
    - `Negative prompt placeholder (%negative_prompt%) not found`
  - 백업 → 갱신 → "재시작 필요" 배너
- **Replace (이름 유지)**: 새 워크플로우 사용 = 같은 파일명의 .json 으로 업로드 교체 (기존 파일을 덮어쓰기). 워크플로우 이름 유지가 핵심. 봇 코드는 항상 같은 이름으로 로드.
- **Upload (신규 파일명)**: 신규 .json 도 업로드 가능 — 단 봇이 자동으로 사용하지는 않음 (봇은 하드코드된 이름만 로드). 사용자가 운영 시 같은 이름으로 교체 필요. (활성 메커니즘 향후 도입 시 [§9.2 미결] 변경 가능.)
- **Delete**: 워크플로우 삭제 가능. 단 봇이 사용하는 이름(`main_character_build.json`)을 삭제하면 봇 시작 실패 — UI 가 경고 표시.
- **LoRA 슬롯**: 모든 워크플로우의 Power Lora Loader 노드(Power Lora Loader rgthree)에서 `lora_N` 슬롯은 **빈 상태**로 시작 (Phase 7에서 일괄 제거 완료). UI 에서 사용자가 LoRA 추가하려면 JSON viewer 로 직접 추가 + placeholder 검증은 그대로.
- **API**:
  - `GET /api/workflows` → list `[{ filename, size, mtime, has_pos_placeholder, has_neg_placeholder }]`
  - `GET /api/workflows/[filename]` → 워크플로우 JSON 본문 (편집용)
  - `PUT /api/workflows/[filename]` → JSON 본문 저장 + placeholder 검증
  - `POST /api/workflows` (multipart) → 신규 파일 업로드 + 검증
  - `DELETE /api/workflows/[filename]` → 백업 후 삭제

### 4.6 봇 라이프사이클 제어
- **상태**: running / stopped / starting / stopping + PID + uptime + 등록된 봇 목록 + last exit code
- **시작**: `child_process.spawn("python3", ["-m", "src.bot"], { cwd: <fork>, stdio: ["ignore", logFd, logFd] })` → PID file 작성 → 5초 모니터 (즉시 종료 시 실패)
- **종료**: `process.kill(pid, "SIGTERM")` → 10초 대기 → 살아있으면 `SIGKILL`
- **재시작**: stop → 5초 wait → start
- **로그 tail**: WebSocket `/api/bot/logs/ws` → 봇 stdout (`logs/bot.log`) tail (마지막 200 + 신규 라인)
- **API**:
  - `GET /api/bot/status`
  - `POST /api/bot/start`
  - `POST /api/bot/stop`
  - `POST /api/bot/restart`
  - `WS /api/bot/logs/ws` (또는 polling fallback `GET /api/bot/logs?tail=500`)

### 4.8 Connections (LLM/외부 서비스 연결)
PM 명시: "URL과 token 저장, ping test 후 success or fail 메세지". 4개 endpoint 를 단일 페이지에서 관리.

대상 endpoint (각 `URL` + `token` + Ping 버튼 + status badge):

| 서비스 | URL 변수 | Token 변수 | Token blank 허용 | Ping 검증 방법 |
|---|---|---|---|---|
| **ComfyUI** | `COMFYUI_URL` | (없음) | — | `GET <URL>/system_stats` (200 OK + JSON 파싱 성공) |
| **Gemma4 / OpenWebUI** | `OPENWEBUI_URL` | `OPENWEBUI_API_KEY` | ✅ (local llama-cpp-python 일 때 blank) | `GET <URL>/v1/models` with optional `Authorization: Bearer <token>` (200 OK) |
| **Grok** | (Grok 의 base URL — 현재 코드는 X.AI 기본값 하드코드. ★ #9.9 — 별도 변수 추가할지 결정) | `GROK_API_KEY` | ❌ (필수) | `GET https://api.x.ai/v1/models` with `Authorization: Bearer <token>` (200 OK 또는 401/429 등 명확한 응답으로 token 형식 확인) |
| **Prompt Guard** | `PROMPT_GUARD_URL` | (없음 — 현재 비공개; ★ #9.9 — 토큰 추가할지 결정) | — | `GET <URL>/health` (200) 또는 fallback `POST <URL>/check` 더미 텍스트 |

**UI 윤곽 (Connections 페이지)**:
- 각 서비스마다 카드:
  - URL input (필수 — placeholder 에 예시: `http://192.168.x.x:8080`)
  - Token input (`<input type="password">` + reveal toggle — blank 허용 표시)
  - "🔌 Ping" 버튼
  - Status badge: 🟢 Success (응답 + 응답시간 ms) / 🔴 Fail (에러 메시지) / ⚪ Untested
  - "Save & Ping" 단축 버튼
- 페이지 상단에 "전체 Ping" 버튼 (4개 endpoint 일괄 검증)

**저장 동작**:
- URL/token 변경 시 `.env` 파일에 즉시 반영 (.env 편집기와 동일 백엔드)
- Ping 결과는 `platform.sqlite` 의 `connection_check` 테이블에 timestamp 와 함께 기록 (audit + 마지막 ping 결과 caching)

**Dashboard 통합**:
- 홈 Dashboard 에 "Connections health" 카드 — 4개 endpoint 마지막 ping 결과 요약 (🟢 4/4 또는 🔴 1 fail 등). 클릭 시 Connections 페이지로 이동.

**API**:
- `GET /api/connections` → `{ connections: [{ id, url, token_masked, last_ping: { ok, message, ms, ts } }] }`
- `PUT /api/connections/[id]` body `{ url, token }` → `.env` 갱신
- `POST /api/connections/[id]/ping` → 즉시 ping 수행 → `{ ok, message, ms, status_code }`
- `POST /api/connections/ping-all` → 4개 동시 ping

**Ping 구현 디테일**:
- Server-side fetch (브라우저에서 직접 호출하지 않음 — CORS / 사설 IP 접근).
- Timeout 10s default.
- ComfyUI: `system_stats` 엔드포인트가 GPU/VRAM 정보 반환 → 추가로 VRAM 표시 가능 (옵션).
- Grok: `models` 호출은 무료. Chat completion 호출은 비용 발생 — 절대 ping 으로 사용 X.
- Prompt Guard: `/health` 엔드포인트 존재 여부 봇 코드/서버 사이드 확인 후 결정. 없으면 단순 `POST /check` body `{"text":"hello","threshold":0.8}` (저비용).

### 4.7 안전 가드
- **자동 백업**: 모든 편집 전 `platform/data/backups/<rel_path>.<YYYYMMDD-HHMMSS>.bak`
- **JSON syntax 검증**: `json.parse` + ajv (해당 시)
- **`.env` 형식 검증**: key=value 라인 / 주석 / 빈 줄 패턴 유지
- **봇 재시작 시 자동 롤백** (★ #9.3): manual prompt 권장 — 시작 후 N초 안에 종료되면 UI 가 "복원할까요?" 묻기
- **Concurrent edit lock**: 파일별 in-memory mutex (Node 단일 프로세스라 단순)

---

## 5. 디렉터리 구조

```
ella-chat-publish/
├── src/                      # 봇 코드 (불변)
├── config/                   # 봇 config (편집 대상)
├── behaviors/, persona/, images/   # 캐릭터 카드 (편집 대상)
├── comfyui_workflow/         # 워크플로우 (편집 대상)
├── .env                      # 시크릿 (편집 대상)
├── platform/                 # ★ 신규 — Next.js 단일 앱
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── app/                  # App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx          # Dashboard
│   │   ├── env/page.tsx
│   │   ├── characters/
│   │   │   ├── page.tsx      # list
│   │   │   └── [charId]/page.tsx
│   │   ├── prompts/page.tsx
│   │   ├── config/[fileKey]/page.tsx
│   │   ├── workflows/page.tsx
│   │   ├── connections/page.tsx
│   │   ├── bot/page.tsx
│   │   ├── logs/page.tsx
│   │   └── api/              # API routes
│   │       ├── env/route.ts
│   │       ├── characters/route.ts
│   │       ├── characters/[charId]/route.ts
│   │       ├── prompts/grok/route.ts
│   │       ├── prompts/system/route.ts
│   │       ├── config/[fileKey]/route.ts
│   │       ├── workflows/route.ts
│   │       ├── workflows/[filename]/route.ts
│   │       ├── connections/route.ts             # GET 전체 + 마지막 ping
│   │       ├── connections/[id]/route.ts        # PUT URL/token
│   │       ├── connections/[id]/ping/route.ts   # POST 즉시 ping
│   │       ├── connections/ping-all/route.ts    # POST 4개 일괄 ping
│   │       ├── bot/status/route.ts
│   │       ├── bot/start/route.ts
│   │       ├── bot/stop/route.ts
│   │       ├── bot/restart/route.ts
│   │       └── bot/logs/ws/route.ts   # WebSocket
│   ├── lib/
│   │   ├── env-parser.ts     # .env 라인 보존 파서
│   │   ├── file-io.ts        # 백업 + 검증 + 갱신
│   │   ├── bot-process.ts    # subprocess 관리
│   │   ├── db.ts             # better-sqlite3 audit log
│   │   └── schema.ts         # ajv 검증
│   ├── components/           # shadcn/ui + custom
│   └── data/
│       ├── backups/          # 파일 백업
│       ├── platform.sqlite   # audit log
│       └── bot.pid           # 봇 PID
└── logs/
    └── bot.log               # 봇 stdout (admin tails)
```

---

## 6. 보안 / 배포

### 6.1 네트워크
- 기본: **127.0.0.1:9000** (외부 차단)
- 외부 노출 시: `PLATFORM_BIND=0.0.0.0` + `PLATFORM_ADMIN_TOKEN` 헤더 검증 (★ #9.4)

### 6.2 실행
- **dev**: `cd platform && npm run dev` (Next.js hot reload)
- **prod**:
  - `npm run build && npm run start`
  - 옵션: systemd unit `ella-chat-publish-admin.service` (Linux) / launchd plist (Mac)
  - 봇은 `ella-chat-publish.service` 와 별개. admin 이 subprocess 로 봇 띄우는 게 dev/prod 둘 다 동작.

### 6.3 의존성 관리
- `platform/` 안에 자체 `package.json` — 봇 (Python `requirements.txt`) 와 분리
- `npm install` 만 하면 됨 (Python 의존성 영향 X)

---

## 7. 데이터 무결성 / 백업

### 7.1 백업 정책
- 모든 편집 = 자동 백업 → `platform/data/backups/<rel_path>.<YYYYMMDD-HHMMSS>.bak`
- 보관: 무제한 (v1) → v2 에서 30일 회전 (★ #9.5)
- UI: `Backups` 페이지 — 파일별 백업 list + "이 시점으로 복원"

### 7.2 git 자동 commit
- v1 미도입 (★ #9.5)
- v2 에서 결정. `.env` 가 `.gitignore` 에 있어 자동 commit 가드 OK.

### 7.3 핫 리로드
- 봇은 config 핫 리로드 X. 편집 응답 / Dashboard 배너에 "재시작 필요" 표시.

---

## 8. 마일스톤 (M0 ~ M5)

### M0 — 골격 + 봇 dashboard + 시작/종료 (1.5–2일)
- `platform/` Next.js 프로젝트 초기화 (`npx create-next-app`)
- shadcn/ui 설치 + Tailwind 설정
- Layout (Sidebar nav + Header + Main)
- Dashboard 페이지 (봇 status 카드 + Start/Stop/Restart 버튼)
- `lib/bot-process.ts` (subprocess + PID file)
- `app/api/bot/status|start|stop|restart/route.ts`
- 로그 tail (M5 까지는 단순 polling — `GET /api/bot/logs?tail=500`)
- **테스트**: `npm run dev` → http://127.0.0.1:9000 → Start → 봇 PID 표시 → 텔레그램 봇 응답 → Stop → PID 사라짐.

### M1 — .env 편집기 + Connections (2–2.5일)
- `lib/env-parser.ts` (라인 보존 파서)
- `.env.example` 코멘트 추출 → 인라인 도움말
- 카테고리별 form (shadcn `Tabs`)
- 시크릿 마스킹 + `Eye` 아이콘 토글 (모든 `*_API_KEY` / `*_TOKEN` 자동 마스킹)
- 모든 변수 편집 가능 (LLM 백엔드 포함; `VIDEO_MODEL` 만 read-only)
- **Connections 페이지** (§4.8): 4개 endpoint 카드 (ComfyUI / OpenWebUI / Grok / Prompt Guard)
  - URL + token input + Ping 버튼 + status badge
  - "전체 Ping" 단축 버튼
  - Ping 결과 `platform.sqlite` `connection_check` 테이블에 기록
  - Dashboard 에 "Connections health" 요약 카드
- 저장 시 백업 + 검증 + "재시작 필요" toast
- **테스트**:
  - `GROK_API_KEY` 변경 → 백업 생성 → .env 갱신 → "Ping" 버튼 → 🟢 Success.
  - 잘못된 API key 입력 → "Ping" → 🔴 Fail (401).
  - ComfyUI URL 변경 → Ping → `system_stats` 응답.
  - Prompt Guard URL blank → Ping → 🔴 (URL 필수 안내).

### M2 — Prompt 편집기 (1일)
- `app/prompts/page.tsx` (Monaco editor)
- `grok_prompts.json` 5 키 + `system_prompt.json` 2 키
- JSON parse / 빈 값 검증
- `${var}` placeholder lint
- Diff viewer (`react-diff-viewer-continued`)
- **테스트**: `system` 한 줄 추가 → 저장 → 봇 재시작 → 다음 이미지 generation 에 반영 확인.

### M3 — 캐릭터 CRUD (2–2.5일)
- `app/characters/page.tsx` (list)
- `app/characters/[charId]/page.tsx` (edit form)
- Form 모드 (schema 기반 자동 생성) + Raw JSON 모드 토글 (★ #9.1 — 둘 다인 경우)
- Create / Duplicate / Delete
- 신규 시 `TEST_/PROD_CHAR_BOT_<charNN>` .env 자동 추가 (★ #9.7)
- first_mes 미리보기 ({{user}}/{{char}} 매크로)
- ajv 로 character_card_schema 검증
- **테스트**: 새 char10 추가 → 3 파일 + .env 라인 → 봇 재시작 → 로그에 `캐릭터 봇 등록: char10`.

### M4 — 이미지 config (1.5–2일)
- `app/config/[fileKey]/page.tsx`
- `sfw_scenes.json` scene 카드 편집 (chip input)
- `pose_motion_presets.json` 편집
- `sfw_denylist.json` chip input
- `profile_keys.json` chip input
- `character_card_schema.json` Monaco + dry-run (모든 캐릭터 validate)
- **테스트**: scene 추가 → `/random` 으로 N회 시도 → 새 scene 후보군 포함 확인.

### M5 — ComfyUI 워크플로우 + 로그 viewer (1.5–2일)
- `app/workflows/page.tsx` — list / upload / delete / activate
- 활성 메커니즘: `config/active_workflow.json` 추가 (★ #9.2)
- `src/comfyui.py` 가 이 값을 읽도록 별도 PR (Python 봇 코드 한 줄 수정)
- WebSocket 기반 실시간 로그 tail (`ws` 라이브러리)
- 로그 search/grep + 다운로드
- **테스트**: 새 워크플로우 업로드 → 활성 → 봇 재시작 → 새 워크플로우로 이미지 gen.

### Phase 2 (옵션)
- M6 — 인증 토큰 / HTTPS / 외부 노출 (★ #9.4)
- M7 — 비디오 모델 카탈로그 (현재 wan-2.6-flash 만)
- M8 — git 자동 commit / 다중 admin

**합계 ~9–11일** (M0–M5).

---

## 9. ★ PM 결정 필요 항목 (남은 것)

(v1 plan에서 결정된 항목: 기술 스택 (Next.js 풀스택), 디렉터리 위치 (서브디렉터리), 봇 프로세스 관리 (subprocess), 데이터 저장 (파일 + SQLite audit) — 모두 v2에 확정.)

### 9.1 캐릭터 편집 UX — ✅ 결정 완료
- **PM**: Form + Raw JSON 토글 — 둘 다 지원

### 9.2 ComfyUI 워크플로우 활성 메커니즘 — ✅ 결정 완료
- **PM**: 활성 메커니즘 도입 안 함. 봇 코드는 기존 파일명 그대로 사용. 사용자는 JSON viewer 로 같은 파일을 편집하거나 같은 이름의 .json 으로 교체.
- 부수 명세: positive(`%prompt%`) + negative(`%negative_prompt%`) placeholder 누락 시 save 거부.
- LoRA 슬롯은 모두 빈 상태 (Phase 7에서 즉시 처리 완료).

### 9.3 봇 자동 롤백 — ✅ 결정 완료 (PM: B Manual prompt)
**시나리오**: 사용자가 캐릭터 카드 / prompt JSON / .env 등을 편집 → "재시작" 버튼 클릭 → 봇 시작 → **봇이 5–10초 안에 즉시 종료** (편집된 파일에 syntax 에러 / 잘못된 schema / 봇이 거부할 값 등).

**현재 변경 추적**: 매 저장 시 `platform.sqlite` 의 `change_log` 테이블에 `{file_path, ts, before_path(=백업), after_content_hash}` 기록. 마지막 N건 (예: 5건) 의 변경 set 보유.

**3가지 행동 옵션**:
| 옵션 | 동작 |
|---|---|
| **A. 자동 롤백** | 봇 종료 감지 → 직전 변경 set 의 모든 파일을 백업에서 자동 복구 → 봇 재시작 시도 |
| **B. Manual prompt (권장)** | 봇 종료 감지 → UI 에 dialog 표시: "봇이 시작 직후 종료됨. 직전 변경: A.json, B.json. 복구하시겠습니까? [복구] [디버그하기]" |
| **C. 롤백 없음** | 봇 종료를 알리고 끝. 사용자가 직접 처리 (백업 페이지에서 수동 복원). |

**B 권장 이유**:
- 자동(A)은 의도적 변경까지 되돌릴 위험 — 예: 사용자가 캐릭터 5개를 일괄 편집한 후 봇이 다른 이유로 죽으면, 5개 모두 되돌려짐.
- 없음(C)은 사용자 부담이 큼 — 봇 로그 보고 어느 파일이 문제인지 직접 파악해야.
- B는 "어떤 파일이 마지막 변경이었고, 복구할지" 사용자가 한 클릭으로 결정.

**구현 부담**: B 가 가장 적당. dialog UI + 복원 버튼만 추가. A 는 자동화 + 안전성 검증 비용.

→ **PM 답변 요청**: A / B / C 중 어느 옵션?

### 9.4 인증 — ✅ 결정 완료
- **PM**: 127.0.0.1 only, v1 무토큰

### 9.5 백업 회전 — ✅ 결정 완료 (PM: A 무제한 v1)
**현재 백업 정책 (v1)**: 모든 편집 = `platform/data/backups/<rel_path>.<YYYYMMDD-HHMMSS>.bak` 으로 timestamp 백업. 무제한 누적.

**디스크 부담 추정**:
- 캐릭터 카드 1건 ≈ 5–10 KB. 9 캐릭터 × 3 파일 = ~150 KB.
- prompt JSON: grok_prompts.json ≈ 50 KB, system_prompt.json ≈ 7 KB.
- sfw_scenes.json ≈ 50 KB.
- .env ≈ 2 KB.
- 매일 5건 편집 × 365일 = 1825건/년 → ≈ **20–50 MB/년** (보수적).

**옵션**:
| 옵션 | 동작 |
|---|---|
| **A. 무제한 (권장 v1)** | 영구 보관. 디스크 부담 미미. 단순. |
| **B. 30일 회전** | 30일 지난 백업 자동 삭제. 디스크 일정. |
| **C. 최근 N건만** | 파일별로 최근 N건만 유지 (예: N=20). |
| **D. 회전 없이 수동 정리** | UI 에 "오래된 백업 정리" 버튼 — 사용자가 명시적 클릭 시만. |

**A (v1) 권장 이유**: 데이터 사이즈 작음 + 단순. v2에서 디스크 사용량 모니터링 후 회전 도입 결정.

→ **PM 답변 요청**: A / B / C / D 중 어느 옵션?

### 9.6 git 자동 commit — ✅ 결정 완료 (PM: A v1 미도입 — SQLite audit table 만)
**옵션**: 매 파일 저장 시마다 admin 앱이 자동으로 git commit 수행 (메시지 = `admin: edit <file>`).

**장점**:
- 깊이 있는 audit — `git log` / `git blame` / `git diff` 로 누가 언제 무엇을 바꿨는지 추적 가능.
- 백업의 진화된 형태 — 시간순 변경 이력 + 의미있는 메시지.
- 단계별 복원 가능 (`git revert`).

**단점**:
- **시크릿 노출 위험**: `.env` 변경 시 commit 되면 git 히스토리에 토큰/API 키 영구 기록. 단 `.env` 가 `.gitignore` 에 있으므로 자동 제외 (확인 필요).
- 신규 캐릭터 추가 시 `.env` 라인 자동 추가 (§9.7) → `.env` 자체는 .gitignore이지만 .env.example 갱신 시도 시 고민.
- 중요한 변경/사소한 변경 구분이 안 됨 — git 히스토리가 매우 verbose 해짐.
- 사용자가 매 저장마다 commit 메시지를 직접 쓸 수 없음 (자동 생성).
- v1 운영자는 PM 본인 (단일 admin) — git audit 의 가치가 낮을 수도.

**대안**: `platform.sqlite` 의 `change_log` 테이블에 audit 기록 (이미 plan에 포함). git commit 보다 가볍고 시크릿 안전.

**옵션**:
| 옵션 | 동작 |
|---|---|
| **A. v1 미도입 (권장)** | SQLite audit 만. v2에서 운영 경험 후 결정. |
| **B. v1 도입** | `.env` 만 .gitignore 보호 한 채로 매 저장마다 자동 commit. |
| **C. 수동 commit** | UI 에 "현재 변경 내용을 git commit" 버튼 — 사용자가 명시적 클릭 시만. |

**A 권장 이유**: 단일 admin / 백업 + audit table 로 충분 / 시크릿 위험 감소 / git 히스토리 노이즈 회피.

→ **PM 답변 요청**: A / B / C 중 어느 옵션?

### 9.7 LLM 백엔드 변수 노출 — ✅ 결정 완료 (PM: A 현재 v2 — `.env` 페이지 + Connections 페이지 둘 다에서 편집 가능)
**상태**: v2 plan §4.8 Connections 페이지에서 OpenWebUI URL + token 편집 가능 + ping 검증 — 이미 결정 완료.

**PM이 다시 질문한 이유 추정**: v1 plan 의 권장안 ("read-only 표시") 보고 답한 듯. v2에서 무효.

**현재 plan v2 동작**:
- `.env` 편집기 (§4.1): `OPENWEBUI_URL`, `OPENWEBUI_API_KEY`, `MODEL_NAME`, `LLM_API_PATH` — **편집 가능**.
- Connections 페이지 (§4.8): OpenWebUI/Gemma 카드에서 동일 변수 편집 + Ping 버튼.
- 두 페이지가 같은 .env 파일을 source-of-truth 로 공유.

**옵션**:
| 옵션 | 동작 |
|---|---|
| **A. 현재 v2 (권장)** | 편집 가능 + Connections 에서 ping. 양쪽 페이지에서 동일 데이터 편집. |
| **B. 일부 read-only** | `.env` 페이지에선 LLM 백엔드 변수 read-only, Connections 페이지에서만 편집 가능. (역할 분리) |
| **C. 완전 read-only** | 어디서도 편집 불가 (PM 직접 .env 파일 편집). v1의 원래 권장안. |

**A 권장 이유**: PM이 명시한 "URL과 token 저장, ping test" 요구를 그대로 충족. 단순.

→ **PM 답변 요청**: A / B / C 중 어느 옵션?

### 9.8 신규 캐릭터 시 .env 자동 라인 추가 — ✅ 결정 완료
- **PM**: 자동 추가 (빈 값) + UI 에서 토큰 입력 prompt

### 9.9 비디오 모델 카탈로그 (PM 결정 반영) — ✅ 결정 완료, 명세 갱신 필요
- **PM**: Atlas Cloud 에 있는 모델이라면 사용자가 추가할 수 있어야 함. 카탈로그 + dropdown.

**구현 명세**:
- 신규 config 파일: `config/video_models.json`
  ```json
  {
    "models": [
      {"id": "alibaba/wan-2.6/image-to-video-flash", "label": "Wan 2.6 Flash (default)", "native_audio": true, "default": true},
      {"id": "alibaba/wan-2.6/image-to-video", "label": "Wan 2.6 (standard)", "native_audio": true},
      {"id": "alibaba/wan-2.7/image-to-video", "label": "Wan 2.7", "native_audio": true}
    ]
  }
  ```
- UI: `.env` 편집기 또는 별도 "Video" 페이지에서 모델 dropdown + "+ Add Model" 버튼 → user 가 모델 ID 입력 → 카탈로그에 추가
- `VIDEO_MODEL` .env 변수는 dropdown 선택 결과로 갱신 (자유 입력 안 됨 — 카탈로그 안에서만 선택)
- 봇 코드 `src/video.py:_NATIVE_AUDIO_MODELS`, `_KNOWN_MODELS` 가 이 JSON 을 읽도록 한 줄 수정 (별도 PR)
- v1 검증: 모델 ID 형식 체크 (`vendor/model/variant`) + Atlas Cloud `/models` API 로 실제 존재 여부 확인 (옵션)

### 9.10 Grok base URL 변수
- 현재: `src/grok.py` 가 X.AI 엔드포인트 하드코드 가능성. Connections 페이지에서 URL 편집을 지원하려면 변수가 필요.
- **권장**: `GROK_BASE_URL` (기본값 `https://api.x.ai/v1`) 신규 추가 → `src/grok.py` 가 이를 읽도록 한 줄 수정 (별도 PR).
- 대안: Connections 페이지에서 Grok URL 은 표시만 (편집 불가). v1 미도입.

### 9.11 Prompt Guard 토큰 / health 엔드포인트
- 현재: `src/input_filter.py` 의 `check_prompt_guard()` 가 토큰 미사용. health 엔드포인트 미확인.
- **권장**: v1 무토큰 (현재대로). Ping 검증은 `POST /check` 더미 텍스트로 fallback.
- 대안: 토큰 추가 — Prompt Guard 서버에 인증 추가 시 (현재 .env 에 미존재).

---

## 10. 참고

### SillyTavern 차용 / 비차용
- 차용: Character Card 형식, World Info 의 키워드 트리거 컨셉(M6+ 후보), Quick Reply 미리보기
- 비차용: chat UI, LLM 직접 호출, 모델 라우팅, plugin marketplace

### 봇 운영 컨텍스트 (CLAUDE.md 발췌)
- 봇 entry: `python -m src.bot` / `bot.py:202` `asyncio.run(main())`
- 봇 토큰: `ENV` 접두사 매핑 (`TEST_` / `PROD_`) — `bot.py:23-25`
- Graceful shutdown: SIGINT/SIGTERM → cleanup → exit (`bot.py:168-198`)
- 봇은 config 핫 리로드 X — 모든 변경 후 재시작 필요

---

## PM Sign-off 체크리스트

v1 에서 결정 완료된 항목 (재확인 X):
- ✅ Next.js 풀스택 (TypeScript)
- ✅ `platform/` 서브디렉터리
- ✅ subprocess 봇 제어 (Node `child_process`)
- ✅ 파일 source-of-truth + SQLite audit log

결정 완료 (PM):
- [x] **§9.1** 캐릭터 편집 UX — Form+Raw 둘 다
- [x] **§9.2** ComfyUI 워크플로우 — 활성 메커니즘 미도입, JSON viewer 편집 + 같은 이름 교체 + placeholder 검증 + LoRA 빈칸 (즉시 처리 완료)
- [x] **§9.4** 인증 — 127.0.0.1 only 무토큰
- [x] **§9.7** 신규 캐릭터 .env 자동 라인 — 자동 추가
- [x] **§9.9** 비디오 모델 카탈로그 — `config/video_models.json` + dropdown + 사용자 추가 가능

결정 완료 (PM):
- [x] **§9.3** 봇 자동 롤백 — B (Manual prompt)
- [x] **§9.5** 백업 회전 — A (무제한 v1)
- [x] **§9.6** git 자동 commit — A (v1 미도입)
- [x] **§9.7** LLM 백엔드 변수 노출 — A (`.env` + Connections 둘 다 편집 가능)

추가 (M0 진행 중 / 별도 PR 시 결정 — 현재 권장 default):
- [ ] **§9.10** `GROK_BASE_URL` 신규 변수 — v1 도입 (권장) / 미도입
- [ ] **§9.11** Prompt Guard 토큰 — v1 무토큰 (권장) / 토큰 추가

**전체 핵심 결정 항목 9건 모두 closed. M0 시작 가능.**

확인 필요:
- [ ] `src/comfyui.py` 워크플로우 로딩 코드 — M5 시작 전 한 번 확인 (별도 PR 영향 범위)
- [ ] 마일스톤 일정 (총 9–11일) 동의

사인오프 → M0 시작.
