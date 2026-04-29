# STATUS — ella-chat-publish

> 작업 진행 상황 실시간 트래커. 매 의미있는 단계마다 갱신.
> 자세한 결정 사항·아키텍처는 [CLAUDE.md](CLAUDE.md) / [plan.md](plan.md) / [NSFW_INVENTORY.md](NSFW_INVENTORY.md) 참고.

**마지막 갱신**: 2026-04-27 (Platform M0 구현 + 9 시나리오 통과 / develop 머지 대기)

---

## 현재 상태

- **브랜치**: `feat/feature_M0_admin_skeleton`
- **다음 작업**: Platform M1 — `.env` 편집기 + Connections 페이지 (4개 endpoint ping)
- **진행 중**: M0 develop 머지 대기 (테스트 9 시나리오 모두 통과)
- **블로커**: 없음

---

## 완료 (역순)

| 일자 | 단계 | 브랜치 | 머지 커밋 | 핵심 |
|---|---|---|---|---|
| 2026-04-27 | Platform M0 — Admin 골격 | `feat/feature_M0_admin_skeleton` | (develop 대기) | Next.js 14 scaffold + sidebar + bot-process.ts + 5 API routes + Dashboard UI (status card + log tail). 9 시나리오 모두 PASS |
| 2026-04-27 | Plan v2 + 정책 셋업 | main 직접 | `b11108e` 외 | Next.js 풀스택 plan 확정, git workflow 정책 추가, STATUS.md 시작 |
| 2026-04-27 | LoRA 슬롯 제거 | main 직접 | `271f2d5` | 3개 ComfyUI 워크플로우 LoRA 14개 슬롯 모두 제거 (archived 의 NSFW LoRA 9개 포함) |
| 2026-04-27 | Lighting purge | main 직접 | `af6a3f0` | 이미지 배경 green leak 수정 (lighting 태그 ABSOLUTE 금지) + LLM `<\|channel\|>` 토큰 sanitizer |
| 2026-04-27 | Phase 6 — Env + 결제 제거 | main 직접 | `4eb3068` | 운영 secrets 채움 + Telegram Stars/tier/payment 코드 일괄 삭제 (-979 라인) |
| 2026-04-27 | char09 추가 | main 직접 | `8e3423a` | 오하늘 (수줍은 꽃집 점원, 짝사랑) |
| 2026-04-27 | Phase 3-5 | main 직접 | `cf12855` | Denylist + SFW 캐릭터 카드 8명 + docs SFW 갱신 |
| 2026-04-27 | Phase 2D | main 직접 | `f9e83cf` | 최종 NSFW 잔재 정리 (audiogen-workflow.json 삭제) |
| 2026-04-27 | Phase 2C | main 직접 | `efa9bf8` | Cross-agent integration 수정 + config 잔존 + 서브 CLAUDE.md |
| 2026-04-27 | Phase 2B | main 직접 | `69f98a4` | 핸들러 레이어 재작성 + 잔존 정리 |
| 2026-04-27 | Phase 2A | main 직접 | `16ced9b` | 독립 모듈 재작성 (history, trait_pools, video, comfyui, grok 외부화) |
| 2026-04-27 | Phase 1 | main 직접 | `b607910` | fork 골격 (디렉터리 / verbatim 복사 / 시스템드 unit rename) |

> 이전 phase 들은 main 에 직접 commit 됨 — 정책(브랜치 전략) 도입 이전.

---

## M0 머지 체크리스트 (develop ← feat/feature_M0_admin_skeleton)

- [x] 9 시나리오 수동 테스트 PASS (cold start / start / stop / restart / logs / stale-PID self-heal / double-start 409 / 127.0.0.1 binding / Next.js kill 후 봇 생존)
- [x] `npx tsc --noEmit` — 0 에러
- [x] `platform/CLAUDE.md` 신규 작성
- [x] STATUS.md 갱신 (본 commit)
- [ ] develop 머지 후 platform/CLAUDE.md 의 "현재 마일스톤" 표 그대로 유지 (M1 시작 시 갱신)

---

## 다음 단계 — Platform M1 (`.env` 편집기 + Connections)

### Plan
[plan.md §8 M1](plan.md). M1 시작 시 별도 feature plan MD 를 `docs/features/M1_env_connections.md` 에 작성.

### 브랜치 흐름
```
develop
  └ feat/feature_M1_env_connections
```

### Deliverable (요약)
- `.env` 편집기 — 라인 보존 파서, 카테고리 tabs, 시크릿 마스킹
- Connections 페이지 — ComfyUI / OpenWebUI / Grok / Prompt Guard ping
- `platform.sqlite` `connection_check` 테이블
- Dashboard 에 "Connections health" 요약 카드

### 일정 (예상)
- 2–2.5일

---

## 결정 대기 (PM 답변 받으면 진행)

### M1 시작 시 확인할 항목
- [ ] M1 착수 신호 / 우선순위 (현재는 "M0 머지 후 M1 진행" 가정)
- [ ] `platform.sqlite` 위치 — `platform/data/platform.sqlite` (gitignore) 가정으로 진행해도 OK?

### 별도 PR 후보 (M1+ 진행 중 결정 가능)
- [ ] `GROK_BASE_URL` env 변수 추가 + `src/grok.py` 한 줄 수정 (Connections 페이지 Grok URL 편집 지원)
- [ ] `config/video_models.json` 신규 + `src/video.py` 한 줄 수정 (비디오 모델 카탈로그 + dropdown — plan §9.9)
- [ ] Prompt Guard 토큰 추가 (서버에 인증 도입 시)

---

## 폴더별 CLAUDE.md 상태

main 머지 시 갱신 의무. 현재 상태:

| 폴더 | CLAUDE.md | 비고 |
|---|---|---|
| (root) | ✅ | 본 STATUS 와 함께 갱신 |
| `src/` | ✅ | Phase 2C C9 작성, 이후 Phase 2D 변경 반영 필요 (다음 main 머지 시) |
| `config/` | ✅ | Phase 2C C9 작성 |
| `deploy/` | ✅ | Phase 2C C9 작성 |
| `comfyui_workflow/` | ✅ | Phase 2C C9 작성, audiogen-workflow.json drop 반영됨 (Phase 2D D3) |
| `behaviors/` | ✅ | 9 SFW 캐릭터 카드 안내 (정책 셋업 commit 에서 작성) |
| `persona/` | ✅ | 동일 |
| `images/` | ✅ | 동일 |
| `docs/` | ✅ | 동일 |
| `scripts/` | ✅ | 현재 비어있음 (`.gitkeep` 만) |
| `tools/` | ✅ | 동일 |
| `jobs/` | ❌ | (비어있음 — 미작성 OK) |
| `world_info/` | ❌ | (비어있음 — 미작성 OK) |
| `platform/` | ✅ | M0 에서 신규 작성 |

---

## 갱신 규약

- **이 파일은 매 의미있는 단계 완료마다 갱신.**
- "진행 중" → "완료" 이동 시 머지 커밋 해시 기록.
- 결정 대기 항목은 PM 답변 후 즉시 제거.
- 마지막 갱신 시각/날짜를 상단에 명시.
- `develop` 머지 시 STATUS.md 갱신 commit 동반.
- `main` 머지 시 STATUS.md + 모든 CLAUDE.md 갱신 commit 동반 (CLAUDE.md 워크플로우 섹션 참고).
