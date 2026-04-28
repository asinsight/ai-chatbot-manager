# ella-chat-publish — SFW fork of ella-telegram

## 프로젝트 목표

`/Users/junheeyoon/Code/ella-telegram`의 텔레그램 캐릭터 챗봇을 **SFW(Safe-For-Work) 전용 버전**으로 새로 빌드한다. 동일한 핵심 기능(캐릭터 챗, 이미지 생성, 비디오 생성, 텔레그램 통합, ComfyUI 연동)을 유지하되, 성적/명시적 콘텐츠 생성·유도·게이팅 로직과 흥분(arousal) 스탯 시스템을 전면 제거하여 일반 등급의 캐릭터 인터랙션 봇으로 만든다. 오픈소스 공개 버전이므로 유료 등급 게이팅 / 빌링 / 텔레그램 Stars 코드도 모두 제거되어 모든 유저가 동일한 기능을 사용한다.

## 중요 원칙

- **원본 절대 불변**: `/Users/junheeyoon/Code/ella-telegram` 디렉터리는 read-only다. 어떤 경우에도 수정/삭제/추가하지 않는다. 참고용으로만 읽는다.
- **현재 작업 디렉터리**: `/Users/junheeyoon/Code/ella-chat-publish` — 모든 새 코드/문서는 여기에 작성한다.
- **ComfyUI checkpoint 가중치는 스코프 외**: 모델 파일명은 NSFW 표기가 있어도 검토 대상이 아니다. 워크플로우 로직과 LoRA 결합 방식만 정리한다.
- **미성년자 보호 입력 필터는 유지**: `src/input_filter.py`의 미성년/loli/shota 차단 정규식은 SFW에서도 안전망으로 그대로 가져온다.

## 결정 사항 (Design Decisions)

1. **캐릭터 카드 미이관**: `behaviors/`, `persona/`, `images/` 의 char01–char10 + char_test JSON은 fork로 가져오지 않는다. SFW 전용 캐릭터 카드를 새로 작성한다. → 기존 인벤토리의 STRIP/AUDIT 항목 다수가 "신규 작성"으로 단순화됨.
2. **Stat 시스템 단순화**: `arousal` 개념은 코드/스키마/프롬프트/캐릭터 카드 모든 레이어에서 완전 제거. **`fixation`만 남긴다** (`mood`, `location`은 보조로 유지). `heat_active`, `body_nsfw_json`, `arousal_speech`, `arousal_response`, `heat_cycle`, `curse_heat`, `RELIEF`, `Layered Lust` 모두 미존재.
3. **이미지 생성기 SFW Only**: `/random NSFW` 버튼 / NSFW 분기 / NSFW LoRA preset / NSFW 씬 카탈로그 / NSFW 분류기 (`pose_scene_classifier.py`) 모두 미포함. SFW 경로 단일화.
4. **ComfyUI 임베딩 prefix 재배치** (`comfyui.py:52-53`):
   - 현재 원본:
     - `EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos, embedding:illustrious/lazynsfw"`
     - `EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"`
   - SFW fork:
     - `EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"` (lazynsfw 제거)
     - `EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazy-nsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"` (lazy-nsfw를 negative 맨 앞에 prefix)
5. **Positive 프롬프트 섹션 전면 재작성**: `grok.py`의 `SYSTEM_PROMPT` (Danbooru 태그 생성 룰 8/9/9-2/10), `config/system_prompt.json`의 master_prompt 중 photo/physical-realism 섹션, 그리고 positive 프롬프트 조립 로직 (handlers_imagegen.py + prompt.py)을 전부 새로 작성. 기존 룰을 한 줄씩 strip하지 않고 **백지에서 SFW 룰셋을 새로 정의**한다.
6. **사진 보내기 트리거 재연결 (arousal → fixation)**: 원본은 [handlers_char.py:687-691](../ella-telegram/src/handlers_char.py#L687)에서 `arousal > 30`일 때만 📷 버튼을 노출한다. SFW fork에서는 arousal이 없어지므로 **fixation 임계값**으로 재바인딩한다. 추가로 [handlers_char.py:793-798](../ella-telegram/src/handlers_char.py#L793)의 `fixation < 20` 거리두기 가드는 그대로 유지한다.
   - 제안 임계값 (구현 단계에서 확정): `fixation > 50` → 📷 버튼 노출, `fixation > 80` → IMAGE_AUTONOMY 상향
   - LLM `[STAT:]` 토큰 포맷도 `fixation+3, arousal+5, mood:..., location:...` → `fixation+3, mood:..., location:...`로 변경
   - `heat_cycle` 트리거는 미존재 ([handlers_char.py:442-466](../ella-telegram/src/handlers_char.py#L442))
   - `[RELIEF]` 시그널 미존재 ([handlers_char.py:603-617](../ella-telegram/src/handlers_char.py#L603))

7. **비디오 LoRA 전면 삭제 + 모델 변경**: 원본 [src/video.py](../ella-telegram/src/video.py)의 LoRA 분기를 모두 제거하고, 비디오 모델을 Atlas Cloud `alibaba/wan-2.6/image-to-video-flash` (= "wan2.6-flash")로 고정한다.
   - **삭제 대상**:
     - [video.py:29](../ella-telegram/src/video.py#L29) `_LORA_MODEL_ID = "atlascloud/wan-2.2-turbo-spicy/image-to-video-lora"`
     - [video.py:117-132](../ella-telegram/src/video.py#L117) `_prepare_loras()` 함수 전체
     - [video.py:259, 273-274, 278-312](../ella-telegram/src/video.py#L259) `lora_config` 파라미터 / `has_lora` 분기 / `high_noise_loras`+`low_noise_loras` kwargs / 모델 override 로직
     - [video.py:25, 305-307](../ella-telegram/src/video.py#L25) `CIVITAI_API_TOKEN` 관련 코드
     - [video_context.py:34-39](../ella-telegram/src/video_context.py#L34) `lora_preset` 매핑 hint, `_resolve_preferred_pose_key()` 호출 부위
     - 호출부에서 `lora_config=` 인자 제거 (handlers 시리즈)
   - **모델 설정**:
     - [video.py:17](../ella-telegram/src/video.py#L17) `VIDEO_MODEL` 기본값을 `"alibaba/wan-2.6/image-to-video-flash"`로 변경 (Atlas Cloud 네이티브 오디오 지원)
     - `.env.example`에 `VIDEO_MODEL=alibaba/wan-2.6/image-to-video-flash` 명시
   - **DaSiWa/RunPod fallback 경로 — 옵션 A 확정 (전체 삭제)**:
     - [video.py:140](../ella-telegram/src/video.py#L140) DaSiWa ComfyUI 워크플로우 로드 코드
     - [video.py:156-260](../ella-telegram/src/video.py#L156) `generate_video_runpod()` 함수 전체
     - [video.py:282-285](../ella-telegram/src/video.py#L282) DaSiWa 라우팅 분기
     - [comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json](../ella-telegram/comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json) 미이관
     - ComfyUI MMAudio bypass 로직(무음 비디오 → MMAudio v2 합성) 동반 삭제
     - `RUNPOD_VIDEO_*` 환경변수, `runpod_video_enabled` 플래그, [comfyui.py:46-49](../ella-telegram/src/comfyui.py#L46) RunPod 비디오 설정 모두 제거
     - [deploy/runpod-video/](../ella-telegram/deploy/runpod-video/) 폴더 미이관
   - **참고**: [video.py:33-35](../ella-telegram/src/video.py#L33)에 `wan-2.6/image-to-video-flash`가 이미 known model 리스트에 있어 호출 인터페이스는 그대로 사용 가능

8. **워크플로우 규칙 (코드 수정 방식)**: 원본 `/Users/junheeyoon/Code/ella-telegram`에 있는 코드를 절대 건드리지 않는다. 수정이 필요한 모든 코드/룰은 다음 절차를 따른다:
   1. 원본 파일을 `/Users/junheeyoon/Code/ella-chat-publish` 내 같은 상대 경로로 **복사**한다 (Read → Write).
   2. 복사된 사본을 **수정**한다 (Edit).
   3. 모든 편집·삭제·추가 작업은 fork 디렉터리 안에서만 일어난다.

   적용 범위:
   - **복사 후 수정**: `src/*.py` 대부분 (grok.py, history.py, handlers_*.py, prompt.py, trait_pools.py, comfyui.py, video.py, video_context.py 등), `config/system_prompt.json`, ~~`config/lora_presets.json`(SFW LoRA만 남김)~~ → **DROP 확정 (아래 추가 DROP 참조)**, `config/sfw_scenes.json`, `comfyui_workflow/*.json`
   - **신규 작성 (NEW, 복사 안 함)**: `behaviors/`, `persona/`, `images/` 의 SFW 캐릭터 카드, `config/grok_prompts.json` (외부화된 SFW 프롬프트)
   - **이관 안 함 (DROP)**: `config/nsfw_scenes.json`, `config/nsfw_scenes.json.bak`, `docs/nsfw_rules.json`, `src/pose_scene_classifier.py`, `comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json`, `comfyui_workflow/audiogen-workflow.json` (Phase 2D 삭제 — wan2.6-flash 네이티브 오디오 사용으로 별도 합성 불필요), `deploy/runpod-video/`, `data/`, `output/`, `logs/`, `images/`(런타임 산출물), `venv/`, `.env`
   - **추가 DROP (구현 단계 확정)**: `config/lora_presets.json` (Phase 2B B6에서 `pose_motion_presets.py` LoRA 로딩 단순화 후 fork 코드 어디에서도 참조 안 함 — 원래 계획은 COPY+STRIP 이었음), `config/dasiwa_aio_defaults.json` (Phase 2A A3에서 DaSiWa 코드 경로가 삭제되어 묵시적으로 DROP — 원래 계획은 COPY+STRIP 이었음)
   - **복사 + rename + strip**: `src/wan_nsfw_i2v_prompting_guide.md` → `src/wan_i2v_prompting_guide.md` (NSFW 섹션만 삭제, 일반 가이드 유지)

9. **Grok 시스템 프롬프트 외부화**: 원본은 `grok.py` 내부에 5개 프롬프트 상수가 하드코드되어 있다 — 이를 JSON 파일로 추출해 런타임에 로드하도록 한다. 코드를 안 건드리고도 프롬프트 튜닝이 가능해진다.

   **외부화 대상** (원본 위치):
   | 상수명 | 원본 위치 | 용도 |
   |---|---|---|
   | `VIDEO_ANALYZER_PROMPT` | [grok.py:79](../ella-telegram/src/grok.py#L79) | 비디오 안전도 + 포즈 tier 분류 (f-string) |
   | `SYSTEM_PROMPT` | [grok.py:159](../ella-telegram/src/grok.py#L159) | 캐릭터 챗 → Danbooru 태그 생성 룰 |
   | `RANDOM_SYSTEM_PROMPT` | [grok.py:645](../ella-telegram/src/grok.py#L645) | `/random` 씬 프롬프트 |
   | `CLASSIFY_SYSTEM_PROMPT` | [grok.py:991](../ella-telegram/src/grok.py#L991) | 입력 분류 |
   | `PARTIAL_EDIT_SYSTEM_PROMPT` | [grok.py:1226](../ella-telegram/src/grok.py#L1226) | 캐릭터 부분 수정 |
   | `VIDEO_SYSTEM_PROMPT` | [grok.py:46-55](../ella-telegram/src/grok.py#L46) | 이미 외부 파일 로드 — `src/wan_i2v_prompting_guide.md` (rename + strip된 사본)에서 계속 로드 |

   **설계**:
   - 위치: `config/grok_prompts.json` (단일 파일, 키 = 프롬프트 이름)
   - 키: `system`, `video_analyzer`, `random`, `classify`, `partial_edit`, `video_system`
   - 값: 멀티라인 문자열 (JSON에서는 `\n`로 직렬화). f-string의 `{변수}`는 JSON에 그대로 두고 `grok.py`가 로드 후 `.format(**ctx)`로 채움 — 단, JSON 안의 중괄호는 의미상 충돌하므로 (예: JSON 예시 출력) `${변수}` 같은 다른 placeholder 문법으로 통일하거나 `string.Template`을 사용하는 것을 권장.
   - 로더: `grok.py` import 시점에 한 번 로드. 로딩 실패 시 명확한 에러로 fail-fast (fallback 문자열 안 둠 — 잘못된 빈 프롬프트로 운영되는 사고 방지).
   - 핫 리로드: 일단 미지원 (필요해지면 명시적 함수 추가). 프로세스 재시작으로 갱신.
   - 검증: 로드 직후 모든 키 존재 여부 + 빈 문자열 여부 체크.
   - SFW fork에서는 이 JSON을 백지에서 SFW 룰셋으로 작성한다 (NSFW 룰 8/9/9-2 / safety_level 5단계 / Tier 분류 등 미포함).

## 현재 단계

**Phase 0 — Discovery (완료)**: 원본 코드베이스의 NSFW 의존성 인벤토리 작성.
- ✅ NSFW 인벤토리 문서 작성 → [NSFW_INVENTORY.md](NSFW_INVENTORY.md)
- ✅ 사용자 검토 후 fork 작업 우선순위 확정 → Phase 1 ~ 2D 진행

## Implementation Status (진행 상황)

> 본 섹션은 계획 문서(이 CLAUDE.md, NSFW_INVENTORY.md)가 작성된 이후 실제로 구현된 단계를 기록한다. 위쪽 결정 사항은 *계획*, 아래 표는 *실행 결과*.

| Phase | 상태 | 커밋 | 내용 |
|---|---|---|---|
| Phase 1 | ✅ 완료 | `b607910` | fork 골격 (디렉터리 / 미이관 항목 / `ella-chat-publish.service` rename) |
| Phase 2A | ✅ 완료 | `16ced9b` | 독립 모듈 재작성 (history.py, trait_pools.py, comfyui.py, video.py, video_context.py, prompt.py, A3에서 DaSiWa 경로 삭제) |
| Phase 2B | ✅ 완료 | `69f98a4` | 핸들러 레이어 + 잔존 정리 (handlers_*, grok.py 외부화, B6: `pose_motion_presets.py` LoRA 로딩 드롭) |
| Phase 2C | ✅ 완료 | `efa9bf8` | 통합 수정 + config 잔재 (C4: `lora_presets.json` 참조 0건 검증, C6: `dasiwa_aio_defaults.json` 참조 0건 검증) + 서브 디렉터리 CLAUDE.md |
| Phase 2D | 🔄 진행 중 | — | 최종 잔재 정리 (D3에서 `comfyui_workflow/audiogen-workflow.json` 삭제), 본 D4 문서 동기화 |
| **Pending** | 🔜 | — | SFW 캐릭터 카드 신규 작성 (`behaviors/`, `persona/`, `images/`), end-to-end 테스트 |

## NSFW 인벤토리 요약

상세는 [NSFW_INVENTORY.md](NSFW_INVENTORY.md) 참조.

### 영향이 큰 모듈 (REWRITE 또는 광범위 STRIP)
1. **`src/grok.py`** (2,042 LOC, 129 NSFW 매치) — Danbooru 태그 생성 룰(Rule 8/9/9-2/10), VIDEO_ANALYZER `safety_level` 분류, NSFW i2v 가이드 로딩 — ♻️ REWRITE
2. **`src/history.py`** (2,078 LOC, 62 매치) — DB 스키마(`arousal`, `body_nsfw_json`, `heat_active` 컬럼), arousal decay 로직, 캐릭터 기본값 — ✂️ STRIP
3. **`src/handlers_imagegen.py`** (1,611 LOC, 77 매치) — `/random NSFW` 분기, body_nsfw 머지, NSFW LoRA 오버라이드 — ✂️ STRIP
4. **`src/handlers_char.py`** (1,503 LOC, 44 매치) — arousal 스탯 통합, heat cycle, RELIEF 시그널, IMAGE_AUTONOMY 게이팅 — ✂️ STRIP
5. **`src/prompt.py`** (749 LOC, 26 매치) — arousal 임계값 분기, **Layered Lust** 3-layer 구조, arousal speech/response — ✂️ STRIP
6. **`src/trait_pools.py`** (818 LOC, 50 매치) — BODY_NSFW_* 5개 상수(60+ 태그), NSFW 씬 로더/롤러, FORCE_NSFW_SCENE — ✂️ STRIP
7. **`config/system_prompt.json`** master_prompt — Section 2(PHOTO 행위 묘사), 5(PHYSICAL REALISM NSFW), 5-1(CLIMAX/RELIEF) — ♻️ REWRITE
8. **`config/lora_presets.json`** — NSFW 전용 LoRA preset 다수 — ~~✂️ STRIP~~ → 🚫 **DROP** (Phase 2B B6 이후 fork 코드에서 참조 0건 — 미이관 확정)

### 전체 삭제 대상 (DROP, fork에 미이관)
- `config/nsfw_scenes.json` (488 lines, 100% NSFW 씬 카탈로그) + `.bak`
- `docs/nsfw_rules.json` (캐릭터별 sexual personality)
- `src/pose_scene_classifier.py` (대화 → NSFW 씬 분류기, 100% NSFW 의도)
- `comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json` (DaSiWa fallback 경로 삭제에 따라)
- `deploy/runpod-video/` (DaSiWa fallback 경로 삭제에 따라)
- `danbooru_tag_strategy.md` Section 10 (또는 파일 자체 SFW 버전으로 교체)

### Rename + Strip 대상
- `src/wan_nsfw_i2v_prompting_guide.md` → `src/wan_i2v_prompting_guide.md`: 파일명 변경하면서 NSFW 섹션 3개만 삭제 (일반 i2v 가이드는 유지). `grok.py`가 새 파일명에서 계속 로드

### 작업 권장 순서 (결정사항 반영본)

> **공통 절차**: 모든 코드/설정 수정은 "원본 파일을 fork 디렉터리로 **복사** → 사본을 **수정**" 순서로 진행. 원본은 절대 건드리지 않는다. 신규 작성(NEW) 항목은 원본을 복사하지 않는다.

1. 새 디렉터리 골격 생성 (NSFW 데이터/문서/캐릭터 카드는 처음부터 미포함)
2. **DB 스키마 정리** (`history.py` 복사 → `arousal`/`body_nsfw_json`/`heat_active` 컬럼 정의·decay 로직·기본값·`STAT_DELTAS` arousal 항목 모두 제거 → `fixation`/`mood`/`location` 만 유지)
3. `trait_pools.py` 복사 → `BODY_NSFW_*` 5개 상수 / NSFW 씬 함수 / `FORCE_NSFW_SCENE` 제거; SFW 씬 풀과 일반 의상/속옷 풀만 유지
4. `pose_scene_classifier.py` 미이관 (호출부도 fork에 처음부터 없게 함)
5. `comfyui.py` 복사 → embedding prefix 두 줄 변경 (`lazynsfw`를 negative prefix 맨 앞으로 이동)
6. **`video.py` 복사 → LoRA 전면 삭제 + 모델 변경 (옵션 A 확정)**:
   - `_LORA_MODEL_ID`, `_prepare_loras()`, `lora_config` 파라미터, `has_lora` 분기, `high_noise_loras`+`low_noise_loras` kwargs, `CIVITAI_API_TOKEN` 코드 모두 삭제
   - `VIDEO_MODEL` 기본값을 `alibaba/wan-2.6/image-to-video-flash`로 변경
   - DaSiWa/RunPod fallback 경로 전체 삭제: `generate_video_runpod()` 함수, DaSiWa 라우팅 분기, ComfyUI MMAudio bypass 로직, [comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json](../ella-telegram/comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json) 미이관, `comfyui.py`의 RunPod 비디오 설정 + `RUNPOD_VIDEO_*` 환경변수, `deploy/runpod-video/` 폴더 모두 제거
   - `video_context.py` 복사 → `lora_preset` 관련 hint/매핑 코드 제거
7. **`grok.py` 복사 → 프롬프트 외부화 + 백지 재작성**:
   - 5개 프롬프트 상수(`VIDEO_ANALYZER_PROMPT`, `SYSTEM_PROMPT`, `RANDOM_SYSTEM_PROMPT`, `CLASSIFY_SYSTEM_PROMPT`, `PARTIAL_EDIT_SYSTEM_PROMPT`)를 코드에서 제거
   - import 시 `config/grok_prompts.json`을 로드하는 구조로 변경 (fail-fast, fallback 없음)
   - `config/grok_prompts.json` 신규 작성 — SFW Danbooru 룰만 정의 (옷 풀세트 강제, 노출/체액/성행위 태그 금지). `VIDEO_ANALYZER_PROMPT`도 항상 SFW만 산출
   - **i2v 가이드 파일 처리**: `src/wan_nsfw_i2v_prompting_guide.md` → `src/wan_i2v_prompting_guide.md`로 **rename 후 NSFW 섹션 삭제** (복사 → 수정). 원본은 그대로 두고 fork에서 새 파일명으로 작성.
     - 삭제 대상 섹션: `## NSFW Levels (arousal-gated)` (line ~198), `### Composer level selection` (line ~210, NSFW Levels 하위), `## AHEGAO VERBATIM` (line ~223)
     - 유지: 카메라 vocab / 모션 vocab / 조명 / 표정 / 오디오 / Failure Matrix / Output Schema 등 일반 i2v 가이드 부분
     - `### Vulgar anatomy terms — AVOID in motion_prompt` (line ~161) 섹션은 SFW에서도 motion prompt에 vulgar 표현이 들어가지 않게 하는 안전망이므로 그대로 유지
     - `grok.py`의 가이드 로딩 경로(`_GUIDE_PATH`)도 새 파일명에 맞춰 갱신
8. **`config/system_prompt.json` 복사 → master_prompt 재작성**:
   - Section 2(PHOTO SENDING)를 SFW 시나리오만(일상/취미/풍경/표정/스타일/포즈) 기준으로 재작성
   - Section 5(PHYSICAL REALISM NSFW), Section 5-1(CLIMAX/RELIEF) 삭제
9. **`handlers_char.py` 복사 → arousal 시스템 제거 + 사진 보내기 fixation 재바인딩**:
   - `arousal`/`heat_cycle`/`[RELIEF]`/`set_character_arousal` import 및 호출부 제거
   - `[STAT:]` 토큰 파서에서 `arousal_delta` 제거, `update_character_stats` 시그니처에서 `arousal_delta` 제거
   - **📷 버튼 노출 조건**: `arousal > 30` → `fixation > 50` (임계값 구현 단계 확정)
   - `fixation < 20` 거리두기 가드는 그대로 유지
10. **`handlers_imagegen.py` 복사 → `/random NSFW` 분기 / `body_nsfw` 머지 / NSFW LoRA override 제거**
11. **`handlers_main.py` 복사 → `/scene` admin 명령에서 NSFW 분기 제거**
12. **`prompt.py` 복사 → arousal 분기 / Layered Lust / arousal speech 제거**, `IMAGE_AUTONOMY`는 fixation 기반 단일 분기로 단순화
13. **SFW 캐릭터 카드 신규 작성** (`behaviors/`, `persona/`, `images/` — NEW): `arousal_speech`/`arousal_response`/`heat_cycle`/`curse_heat`/`body_nsfw` 필드 미존재
14. ~~`config/lora_presets.json` 복사 → NSFW 전용 LoRA preset 삭제, 유틸성(스타일/조명/품질) 만 유지~~ → **Phase 2B B6 결과 DROP 확정**: B6에서 `pose_motion_presets.py`가 LoRA 로딩 자체를 드롭하면서 fork 코드에 `lora_presets.json`을 참조하는 곳이 없음(Phase 2C C4 검증). 파일 미이관.
15. **`config/sfw_scenes.json` 복사 → 한 줄씩 audit**, 경계 항목(suggest/tease/lingerie-focused) 톤다운 또는 제거
16. `.env.example` 복사 → `POSE_CLASSIFIER_*`, `FORCE_NSFW_SCENE`, `CIVITAI_API_TOKEN` 제거; `VIDEO_MODEL` 기본값 갱신
17. End-to-end SFW 테스트 + NSFW 트리거 negative 테스트 (예: "옷 벗어줘", "야한 사진" 입력 시 SFW로 강건히 거절/우회)

## 폴더 규칙

- 원본 참조는 항상 절대 경로 또는 `../ella-telegram/...` 형태로 표기
- fork 시작 시 가져오지 않는 폴더: `data/`, `output/`, `logs/`, `images/`(런타임 산출물), `venv/`, `.env`(시크릿)
- 새 plan/status 문서는 ella-telegram의 plan.md 등을 그대로 가져오지 않고 SFW용으로 새로 작성
