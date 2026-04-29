# STATUS — ella-chat-publish

> 작업 진행 상황 실시간 트래커. 매 의미있는 단계마다 갱신.
> 자세한 결정 사항·아키텍처는 [CLAUDE.md](CLAUDE.md) / [plan.md](plan.md) / [NSFW_INVENTORY.md](NSFW_INVENTORY.md) 참고.

**마지막 갱신**: 2026-04-28 (M1 + 전면 영어화 + char05 단일 캐릭터 / develop 머지 대기)

---

## 현재 상태

- **브랜치**: `feat/feature_M1_env_connections`
- **다음 작업**: Platform M2 — Prompt 편집기 (Monaco + diff viewer)
- **진행 중**: M1 + i18n develop 머지 대기 (전 phase 영어화 + char05 만 sample 캐릭터로)
- **블로커**: 없음

---

## 완료 (역순)

| 일자 | 단계 | 브랜치 | 머지 커밋 | 핵심 |
|---|---|---|---|---|
| 2026-04-28 | i18n full English + char05 sample | `feat/feature_M1_env_connections` | (develop 대기) | scope D 영어화 (markdown 제외): .env.example, platform/, src/* (논-handler+handlers), config/, char05 만 남기고 영어화 (char01-04 + char06-09 삭제). docs cleanup (terms_of_service / video-improve1 drop). |
| 2026-04-28 | Platform M1 — env editor + Connections | `feat/feature_M1_env_connections` | (develop 대기) | /env 카테고리 tabs + 시크릿 마스킹 + 자동 백업 + restart toast / /connections 4 endpoint Ping + SQLite 기록 + Dashboard health card / GROK_BASE_URL pre-req + Grok 모델 override 5종 노출. 12 시나리오 PASS. |
| 2026-04-27 | Platform M0 — Admin 골격 | `feat/feature_M0_admin_skeleton` | `7804ea1` | Next.js 14 scaffold + sidebar + bot-process.ts + 5 API routes + Dashboard UI. 9 시나리오 모두 PASS. |
| 2026-04-27 | Plan v2 + 정책 셋업 | main 직접 | `b11108e` 외 | Next.js 풀스택 plan 확정, git workflow 정책 추가, STATUS.md 시작 |
| 2026-04-27 | LoRA 슬롯 제거 | main 직접 | `271f2d5` | 3개 ComfyUI 워크플로우 LoRA 14개 슬롯 모두 제거 (archived 의 NSFW LoRA 9개 포함) |
| 2026-04-27 | Lighting purge | main 직접 | `af6a3f0` | 이미지 배경 green leak 수정 (lighting 태그 ABSOLUTE 금지) + LLM `<\|channel\|>` 토큰 sanitizer |
| 2026-04-27 | Phase 6 — Env + 결제 제거 | main 직접 | `4eb3068` | 운영 secrets 채움 + Telegram Stars/tier/payment 코드 일괄 삭제 (-979 라인) |
| 2026-04-27 | char09 추가 | main 직접 | `8e3423a` | (이후 i18n 단계에서 삭제됨) |
| 2026-04-27 | Phase 3-5 | main 직접 | `cf12855` | Denylist + SFW 캐릭터 카드 8명 (이후 i18n 에서 char05 만 잔류) + docs SFW 갱신 |
| 2026-04-27 | Phase 2D | main 직접 | `f9e83cf` | 최종 NSFW 잔재 정리 |
| 2026-04-27 | Phase 2C | main 직접 | `efa9bf8` | Cross-agent integration 수정 + config 잔존 + 서브 CLAUDE.md |
| 2026-04-27 | Phase 2B | main 직접 | `69f98a4` | 핸들러 레이어 재작성 + 잔존 정리 |
| 2026-04-27 | Phase 2A | main 직접 | `16ced9b` | 독립 모듈 재작성 (history, trait_pools, video, comfyui, grok 외부화) |
| 2026-04-27 | Phase 1 | main 직접 | `b607910` | fork 골격 |

---

## M1 + i18n 머지 체크리스트 (develop ← feat/feature_M1_env_connections)

- [x] M1 12 시나리오 (수동 테스트) PASS
- [x] i18n: grep '[가-힣]' platform/ → 0 matches
- [x] i18n: grep '[가-힣]' src/handlers_*.py / persona / behaviors / images → 0 matches
- [x] i18n: grep '[가-힣]' config/*.json → 0 matches
- [x] python -c 'from src import bot' → OK (모든 모듈 import 정상)
- [x] npx tsc --noEmit (platform/) → 0 errors
- [x] char list: 1 sample (char05 — Jiwon Han) + imagegen
- [ ] platform/CLAUDE.md / 루트 CLAUDE.md / STATUS.md (본 commit) 갱신

---

## 다음 단계 — Platform M2 (Prompt 편집기)

### Plan
[plan.md §8 M2](plan.md). M2 시작 시 별도 feature plan MD 를 `docs/features/M2_prompt_editor.md` 에 작성.

### 브랜치 흐름
```
develop
  └ feat/feature_M2_prompt_editor
```

### Deliverable (요약)
- `/prompts` 페이지 — Monaco editor
- `config/grok_prompts.json` 5 키 + `config/system_prompt.json` 2 키 편집
- JSON parse / 빈 값 검증 / `${var}` placeholder lint
- Diff viewer (`react-diff-viewer-continued`)

### 일정 (예상)
- 1일

---

## 결정 대기 (PM 답변 받으면 진행)

### M2 시작 시 확인할 항목
- [ ] M2 착수 신호
- [ ] `/prompts` 에디터 JSON 정합성 검증 — 빈 키 / placeholder mismatch 거부 정책 확인 (plan §4.3 따라 진행 default)

### 별도 PR 후보
- [ ] `config/video_models.json` 신규 + `src/video.py` 한 줄 수정 (비디오 모델 카탈로그 + dropdown — plan §9.9)
- [ ] Prompt Guard 토큰 추가 (서버에 인증 도입 시)

---

## 폴더별 CLAUDE.md 상태

main 머지 시 갱신 의무. 현재 상태:

| 폴더 | CLAUDE.md | 비고 |
|---|---|---|
| (root) | ✅ | 본 STATUS 와 함께 갱신 |
| `src/` | ✅ | i18n 단계에서 모듈 파일 갱신 — 다음 main 머지 때 CLAUDE.md 도 갱신 권장 |
| `config/` | ✅ | i18n 단계에서 grok_prompts / system_prompt / sfw_scenes / sfw_denylist 영어화 반영 필요 |
| `deploy/` | ✅ | 변경 없음 |
| `comfyui_workflow/` | ✅ | 변경 없음 |
| `behaviors/` | ✅ | 본 commit 에서 char list 갱신 (char05 단일) |
| `persona/` | ✅ | 동일 |
| `images/` | ✅ | 동일 |
| `docs/` | ✅ | terms_of_service / video-improve1 drop 반영 |
| `scripts/` | ✅ | 변경 없음 |
| `tools/` | ✅ | 변경 없음 |
| `jobs/` | ❌ | (비어있음 — 미작성 OK) |
| `world_info/` | ❌ | (비어있음 — 미작성 OK) |
| `platform/` | ✅ | 본 commit 에서 M1 (env / connections / db / ping) 반영 |

---

## 갱신 규약

- **이 파일은 매 의미있는 단계 완료마다 갱신.**
- "진행 중" → "완료" 이동 시 머지 커밋 해시 기록.
- 결정 대기 항목은 PM 답변 후 즉시 제거.
- 마지막 갱신 시각/날짜를 상단에 명시.
- `develop` 머지 시 STATUS.md 갱신 commit 동반.
- `main` 머지 시 STATUS.md + 모든 CLAUDE.md 갱신 commit 동반 (CLAUDE.md 워크플로우 섹션 참고).
