# Video Improvement #1 — 진행 로그 (Historical, SFW fork)

> **Historical design notes.** 본 문서는 원본 `ella-telegram` 의 video 파이프라인 개선 작업 (`feat/video-improve1` 통합 브랜치) 기록을 SFW fork 관점에서 발췌한 것이다. SFW fork (`ella-chat-publish`) 는 이 작업 이후의 결정에 따라 비디오 파이프라인을 단순화했으므로, 본 문서의 모든 phase 가 fork 코드에 그대로 적용되는 것은 아니다. fork 의 현재 모델은 **Atlas Cloud `alibaba/wan-2.6/image-to-video-flash`** (네이티브 오디오 지원) 단일 모델이며, LoRA / DaSiWa / RunPod fallback / NSFW 분류기 / arousal 게이팅은 모두 제거됐다. 자세한 fork 결정은 `CLAUDE.md` 결정사항 7번 참조.
>
> 아래 phase 들은 다음 관점에서만 fork 와 관련된다:
> - i2v 가이드 파일을 외부 md 로 빼서 grok 이 로드하는 wiring 패턴 (Phase 3-W) — fork 도 동일 패턴 사용 (`src/wan_i2v_prompting_guide.md`)
> - ImageGen 🎬 자동 모션 + chat_history 분기 동작 (Phase 1, Phase 2) — fork 의 ImageGen 경로에서도 동일 로직이 그대로 작동
> - 사용자-facing `/motion` 커맨드 제거 (Phase 2) — fork 도 `/motion` 커맨드 없음
>
> 원본의 NSFW 관련 fallback (CSAM 차단/refund 카운트/danbooru 태그 fallback) 부분은 SFW fork 에서는 컨텍스트가 다르므로 (SFW 단일 톤, denylist 기반 사전 필터) 본 문서에서는 일반적인 "explicit prompt block 시 silent refund" 정책 정도로만 참고할 것.

`feat/video-improve1` 통합 브랜치 작업 기록. 각 sub-feature 브랜치 완료 시 여기에 요약 누적.

**시작일**: 2026-04-21 (원본 기준)
**브랜치 구조 (원본)**: `main ← develop ← feat/video-improve1 ← feat/<phase-name>`

---

## Phase 1 — Grok Vision 이미지 단독 분석 강화

- **브랜치**: `feat/i2v-vision-enhance`
- **커밋**: `624d3fc`
- **상태**: ✅ 완료 (원본 머지 대기 중 시점)
- **작업 시간**: ~0.3일

**목적**
ImageGen 🎬 버튼처럼 대화 히스토리 없이 Grok Vision만으로 영상 프롬프트를 만들 때, Grok이 씬 의도를 모르고 평균값 모션을 생성하는 문제 완화. 이미지에 물리적으로 연결되는 미세 모션만 생성하도록 강제.

**구현**
- `src/grok.py generate_video_prompts()` — `chat_history`가 None/empty일 때만 `VIDEO_SYSTEM_PROMPT` 뒤에 IMAGE-ONLY MODE 규칙 블록 동적 첨부
- 토큰 ~180개 추가, chat_history 있을 때는 0 토큰 오버헤드
- 핵심 규칙 (SFW fork 에 그대로 적용 가능):
  1. 이미지에서 pose/표정/시선 직접 읽기 (추측 금지)
  2. 5-8초 내 물리적 연속 미세 모션만 (호흡, 시선, 머리카락, 옷자락, 손끝)
  3. 금지: 새 인물/오브젝트, 의상 변화, 포즈 재구성 (standing up, walking, turning, hand relocation)
  4. 불확실 시 작은 충실한 모션 선호

**범위**
- Vision 1차 호출 + 텍스트 재시도 호출 모두 적용 (동일 chat_history 조건)
- `motion_override` 경로는 미적용 — 유저 명시 모션은 신뢰
- 기존 rule 수정 없음, 순수 additive

**SFW fork 영향**
- ImageGen 🎬 (chat_history=None) → 모션 품질 개선 기대 — fork 에서도 동일 효과
- Character bot 🎬 (chat_history 있음) → 0 토큰 오버헤드, 기존 동작 동일

---

## Phase 2 — ImageGen `/motion` 커맨드 제거

- **브랜치**: `feat/i2v-motion-command-remove`
- **커밋**: `2ae03fc`
- **상태**: ✅ 완료
- **작업 시간**: ~0.25일

**목적**
ImageGen 봇의 `/motion <한글 모션>` 커맨드를 완전 제거. i2v 모델이 이미지에 물리적으로 연결되지 않는 임의 모션(예: 누워있는 캐릭터 → "걷기")을 충실히 반영하지 못해 유저 혼란 + 깨진 영상 생성 유발. 자동 모션(🎬 버튼)만 남기고 사용자 모션 지정 경로 제거.

**구현 요지**
- `src/handlers_imagegen.py`: `motion_command` 핸들러 / 등록 / 도움말 라인 / 캡션 문구 제거
- `src/grok.py`: `generate_video_prompts(motion_override=...)` 파라미터는 내부 API로 보존, dead parameter 주석 추가
- `src/video_context.py`, `src/CLAUDE.md`: `/motion` 레퍼런스 업데이트

**SFW fork 영향**
- fork 도 `/motion` 커맨드 미존재 — ImageGen 유저는 🎬 버튼(자동 모션)만 사용
- chat_history=None + motion_override=None 경로는 Phase 1 IMAGE-ONLY 규칙이 그대로 적용됨

---

## Phase 2-B — Vision 호출 fallback 패턴 (참고)

- **브랜치**: `feat/i2v-fallback-pipeline`
- **상태**: 원본에서는 ✅ 완료. SFW fork 에는 아래의 일부만 의미 있음.

원본 작업의 핵심은 "explicit 토큰을 포함한 danbooru 태그를 Vision 에 매번 전달하면 외부 vision 안전 필터가 오발동" 하는 케이스를 다루는 2-step fallback (Step 1 태그 없이 → Step 2 태그 포함 → Step 3 BLOCKED) 이었다.

SFW fork 의 컨텍스트는 다르다:
- fork 는 애초에 explicit 태그가 prompt 조립 단계에서 denylist (`config/sfw_denylist.json`) 로 사전 스트립되므로, 해당 토큰이 vision 호출에 도달할 일이 거의 없다.
- 따라서 원본의 "Step 1 baseline → Step 2 태그 fallback" 분기는 SFW fork 에서는 단순화 가능 — 단일 Vision 호출 + 차단 시 BLOCKED 반환.
- Vision 이 SFW fork 의 prompt 도 거부할 수 있는 (예: 외부 안전 필터의 false positive) 케이스 자체는 여전히 발생 가능하므로, **차단 시 silent BLOCKED + 유저 카운트 보존** 정책은 유지 가치가 있다.

**참고할 만한 구현 패턴**
- `src/handlers_char.py video_callback_handler` / `src/handlers_imagegen.py _run_video_generation`:
  - Vision 차단 시 AtlasCloud 호출 건너뜀
  - 유저 메시지는 단일 "😢 영상 생성이 제한됐어요. 다시 시도해 주세요."
  - 🎬 버튼 복구 → 유저 재시도 가능
  - 운영 로그 (`logger.warning`) 만 남기고 admin 알림 없음 — 유저 채널 유출 방지

**Refund 정책 주의 (원본의 후행 수정)**
원본은 Phase 2-B 도입 시 `refund_video_usage()` 함수를 추가했다가, 이후 별도 패치(`feat/remove-refund-video-usage`, 커밋 `13d2a9d`)에서 제거했다. 이유: caller 가 "성공 후 increment" 패턴으로 구현되어 있으므로 BLOCKED 시점에는 카운트가 아직 0 → refund 가 양수 카운트를 추가로 깎는 -1 버그를 만든다. SFW fork 에서도 동일 패턴이라면 **refund 함수를 추가하지 말 것** — BLOCKED 시 단순히 increment 를 건너뛰면 충분하다.

---

## Admin 알림 정리 — 유저 봇 경로의 `notify_admins` 제거

- **브랜치**: `feat/remove-video-fallback-admin-alerts`
- **커밋**: `459ef9f`
- **상태**: ✅ 완료

**목적**
유저 대면 봇(`context.bot`)이 admin 채널 메시지를 유출시키지 않도록, 비디오 fallback 경로의 `notify_admins(context.bot, ...)` 호출을 모두 제거하고 `logger.info` / `logger.warning` 으로 대체. 인프라 알림은 `src/watchdog.py` + `src/bot.py` 가 별도로 `main_bot` 을 통해 보낸다.

**SFW fork 적용 노트**
- fork 의 비디오 핸들러도 동일 원칙 — `context.bot` 으로 admin 알림 보내지 말 것
- 운영 로그 grep 패턴: `logger.info("Grok 비디오 차단: user=%s", user_id)` 같은 단일 라인

**파일 (원본 기준)**
- [src/handlers_char.py](../../ella-telegram/src/handlers_char.py) — notify_admins import 제거, logger 대체
- [src/handlers_imagegen.py](../../ella-telegram/src/handlers_imagegen.py) — 동일 패턴

---

## Phase 3-R — t2v 폐기, i2v 품질 강화로 전환 (PIVOT)

- **브랜치**: `feat/wan-i2v-research`
- **상태**: ✅ 완료
- **일자**: 2026-04-22
- **작업 시간**: ~0.5일

### 배경 — 왜 t2v 를 버렸는가

당초 원본 plan (Phase 3 ~ Phase 5) 은 **VideoGenEPBot 신규 봇 + text-to-video 직결 아키텍처** 방향이었다. t2v 로 이미지 중간 단계를 제거하면 씬/카메라 자유도가 확보되어 i2v 의 근본 제약 (5~8초 연속 모션만 가능) 을 우회할 수 있다는 가설이었다.

피벗 직전 AtlasCloud t2v 라인업 실험 결과 (PM 수동 샘플링): 모델 별로 "속도 vs 품질" 트레이드오프가 심해서 챗봇 실시간 사용에 만족스러운 단일 t2v 모델이 없었다.

PM 결정: **VideoGenEPBot 방향 취소**. 그 리소스를 **이미 동작 중인 ImageGen 봇의 i2v 파이프라인 + 이미지 파이프라인 품질 강화** 에 재투자.

### 결정 — 폐기한 것 (원본 기준)

- VideoGenEPBot 전용 봇
- `src/handlers_videogen.py` 작성 안 함
- `config/video_t2v_templates.json` preset/pose JSON
- `VIDEO_T2V_SYSTEM_PROMPT` Grok t2v 프롬프트 생성
- t2v 모델 fallback 체인
- `/preset` 커맨드 및 UX
- Admin `/video_model` / `/video_length` / `/video_fallback_chain` 메뉴

### 결정 — 새 산출물

본 피벗 브랜치 (`feat/wan-i2v-research`) 에서 문서 자산 생산:

1. **`research.md` 섹션 추가** — Wan i2v 프롬프팅 리서치
   - i2v vs t2v 구조적 차이, Wan 2.2-turbo / 2.6 / 2.6-flash / 2.7 / seedance 비교표
   - 카메라 한계 (가능/금지 움직임)
   - 오디오 프롬프트 (native audio 전용 규칙)
   - 실패 사례 (face drift, limb dissolution, clothing reconstruction) + 대응
   - AtlasCloud API 특이사항

2. **`src/wan_i2v_prompting_guide.md` 신규** — Grok 주입용 실무 가이드 (SFW fork 가 사용하는 파일명. 원본은 다른 파일명으로 작성됐고, fork 가 rename + strip 해서 사용한다. SFW fork 의 grok 시스템 프롬프트 외부화 (`config/grok_prompts.json`) 와 함께 i2v 가이드도 코드 외부 md 로 분리됨)
   - `danbooru_prompting_guide.md` 패턴 재활용 (영어, 압축, actionable)
   - 카메라 vocab / 모션 vocab / 조명 / 표정 / 오디오 / Failure Matrix / Output Schema
   - **SFW 안전망**: motion prompt 에 vulgar anatomy 토큰이 들어가지 않도록 차단하는 섹션은 SFW fork 에도 그대로 유지 — denylist 와 이중 안전망

### Phase 3 재구성 (원본 기준 — fork 는 이 표를 그대로 따르지 않음)

| Phase | 주제 | 원본 상태 |
|-------|------|-----------|
| 3-R | Wan i2v 리서치 + 가이드 md | ✅ 완료 |
| 3-1 | Grok VIDEO_SYSTEM_PROMPT → 가이드 파일 로드 방식 교체 | 대기 (원본) / fork 에는 적용됨 |
| 3-2 | ImageGen 🎬 품질 튜닝 + 샘플 테스트 | 대기 |
| 3-3 | Vision sanitize fallback | 대기 (fork 에선 denylist 사전 스트립으로 부분 대체) |
| 3-4 | ImageGen 🎬 씬 프리셋 (motion intent) | 대기 |
| 3-5 | wan-2.6 / 2.7 i2v 비교 + default 재평가 | 대기 (fork 는 wan-2.6-flash 로 고정) |
| 3-6 | ImageGen `/random` 품질 튜닝 | 대기 |
| 3-7 | Audio prompt 품질 개선 (native audio) | 대기 |

### SFW fork 영향

- fork 는 Phase 3-R 의 **결과 산출물 (i2v 가이드 md 외부화)** 패턴만 채택했다. wan-2.6/2.7 비교, 씬 프리셋, sanitize fallback 등은 fork 의 단순화 정책 (단일 모델, denylist 기반 사전 필터) 으로 대체됐다.

---

## Phase 3-W — Grok 가이드 파일 로드 wiring

- **브랜치**: `feat/wan-i2v-research` (Phase 3-R 과 동일 브랜치에서 이어감)
- **커밋**: `ec59703`
- **상태**: ✅ 완료
- **작업 시간**: ~0.25일

**목적**
Phase 3-R 에서 작성한 i2v 가이드 md 를 실제 Grok 비디오 프롬프트 생성 경로에 연결.

**구현**
- `src/grok.py` 모듈 init 시 guide 파일 read → `VIDEO_SYSTEM_PROMPT` 상수에 할당
- 기존 embedded string 삭제
- Phase 1 `image_only_suffix` dynamic addition 동작 보존

**SFW fork 적용**
- fork 에서는 가이드 파일이 **`src/wan_i2v_prompting_guide.md`** 로 rename 되어 로드된다 (원본은 다른 파일명).
- 추가로 fork 는 5개 다른 prompt 상수 (`SYSTEM_PROMPT`, `RANDOM_SYSTEM_PROMPT`, `CLASSIFY_SYSTEM_PROMPT`, `PARTIAL_EDIT_SYSTEM_PROMPT`, `VIDEO_ANALYZER_PROMPT`) 도 함께 외부화하여 `config/grok_prompts.json` 단일 파일에서 로드한다 (`CLAUDE.md` 결정사항 9번 참조).
- 효과: 향후 가이드/프롬프트 튜닝 = md/json 파일 편집만, 코드 수정 불필요.

**파일 (fork)**
- `src/grok.py` — `VIDEO_SYSTEM_PROMPT` 는 `src/wan_i2v_prompting_guide.md` 에서 로드, 5개 prompt 는 `config/grok_prompts.json` 에서 로드
- `src/wan_i2v_prompting_guide.md` — fork 가 rename + strip 해서 보유한 SFW i2v 가이드
- `config/grok_prompts.json` — fork 가 신규 작성한 SFW 전용 prompt 번들

## 다음 단계

원본 `ella-telegram` 의 Phase 3-1 ~ 3-7 후속 작업은 SFW fork 와 무관하다. SFW fork 의 비디오 관련 후속 작업은 fork 의 자체 plan/status 문서 (작성 예정) 를 참조한다.
