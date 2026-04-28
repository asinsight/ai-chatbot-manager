# STATUS — ella-chat-publish

> 작업 진행 상황 실시간 트래커. 매 의미있는 단계마다 갱신.
> 자세한 결정 사항·아키텍처는 [CLAUDE.md](CLAUDE.md) / [plan.md](plan.md) / [NSFW_INVENTORY.md](NSFW_INVENTORY.md) 참고.

**마지막 갱신**: 2026-04-27 (정책 셋업 + main 안정)

---

## 현재 상태

- **브랜치**: `main` (안정)
- **다음 작업**: Platform M0 — Admin 웹앱 골격 (Next.js 풀스택)
- **진행 중**: 없음 (M0 시작 신호 대기)
- **블로커**: 없음

---

## 완료 (역순)

| 일자 | 단계 | 브랜치 | 머지 커밋 | 핵심 |
|---|---|---|---|---|
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

## 다음 단계 — Platform M0 (Next.js admin 웹앱 골격)

### Plan
[plan.md §8 M0](plan.md) 참고. 본 마일스톤 시작 시 별도 feature plan MD 를 `docs/features/M0_admin_skeleton.md` 에 작성.

### 브랜치 흐름
```
main
  └ develop (M0 부터 도입)
      └ feat/feature_M0_admin_skeleton
```

### Deliverable (요약)
- `platform/` Next.js 프로젝트 초기화 (`create-next-app` + TypeScript + Tailwind)
- shadcn/ui 컴포넌트 설치 + 기본 layout (Sidebar + Header + Main)
- Dashboard 페이지: 봇 status 카드 + Start/Stop/Restart 버튼 + uptime + bot count
- `lib/bot-process.ts` (Node `child_process.spawn` + PID file 추적)
- `app/api/bot/{status,start,stop,restart}/route.ts`
- 로그 tail (M5 까지는 polling — `GET /api/bot/logs?tail=500`)
- 첫 commit: `chore: scaffold platform/ Next.js app`

### 테스트 시나리오
- `cd platform && npm run dev` → http://127.0.0.1:9000
- Start 버튼 → 봇 PID 표시 → 텔레그램 봇 응답 확인
- Stop 버튼 → 봇 종료
- Restart 버튼 → 5초 안에 재기동
- 봇 stdout/stderr 가 `logs/bot.log` 에 누적

### 일정 (예상)
- 1.5–2일

---

## 결정 대기 (PM 답변 받으면 진행)

### M0 시작 시 확인할 항목
- [ ] 현재 텔레그램 봇 (PID 92612) 처리 — admin 에서 띄울지, 그대로 두고 admin 따로 시도할지
- [ ] M0 시작 신호

### 별도 PR 후보 (M0 진행 중 결정 가능)
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
| `behaviors/` | ❌ | 작성 필요 — SFW 캐릭터 카드 8개 (char01-char09) |
| `persona/` | ❌ | 작성 필요 — 동일 |
| `images/` | ❌ | 작성 필요 — 동일 |
| `docs/` | ❌ | 작성 필요 — 4개 문서 안내 |
| `scripts/` | ❌ | 작성 필요 — 현재 비어있음 (`.gitkeep` 만) |
| `tools/` | ❌ | 작성 필요 — 현재 비어있음 (`.gitkeep` 만) |
| `jobs/` | ❌ | (비어있음 — 미작성 OK) |
| `world_info/` | ❌ | (비어있음 — 미작성 OK) |
| `platform/` | — | M0 에서 신설 시 함께 추가 |

---

## 갱신 규약

- **이 파일은 매 의미있는 단계 완료마다 갱신.**
- "진행 중" → "완료" 이동 시 머지 커밋 해시 기록.
- 결정 대기 항목은 PM 답변 후 즉시 제거.
- 마지막 갱신 시각/날짜를 상단에 명시.
- `develop` 머지 시 STATUS.md 갱신 commit 동반.
- `main` 머지 시 STATUS.md + 모든 CLAUDE.md 갱신 commit 동반 (CLAUDE.md 워크플로우 섹션 참고).
