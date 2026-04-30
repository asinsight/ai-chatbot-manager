# M1 — `.env` 편집기 + Connections 페이지

> **브랜치**: `feat/feature_M1_env_connections`
> **상태**: Plan only — PM 사인오프 후 구현 시작.
> **상위 plan**: [plan.md §4.1](../../plan.md), [plan.md §4.8](../../plan.md), [plan.md §8 M1](../../plan.md)
> **예상 소요**: 2–2.5일

---

## 1. 목표 (M1 Scope)

### Done 조건
1. `/env` 페이지에서 루트 `.env` 모든 변수를 카테고리별 form 으로 편집·저장 (LLM 백엔드 4종 포함, `VIDEO_MODEL` 만 read-only).
2. `/connections` 페이지에서 4 endpoint (ComfyUI / OpenWebUI / Grok / Prompt Guard) 의 URL+token 편집 + Ping 검증.
3. **저장 시 자동 백업** — `platform/data/backups/.env.<YYYYMMDD-HHMMSS>.bak` (무제한 v1).
4. **Ping 결과 SQLite 기록** — `platform/data/platform.sqlite` `connection_check` 테이블에 timestamp + 결과 누적.
5. Dashboard 에 "Connections health" 요약 카드 — 4/4 🟢 또는 N fail 표시.
6. 시크릿 마스킹 — `*_API_KEY` / `*_BOT_TOKEN` / `*_API_TOKEN` 패턴은 `••••••<last4>` + 👁 reveal 토글.
7. 저장 후 toast: "재시작 필요 — Dashboard 에서 Restart 클릭" + Restart 단축 링크.

### Out-of-scope (M1 에서 안 함)
- Prompt 편집 (M2).
- 캐릭터 카드 CRUD (M3).
- 이미지 config / 워크플로우 (M4-M5).
- 봇 자동 재시작 / 자동 롤백 (★ #9.3 Manual prompt 만 표시).
- 백업 회전 (★ #9.5 — v1 무제한, v2 에서 30일).
- 외부 노출 / 인증 (★ #9.4 — 127.0.0.1 only 무토큰).

---

## 2. ★ PM 결정 필요 (시작 전 답변)

### #1 — Grok base URL 변수 신설 여부 (plan §9.10)
- **현재 상태**: `src/grok.py` 가 `base_url="https://api.x.ai/v1"` 를 4곳에 하드코드 (line 376, 472, 등). `.env` 에 변수 없음.
- **A**: 신설 X — Connections 페이지의 Grok 카드는 URL **읽기 전용** (X.AI 고정), token 만 편집.
- **B (권장)**: `GROK_BASE_URL` 변수 추가 (기본값 `https://api.x.ai/v1`) + `src/grok.py` 4곳을 `os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")` 로 교체. **별도 파이썬 PR**(`feat: GROK_BASE_URL env var`)을 M1 진행 중 동시에 진행.
- **선택지가 답에 영향**: A 면 Connections 페이지 Grok 카드의 URL input 비활성화. B 면 모두 편집 가능.

### #2 — Prompt Guard 카드 노출 (plan §9.11)
- **현재 상태**: `PROMPT_GUARD_URL` 은 `src/input_filter.py` 에서 `os.getenv("PROMPT_GUARD_URL", "")` 로 읽음 — 비어있으면 remote 호출 스킵 (regex 필터만 동작). 사설 IP fallback 은 오픈소스 정리 단계에서 제거됨. 토큰 인증 X.
- **A**: 보임 — `.env` 에 `PROMPT_GUARD_URL` 변수 line 추가 (현재 미존재) + Connections 카드 노출. Ping 은 `POST {URL}/check` 더미 텍스트로.
- **B**: 숨김 — Prompt Guard 는 v1 미노출, M1 Connections 페이지에 3개 카드 (ComfyUI / OpenWebUI / Grok) 만.
- **권장**: A. `.env.example` 에도 `#PROMPT_GUARD_URL=` 추가.

### #3 — `platform.sqlite` / 백업 위치
- **권장**: `platform/data/platform.sqlite` + `platform/data/backups/`. `platform/.gitignore` 에 `data/` 추가.
- 이 결정은 plan §5 와 일치하므로 사실상 확인용. **이의 없으면 권장으로 진행**.

### #4 — `npm install better-sqlite3` 추가
- **이슈**: `better-sqlite3` 는 native binding (node-gyp) 필요. M1 시작 시 `npm install` 한 번 더 돌려야 하고, 사용자 머신(macOS arm64) 에서 prebuilt 가 있어야 함.
- **확인 필요**: `npm install better-sqlite3` 시 prebuilt 다운로드 성공 여부. 실패하면 build tool 필요.
- **답변 불필요시 진행**: 권장은 추가 후 install 시도, 실패 시 보고.

---

## 3. 디렉터리 구조 (M1 추가분)

```
platform/
├── app/
│   ├── env/
│   │   ├── page.tsx                # ★ M1 — 카테고리 tabs + form
│   │   └── env-form.tsx            # client component
│   ├── connections/
│   │   ├── page.tsx                # ★ M1 — 4 endpoint 카드
│   │   └── connection-card.tsx     # client component
│   └── api/
│       ├── env/
│       │   └── route.ts            # GET / PUT
│       └── connections/
│           ├── route.ts            # GET 전체 + 마지막 ping
│           ├── [id]/route.ts       # PUT URL/token
│           ├── [id]/ping/route.ts  # POST 즉시 ping
│           └── ping-all/route.ts   # POST 4개 동시 ping
├── components/
│   ├── connections-health-card.tsx # Dashboard 통합용
│   └── ui/
│       ├── input.tsx               # ★ M1 — shadcn primitive
│       ├── label.tsx               # ★ M1
│       ├── tabs.tsx                # ★ M1 (Radix Tabs 래핑)
│       └── toast.tsx               # ★ M1 (sonner 또는 shadcn toaster)
├── lib/
│   ├── env-parser.ts               # ★ M1 — 라인 보존 파서
│   ├── env-categories.ts           # ★ M1 — 변수 → 카테고리 매핑 + 도움말
│   ├── secrets.ts                  # ★ M1 — 마스킹 패턴
│   ├── backup.ts                   # ★ M1 — .env 백업
│   ├── db.ts                       # ★ M1 — better-sqlite3 + 마이그레이션
│   └── ping.ts                     # ★ M1 — 4 endpoint ping 로직
└── data/                           # ★ M1 — gitignore
    ├── platform.sqlite
    └── backups/
```

추가 npm 의존성:
- `better-sqlite3` (native, 단일 파일 SQLite)
- `@radix-ui/react-tabs` (shadcn Tabs)
- `@radix-ui/react-label` (shadcn Label)
- `sonner` (toast — shadcn 권장 stack)

---

## 4. `lib/env-parser.ts` 설계

**책임**: 루트 `.env` 를 라인 단위로 파싱 → 객체 배열로 변환 → 변경 후 같은 라인 순서/주석/빈 줄/quoting 을 보존하며 직렬화.

### 자료형
```ts
type EnvLine =
  | { kind: "blank" }
  | { kind: "comment"; raw: string }
  | { kind: "var"; key: string; value: string; rawComment?: string; quoted?: '"' | "'" | null }
  | { kind: "comment-var"; key: string; value: string; raw: string };

export function parseEnv(text: string): EnvLine[];
export function serializeEnv(lines: EnvLine[]): string;
export function applyUpdates(lines: EnvLine[], updates: Record<string, string>): EnvLine[];
```

### 동작
- 공백/주석 라인은 그대로 보존.
- `KEY=VAL` / `KEY="VAL with spaces"` / `KEY='...'` 모두 인식.
- `applyUpdates({ KEY: "newval" })` 가:
  - 기존 var 라인 → value 만 교체 (quoting 유지).
  - 기존 commented-out 라인 (`#KEY=...`) → uncomment + value 교체.
  - 키가 없으면 → 파일 끝에 `KEY=val` append (M1 기본; 카테고리별 group append 는 v2).
- 새 quoting 결정: value 에 공백/`#` 있으면 `"` 로 감싸기.

### 검증
- 키 형식: `^[A-Z_][A-Z0-9_]*$` 위반 시 reject.
- value 안의 newline 거부.
- LLM 백엔드 4 var 와 `VIDEO_MODEL` 같은 read-only 키는 PUT 핸들러에서 차단 — 파서 자체는 변경 가능 (UI 가 readOnly 플래그로 제어).

---

## 5. `lib/env-categories.ts`

`.env.example` 의 섹션 헤더 블록을 정적으로 모방 — 코드에서 카테고리 매핑을 명시. M1 에서는 동적 파싱 X (단순화).

```ts
export const CATEGORIES: { id: string; label: string; help?: string; keys: string[] }[] = [
  { id: "llm", label: "LLM 백엔드", keys: ["OPENWEBUI_URL","OPENWEBUI_API_KEY","LLM_API_PATH","MODEL_NAME"] },
  { id: "grok", label: "Grok", keys: ["GROK_API_KEY","GROK_MODEL_NAME","GROK_BASE_URL"] },
  { id: "comfyui", label: "ComfyUI", keys: ["COMFYUI_URL","COMFYUI_MAX_QUEUE","COMFYUI_STUCK_TIMEOUT","COMFYUI_VRAM_MIN_MB"] },
  { id: "video", label: "비디오 (Atlas Cloud)", keys: ["ATLASCLOUD_API_KEY","VIDEO_MODEL"] },
  { id: "prompt_guard", label: "Prompt Guard", keys: ["PROMPT_GUARD_URL","PROMPT_GUARD_THRESHOLD","PROMPT_GUARD_TIMEOUT"] },
  { id: "operations", label: "운영", keys: ["IMAGE_AUTONOMY","FORCE_SFW_SCENE","ENV","ADMIN_USER_IDS","ADMIN_NOTIFY","LOG_LEVEL","SUMMARY_THRESHOLD","RECENT_MESSAGES_KEEP","LLM_MAX_CONCURRENT","LLM_MAX_QUEUE_SIZE","LLM_QUEUE_TIMEOUT"] },
  { id: "tokens", label: "봇 토큰 (Test/Prod)", keys: [] },
  { id: "platform", label: "Admin webapp", keys: ["PYTHON_BIN"] },
];
```

- `keys: []` 인 `tokens` 카테고리는 동적으로 모든 매칭 키를 모음.
- 어느 카테고리에도 안 잡힌 키는 "기타" 탭 자동 생성.
- `editable=false` 키 (예: `VIDEO_MODEL`): UI input 비활성화 + 잠금 아이콘.
- 인라인 도움말: `.env.example` 에서 키 바로 위 주석 라인을 추출 (env-parser 가 같이 반환).

---

## 6. `lib/secrets.ts`

```ts
const SECRET_PATTERNS = [/_API_KEY$/, /_BOT_TOKEN$/, /_API_TOKEN$/, /_SECRET$/];
export function isSecret(key: string): boolean { /* ... */ }
export function maskValue(value: string): string {
  if (!value) return "";
  const last4 = value.slice(-4);
  return `••••••${last4}`;
}
```

서버 `GET /api/env` 응답에서는 secret value 를 그대로 반환할지 마스킹할지 결정 필요. **127.0.0.1 only 환경**에서는 응답에 raw value 그대로 반환 + 클라이언트가 `isSecret(key)` 면 토글 전까지 마스킹 표시. 본 M1 는 후자 채택 (단순화).

---

## 7. `lib/backup.ts`

```ts
export async function backupEnv(): Promise<string>;
```

- 위치: `platform/data/backups/.env.<YYYYMMDD-HHMMSS>.bak` (KST 시간 사용).
- 디렉터리 자동 생성.
- 원자적: `fsp.copyFile(.env, tmp)` → `rename(tmp, target)`.
- 무제한 회전 (M5/v2 까지 미정).

---

## 8. `lib/db.ts` (better-sqlite3)

```ts
const db = new Database(path.join(REPO_ROOT, "platform/data/platform.sqlite"));
db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS connection_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    message TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_connection_check_ts ON connection_check (endpoint_id, ts DESC);
`);
```

- `recordPing(endpoint_id, result)` 가 INSERT.
- `getLastPing(endpoint_id)` 가 `SELECT ... ORDER BY ts DESC LIMIT 1`.
- `getRecentPings(endpoint_id, n=20)` — 시계열 표시용 (이번 M1 미사용, 스키마만 준비).

---

## 9. `lib/ping.ts`

각 endpoint 별 ping 함수. 모두 server-side fetch (10s timeout):

```ts
export type PingResult = { ok: boolean; status_code?: number; duration_ms: number; message: string };

async function pingComfyUI(url: string): Promise<PingResult>;
async function pingOpenWebUI(url: string, token?: string): Promise<PingResult>;
async function pingGrok(baseUrl: string, token: string): Promise<PingResult>;
async function pingPromptGuard(url: string): Promise<PingResult>;

export async function pingByEndpointId(id: string): Promise<PingResult>;
export async function pingAll(): Promise<Record<string, PingResult>>;
```

**구현 디테일**:
- URL 정규화: trailing slash 제거.
- ComfyUI `GET /system_stats` → 200 + JSON 파싱 가능 → ok.
- OpenWebUI: token blank 허용 — `Authorization` 헤더는 token 있을 때만.
- Grok: 401 면 "토큰 형식 OK, 권한 부족" → ok=false 지만 status_code=401 → message 에 "credentials rejected" 표시.
- Prompt Guard: `POST /check` body `{"text":"hello","threshold":0.8}` → 200 면 ok.
- Timeout 10s — `AbortController`.

---

## 10. API Routes

### `GET /api/env`
응답:
```json
{
  "categories": [
    { "id": "llm", "label": "LLM 백엔드", "vars": [
      { "key": "OPENWEBUI_URL", "value": "http://...", "comment": "...", "is_secret": false, "editable": true }
    ]}
  ]
}
```

### `PUT /api/env`
```json
{ "updates": { "GROK_API_KEY": "xai-..." } }
```
응답: `{ ok: true, restart_required: true, backup_path: "platform/data/backups/.env.20260428-001234.bak" }`

검증:
- 키마다 `editable` 체크. read-only 키는 422 + `code: "READ_ONLY_KEY"`.
- 미존재 키 (env-categories 에 없는) 는 422 + `code: "UNKNOWN_KEY"` — append 정책은 보수적으로 차단. 단 dynamic 카테고리 (`tokens`) 매칭 시 허용.
- value 안의 newline 거부 → 422 + `code: "INVALID_VALUE"`.

### `GET /api/connections`
```json
{
  "connections": [
    { "id": "comfyui", "label": "ComfyUI", "url_var": "COMFYUI_URL", "token_var": null,
      "url": "http://...", "token_masked": null, "token_blank_allowed": true,
      "last_ping": { "ok": true, "duration_ms": 42, "ts": 1745000000000 }
    }
  ]
}
```

### `PUT /api/connections/[id]`
body `{ url, token }` → 내부적으로 `PUT /api/env` 로 위임.

### `POST /api/connections/[id]/ping`
즉시 ping → SQLite 기록 → `{ ok, status_code, duration_ms, message }`.

### `POST /api/connections/ping-all`
4개 endpoint 동시 ping → 각각 SQLite 기록.

---

## 11. UI

### `/env` — 카테고리 tabs + form
- 변경 dirty state — 저장 전 페이지 이탈 시 confirm.
- 저장 성공 toast: 백업 path + Restart 단축 버튼.
- 저장 실패 — 422 응답 그대로 표시.

### `/connections` — 4 endpoint 카드 + 전체 Ping 버튼
- 카드별 상태: 🟢 OK / 🔴 Fail (status code + 첫 80자 메시지) / ⚪ Untested.
- "Save & Ping" — Save 후 자동으로 Ping 트리거.
- 개별 Ping / 전체 Ping 모두 5–10s 사이 응답.

### Dashboard "Connections health" 카드
- 타이틀 + 4개 dot (🟢/🔴/⚪) — 클릭 → `/connections` 이동.
- 30초 polling (`GET /api/connections` 가 last_ping 만 반환 — 외부 호출 없음).

---

## 12. 테스트 시나리오 (수동)

수동 테스트 — 자동화 X (M1 까지는 vitest 미도입).

1. **`.env` 페이지 — 시크릿 마스킹**: `/env` → Grok 탭 → `GROK_API_KEY` 가 `••••••XXXX` 표시 → 👁 클릭 → 평문 노출 → 다시 클릭 → 마스킹.
2. **`.env` 저장 + 백업**: `IMAGE_AUTONOMY` 를 `2` → `1` 로 변경 → Save → toast 에 backup path 노출 → `ls platform/data/backups/.env.*` 로 파일 확인 → diff 로 변경 확인.
3. **read-only 키 차단**: `VIDEO_MODEL` input 이 disabled. 직접 PUT 호출(`curl -X PUT`)로 변경 시도 → 422 `READ_ONLY_KEY`.
4. **Connections 페이지 Ping (정상)**: ComfyUI 카드 Ping → 🟢 OK + duration. SQLite 에 row 1 추가됨.
5. **Connections Ping (실패)**: GROK_API_KEY 를 `xai-WRONG` 로 변경 → Save → Ping → 🔴 401.
6. **전체 Ping**: 4개 카드 동시 갱신 → 5–10s 안에 마무리.
7. **Prompt Guard URL blank**: PROMPT_GUARD_URL 비우면 (PM #2=A 시) → Ping → 🔴 "URL 필수".
8. **OpenWebUI token blank**: `OPENWEBUI_API_KEY` 비운 채 Ping → llama-cpp-python 경우 200 → 🟢 OK.
9. **재시작 토스트의 "Restart" 링크**: env 저장 후 toast 에서 "Restart" 클릭 → Dashboard 로 이동 후 restart.
10. **백업 무제한**: 5번 연속 저장 → backups/ 에 5개 .bak 누적.
11. **`platform.sqlite` schema 마이그레이션 idempotent**: dev 서버 두 번 시작 후도 에러 없음.
12. **127.0.0.1 only**: LAN 다른 머신에서 `curl http://<ip>:9000/api/env` 거부.

---

## 13. 위험 / 결정 보류

### 위험: better-sqlite3 native build
- `npm install better-sqlite3` 가 prebuilt 다운로드 실패 → node-gyp build 시도 → Xcode CLT 필요할 수 있음.
- **대안 (실패 시)**: Node 22+ 의 `node:sqlite` builtin (Node 24 라 사용 가능) 또는 `bun:sqlite`.

### 위험: Ping 외부 호출이 길어 UI 멈춤
- 10s timeout 지키면 OK. 카드 별로 busy state.

### 결정 보류 (구현 단계 중 PM 컨펌)
- env 저장 시 키 미존재 → append vs reject. 보수적 reject 권장 (오타 방지).
- Connections 카드의 "Save & Ping" 단축 버튼이 Save 실패하면 Ping 도 안 함 (차단).

---

## 14. 커밋 계획

| # | 메시지 | 내용 |
|---|---|---|
| 1 | `chore(platform): add better-sqlite3 + radix-ui tabs/label deps` | package.json + npm install |
| 2 | `feat(platform): env-parser + categories + secrets + backup` | env-parser.ts, env-categories.ts, secrets.ts, backup.ts |
| 3 | `feat(platform): db.ts + connection_check table` | lib/db.ts + 마이그레이션 |
| 4 | `feat(platform): /api/env GET/PUT routes` | app/api/env/route.ts |
| 5 | `feat(platform): /env page + form UI` | app/env/page.tsx + components |
| 6 | `feat(platform): ping.ts + /api/connections routes` | lib/ping.ts + 4 routes |
| 7 | `feat(platform): /connections page + cards` | app/connections/page.tsx |
| 8 | `feat(platform): Dashboard "Connections health" card` | components/connections-health-card.tsx |
| 9 | `docs(M1): platform/CLAUDE.md + STATUS.md + root CLAUDE.md` | develop 머지 직전 |

별도 PR (PM #1 = B 일 경우):
- `feat(grok): GROK_BASE_URL env var` — `src/grok.py` 4곳 + `.env.example` 추가.

---

## 15. develop 머지 체크리스트

- [ ] 모든 테스트 시나리오 (§12) 수동 통과.
- [ ] `npx tsc --noEmit` — 0 에러.
- [ ] `npm run lint` — 경고만, 에러 없음.
- [ ] `STATUS.md` 갱신 (M1 완료 표시 + M2 안내).
- [ ] `platform/CLAUDE.md` "현재 마일스톤" 표 갱신, M1 추가 모듈 (env-parser, db.ts, ping.ts) 기재.
- [ ] 루트 `CLAUDE.md` Implementation Status 표 업데이트.
- [ ] `platform/.gitignore` 에 `data/` 추가.
- [ ] `.env.example` 갱신 (`PROMPT_GUARD_URL`, `GROK_BASE_URL` — PM 결정 반영).
