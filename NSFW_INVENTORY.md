# NSFW Inventory — ella-telegram → ella-chat-publish (SFW fork)

원본: `/Users/junheeyoon/Code/ella-telegram` (read-only, 절대 수정/삭제/추가 금지)
목적: SFW 전용 fork 제작을 위해 NSFW가 포함된 모든 위치를 사전에 식별.

**스코프 규칙**
- ✅ 포함: NSFW 프롬프트, NSFW 트레잇/씬, NSFW 핸들러 분기, NSFW 분류기/필터, arousal(흥분 스탯) 시스템, 발정/heat cycle, NSFW LoRA preset, NSFW 시스템 프롬프트, NSFW 가이드 문서, NSFW 관련 env var
- ❌ 제외: ComfyUI **checkpoint** 모델 가중치 파일명 (예: `*-NSFW-*.safetensors`) — 모델 자체는 그대로 두고 워크플로우 로직과 LoRA 결합만 정리

**조치 표기**
- 🗑️ DELETE: 파일/필드 전체 삭제
- ✂️ STRIP: 파일을 유지하되 NSFW 블록만 제거
- ♻️ REWRITE: 큰 폭으로 재작성 (룰/로직 변경)
- 🆕 NEW: fork에 새로 작성 (원본을 가져오지 않음)
- 🔇 DISABLE: 코드는 두되 env/플래그로 비활성화
- 🔍 AUDIT: 한 줄씩 읽으며 잔여물 확인

---

## 0. 결정사항에 따른 인벤토리 갱신

본 인벤토리는 1차 식별본이며, 다음 결정사항이 적용된 후의 실제 작업 분류는 아래와 같다.

### 워크플로우 규칙 (전 영역 공통)

원본 `/Users/junheeyoon/Code/ella-telegram`은 **read-only**다. 코드/룰을 고칠 때는:
1. 원본 파일을 fork(`/Users/junheeyoon/Code/ella-chat-publish`)로 같은 상대 경로에 **복사** (Read → Write)
2. 복사된 사본을 **수정** (Edit)
3. 모든 편집은 fork 안에서만

NEW 분류 항목(SFW 캐릭터 카드, `config/grok_prompts.json`)은 복사하지 않고 신규 작성.

### 분류 매핑

| 영역 | 1차 분류 | 결정 반영 후 |
|---|---|---|
| `arousal` 스탯 시스템 (history.py / handlers_char.py / prompt.py) | ✂️ STRIP | 📋 COPY+STRIP — 원본 복사 후 arousal 관련 코드 제거 |
| 캐릭터 카드 (behaviors/persona/images) | ✂️ STRIP / 🔍 AUDIT | 🆕 NEW — SFW 캐릭터 카드 신규 작성, 원본 미이관 |
| 이미지 생성기 NSFW 분기 (handlers_imagegen.py) | ✂️ STRIP | 📋 COPY+STRIP — `/random NSFW`/`body_nsfw` 머지/NSFW LoRA override 제거 |
| 사진 보내기 트리거 (handlers_char.py 📷 버튼) | — | 📋 COPY+REBIND — `arousal > 30` → `fixation > 50` 으로 재바인딩 |
| Danbooru 태그 생성 룰 (grok.py SYSTEM_PROMPT) | ♻️ REWRITE | 📋 COPY+♻️ REWRITE — grok.py를 복사 후 프롬프트 상수 5개를 JSON 로딩으로 교체, JSON은 🆕 NEW |
| Grok 프롬프트 외부화 | — | 🆕 NEW — `config/grok_prompts.json` 신규 작성 |
| Positive 프롬프트 조립 (comfyui.py + grok.py + prompt.py + system_prompt.json) | 부분 ✂️ + 부분 ♻️ | 📋 COPY+♻️ REWRITE (전면 재작성) |
| `embedding:illustrious/lazynsfw` (comfyui.py:52) | ✂️ STRIP (제거) | 📋 COPY+MOVE — **negative prefix 맨 앞**으로 이동 |
| `pose_scene_classifier.py` | 🗑️ DELETE / 🔇 DISABLE | 🚫 DROP — 미이관 (호출부도 처음부터 없음) |
| 비디오 LoRA 시스템 (video.py / video_context.py) | — | 📋 COPY+STRIP — LoRA 분기 전면 삭제 |
| 비디오 모델 | — | 📋 COPY+SET — `VIDEO_MODEL = alibaba/wan-2.6/image-to-video-flash` (Atlas Cloud) |
| DaSiWa/RunPod 비디오 fallback 경로 | — | ⚠️ 미정 — Atlas only 단일화(권장) vs 백업 유지 |
| NSFW 씬/LoRA preset (config/nsfw_scenes.json, config/lora_presets.json NSFW preset) | 🗑️ DELETE / ✂️ STRIP | 🚫 DROP (`nsfw_scenes.json`) / 📋 COPY+STRIP (`lora_presets.json`) |
| `src/wan_nsfw_i2v_prompting_guide.md` | 🗑️ DELETE | 📋 COPY+RENAME+STRIP — `wan_i2v_prompting_guide.md`로 이름 변경, NSFW 섹션만 삭제 (일반 i2v 가이드 유지) |
| 기타 NSFW 가이드 문서 (`docs/nsfw_rules.json`, `danbooru_tag_strategy.md` Section 10) | 🗑️ DELETE | 🚫 DROP — 미이관 |

### 사진 보내기 트리거 재바인딩 상세

원본 [src/handlers_char.py:687-691](../ella-telegram/src/handlers_char.py#L687):
```python
# 📷촬영 버튼 — arousal > 30 + 이미지 전송이 없을 때만 표시
if _cached_stats["arousal"] > 30:
    # ... 버튼 추가
```

원본 [src/handlers_char.py:793-798](../ella-telegram/src/handlers_char.py#L793) (이미 fixation 가드 존재):
```python
# 수치 기반 거리두기 — fixation < 20이면 이미지 생성 스킵
if _img_stats["fixation"] < 20:
    logger.info("거리두기 상태 — 이미지 생성 스킵 (fixation=%d, 유저 %s, %s)", ...)
```

SFW fork 적용본 (제안):
- `arousal > 30` 분기 → `fixation > 50` (구현 단계에서 임계값 확정)
- `fixation < 20` 거리두기 가드 그대로 유지
- LLM `[STAT:]` 토큰 포맷도 `arousal+N` 항목 제거

추가로 [history.py:30](../ella-telegram/src/history.py#L30) `STAT_DELTAS`에서 `"arousal"` 키 삭제, [history.py:14-25](../ella-telegram/src/history.py#L14) 캐릭터별 기본값 dict에서 `arousal: 0` 제거.

### 비디오 LoRA 전면 삭제 + 모델 변경 상세

원본 [src/video.py](../ella-telegram/src/video.py) 핵심 발견:

```python
# Line 17 — 현재 기본 모델
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "alibaba/wan-2.7/image-to-video")

# Line 25 — Civitai LoRA 다운로드 토큰
CIVITAI_API_TOKEN = ...

# Line 29 — LoRA 활성 시 강제 사용 모델
_LORA_MODEL_ID = "atlascloud/wan-2.2-turbo-spicy/image-to-video-lora"

# Line 33-35 — known model 리스트 (wan-2.6/image-to-video-flash 이미 포함)
_KNOWN_MODELS = (
    "alibaba/wan-2.6/image-to-video",
    "alibaba/wan-2.6/image-to-video-flash",  # ← SFW fork 기본 모델
    "alibaba/wan-2.7/image-to-video",
)

# Line 117-132 — LoRA bucket 변환 함수
def _prepare_loras(lora_config: dict) -> tuple[list, list]: ...

# Line 259 — LoRA 파라미터
async def generate_video(..., lora_config: dict | None = None): ...

# Line 278-312 — has_lora 분기, 모델 override, kwargs 주입
has_lora = bool(lora_config and ...)
effective_model = _LORA_MODEL_ID if has_lora else VIDEO_MODEL
if has_lora:
    high, low = _prepare_loras(lora_config)
    gen_kwargs["high_noise_loras"] = high
    gen_kwargs["low_noise_loras"] = low
```

**SFW fork 적용본**:
- `_LORA_MODEL_ID`, `_prepare_loras()`, `lora_config` 파라미터, `has_lora` 분기, `high_noise_loras`+`low_noise_loras` kwargs, `CIVITAI_API_TOKEN` 코드 모두 삭제
- `VIDEO_MODEL` 기본값을 `"alibaba/wan-2.6/image-to-video-flash"`로 변경
- `generate_video()` 시그니처 단순화 (lora 인자 제거), 호출부도 모두 갱신
- `.env.example`에서 `CIVITAI_API_TOKEN` 라인 삭제, `VIDEO_MODEL` 기본값 표기 갱신

원본 [src/video_context.py:34-39](../ella-telegram/src/video_context.py#L34) `lora_preset` 매핑/`_resolve_preferred_pose_key()` 관련 hint도 제거.

**DaSiWa/RunPod fallback 경로 — 옵션 A 확정 (전체 삭제)**:
- [video.py:140](../ella-telegram/src/video.py#L140) DaSiWa ComfyUI 워크플로우 로드 코드 삭제
- [video.py:156-260](../ella-telegram/src/video.py#L156) `generate_video_runpod()` 함수 전체 삭제
- [video.py:282-285](../ella-telegram/src/video.py#L282) DaSiWa 라우팅 분기 + ComfyUI MMAudio bypass 로직 동반 삭제
- [comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json](../ella-telegram/comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json) 미이관 (🚫 DROP)
- [comfyui.py:46-49](../ella-telegram/src/comfyui.py#L46) `runpod_video_enabled`, `RUNPOD_VIDEO_ENDPOINT_ID`, `RUNPOD_VIDEO_MAX_WORKERS` 제거
- `.env.example`에서 `RUNPOD_VIDEO_*` 환경변수 제거
- [deploy/runpod-video/](../ella-telegram/deploy/runpod-video/) 폴더 미이관 (🚫 DROP)

### i2v 가이드 파일 rename + NSFW 섹션 strip 상세

원본 [src/wan_nsfw_i2v_prompting_guide.md](../ella-telegram/src/wan_nsfw_i2v_prompting_guide.md) (300+ 라인, NSFW 키워드 매치 15) 의 섹션 헤딩:

```
1   ## Role + Output Contract
5   ## WAN 2.2 i2v Prompt Structure
14  ## Camera Vocabulary (Official WAN 2.2)
39  ## i2v-SAFE vs UNSAFE Camera
62  ## Motion Vocabulary
71  ## Motion Amplitude Target
85  ## Detail Density
104 ## Face Motion
133 ## Identity Anchors
152 ### Abstract / vague — AVOID
155 ### Anchor-breaking verbs — FORBIDDEN
158 ### Transition words — FORBIDDEN
161 ### Vulgar anatomy terms — AVOID in motion_prompt   ← KEEP (SFW 안전망)
164 ## Ambient Fallback
178 ## Lighting & Atmosphere Vocabulary
198 ## NSFW Levels (arousal-gated)                       ← STRIP
210 ### Composer level selection                         ← STRIP (NSFW Levels 하위)
215 ## Expressions
223 ## AHEGAO VERBATIM                                   ← STRIP
233 ## Audio Vocabulary
246 ## Failure Matrix (i2v Anchor Drift)
260 ## Anti-Patterns
273 ## Duration Constraint
279 ## Composer Decision Flow
296 ## Output Schema
```

**SFW fork 적용본**:
- 파일 rename: `src/wan_nsfw_i2v_prompting_guide.md` → `src/wan_i2v_prompting_guide.md` (원본 미이관, 사본을 새 이름으로 작성)
- 삭제 섹션 (3개):
  - `## NSFW Levels (arousal-gated)` (line ~198)
  - `### Composer level selection` (line ~210, NSFW Levels 하위 서브섹션)
  - `## AHEGAO VERBATIM` (line ~223)
- 유지 섹션: 그 외 전부. 일반 i2v 프롬프트 가이드(카메라/모션/조명/표정/오디오/실패 패턴/스키마)는 SFW에도 그대로 유효
- `### Vulgar anatomy terms — AVOID in motion_prompt` (line ~161)는 motion prompt에 vulgar anatomy가 들어가지 않게 하는 안전망이므로 SFW에도 유지
- 본문 안에 `arousal_level`, `nsfw_level` 같은 변수 참조나 inline 표현이 남아있다면 strip 단계에서 같이 제거
- [grok.py:46-55](../ella-telegram/src/grok.py#L46) `_GUIDE_PATH` 경로를 새 파일명으로 갱신 (또는 `config/grok_prompts.json`의 `video_system` 키로 통합 시 가이드 파일 자체 미사용)

### ComfyUI embedding prefix 재배치 상세

[src/comfyui.py:52-53](../ella-telegram/src/comfyui.py#L52) 원본:
```python
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos, embedding:illustrious/lazynsfw"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"
```

SFW fork 적용본:
```python
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazy-nsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"
```

효과: 기존에는 `lazynsfw`가 모든 이미지의 positive에 강제 prefix되어 NSFW 톤을 끌어올렸으나, 이제는 negative에 prefix되어 모든 이미지에서 NSFW 시각적 요소를 일관되게 억제한다.

### 결정 반영으로 단순해지는 작업

다음 항목은 **원본을 정리하지 않고 처음부터 안 가져오므로** 작업이 사라진다:
- `behaviors/char*.json` 11개 파일의 `arousal_speech`/`arousal_response`/`heat_cycle`/`curse_heat` strip 작업
- `persona/char*.json` 13개 파일의 sexual personality descriptor 제거 작업
- `images/char*.json` 11개 파일의 `body_nsfw` 필드 제거 작업
- `src/history.py`의 DB 마이그레이션 (`arousal`/`body_nsfw_json`/`heat_active` 컬럼 drop)
- `src/trait_pools.py`의 `BODY_NSFW_*` 5개 상수 / NSFW 씬 함수 strip 작업
- `src/handlers_imagegen.py`의 `/random NSFW` 분기 / `body_nsfw` 머지 / NSFW LoRA override strip 작업
- `src/handlers_char.py`의 arousal 스탯 통합 strip 작업
- `src/prompt.py`의 Layered Lust / arousal speech / arousal autonomy strip 작업

대신 위 모듈을 **새로 SFW 버전으로 작성**한다 (원본을 참조 자료로만 사용).

### Grok 프롬프트 외부화 결정

원본 [src/grok.py](../ella-telegram/src/grok.py)에는 5개의 프롬프트 상수가 하드코드되어 있다:

| 상수 | 라인 | 용도 |
|---|---:|---|
| `VIDEO_ANALYZER_PROMPT` | [79](../ella-telegram/src/grok.py#L79) | 비디오 safety_level + 포즈 tier 분류 (f-string) |
| `SYSTEM_PROMPT` | [159](../ella-telegram/src/grok.py#L159) | Danbooru 태그 생성 룰 |
| `RANDOM_SYSTEM_PROMPT` | [645](../ella-telegram/src/grok.py#L645) | `/random` 씬 프롬프트 |
| `CLASSIFY_SYSTEM_PROMPT` | [991](../ella-telegram/src/grok.py#L991) | 입력 분류 |
| `PARTIAL_EDIT_SYSTEM_PROMPT` | [1226](../ella-telegram/src/grok.py#L1226) | 캐릭터 부분 수정 |

추가로 [grok.py:46-55](../ella-telegram/src/grok.py#L46)는 `VIDEO_SYSTEM_PROMPT`를 `wan_nsfw_i2v_prompting_guide.md`에서 로드하도록 이미 외부화되어 있다.

**SFW fork 결정**: 5개 상수를 모두 `config/grok_prompts.json`으로 추출, `grok.py`가 import 시 로드. 코드 수정 없이 프롬프트 튜닝 가능. SFW fork에서는 백지 SFW 룰셋으로 새로 작성.

설계 노트:
- 단일 JSON 파일, 키 = 프롬프트 이름 (`system`, `video_analyzer`, `random`, `classify`, `partial_edit`, `video_system`).
- 값에 변수 보간이 필요한 경우 `${var}` placeholder 사용 + `string.Template.substitute()` (또는 다른 안전한 문법). f-string의 `{var}` + `.format()`은 JSON 내부의 중괄호(JSON 예시 출력 등)와 충돌하므로 비추천.
- 로딩 실패 시 fallback 문자열 두지 않고 fail-fast.
- `VIDEO_SYSTEM_PROMPT`는 SFW i2v 가이드를 새로 작성해 같은 JSON에 포함하거나, 별도 마크다운 파일로 유지하되 경로를 JSON 또는 env에서 받도록.

### 결정 반영 후에도 유지되는 작업

- [src/grok.py](../ella-telegram/src/grok.py) — Danbooru 룰 + VIDEO_ANALYZER 백지 재작성 + 5개 프롬프트 상수 외부화 (♻️ + 🆕 `config/grok_prompts.json`)
- [config/system_prompt.json](../ella-telegram/config/system_prompt.json) — master_prompt 재작성 (♻️)
- [src/input_filter.py](../ella-telegram/src/input_filter.py) — 미성년자 필터 그대로 이관 (✅)
- [src/intent_router.py](../ella-telegram/src/intent_router.py) — NSFW 매치 0이므로 거의 그대로 이관 (✅)
- [src/comfyui.py](../ella-telegram/src/comfyui.py) — embedding prefix 두 줄 변경 (✂️ MOVE) 외 대부분 이관
- [src/watchdog.py](../ella-telegram/src/watchdog.py), [src/llm.py](../ella-telegram/src/llm.py), [src/llm_queue.py](../ella-telegram/src/llm_queue.py), [src/rate_limiter.py](../ella-telegram/src/rate_limiter.py), [src/summary.py](../ella-telegram/src/summary.py), [src/token_counter.py](../ella-telegram/src/token_counter.py), [src/profile_keys.py](../ella-telegram/src/profile_keys.py), [src/logging_config.py](../ella-telegram/src/logging_config.py), [src/bot.py](../ella-telegram/src/bot.py), [src/grok_search.py](../ella-telegram/src/grok_search.py), [src/video.py](../ella-telegram/src/video.py) — NSFW 매치 0 또는 미미. 거의 그대로 이관 (✅)
- ComfyUI 워크플로우 + LoRA preset 검토 (🔍)
- `src/danbooru_prompting_guide.md` SFW 부분만 추출 (🔍)
- `.env.example` 정리 (✂️)

---

## 1. 소스 코드 (`src/*.py`)

전체 16,493 lines 중 NSFW 키워드(nsfw/arousal/발정) 매치 라인 수:

| 파일 | LOC | NSFW 매치 | 권장 조치 | 영향도 |
|---|---:|---:|---|---|
| [src/grok.py](../ella-telegram/src/grok.py) | 2,042 | 129 | ♻️ REWRITE | 🔴 매우 큼 |
| [src/history.py](../ella-telegram/src/history.py) | 2,078 | 62 | ✂️ STRIP (DB 스키마 포함) | 🔴 매우 큼 |
| [src/handlers_imagegen.py](../ella-telegram/src/handlers_imagegen.py) | 1,611 | 77 | ✂️ STRIP | 🔴 매우 큼 |
| [src/handlers_char.py](../ella-telegram/src/handlers_char.py) | 1,503 | 44 | ✂️ STRIP | 🔴 매우 큼 |
| [src/handlers_main.py](../ella-telegram/src/handlers_main.py) | 1,066 | 17 | ✂️ STRIP | 🟡 중간 |
| [src/prompt.py](../ella-telegram/src/prompt.py) | 749 | 26 | ✂️ STRIP | 🟡 중간 |
| [src/trait_pools.py](../ella-telegram/src/trait_pools.py) | 818 | 50 | ✂️ STRIP | 🟡 중간 |
| [src/pose_scene_classifier.py](../ella-telegram/src/pose_scene_classifier.py) | 395 | 18 | 🗑️ DELETE 또는 🔇 DISABLE | 🟢 작음 |
| [src/pose_motion_presets.py](../ella-telegram/src/pose_motion_presets.py) | 361 | 11 | ✂️ STRIP | 🟢 작음 |
| [src/video_context.py](../ella-telegram/src/video_context.py) | 81 | 4 | ✂️ STRIP | 🟢 작음 |
| [src/comfyui.py](../ella-telegram/src/comfyui.py) | 606 | 1 | ✂️ STRIP (1라인 embedding) | 🟢 매우 작음 |
| [src/intent_router.py](../ella-telegram/src/intent_router.py) | 195 | 0 | ✅ 유지 | — |
| [src/input_filter.py](../ella-telegram/src/input_filter.py) | 170 | 0 | ✅ 유지 (미성년자 필터는 SFW에도 필요) | — |
| [src/watchdog.py](../ella-telegram/src/watchdog.py) | 175 | 0 | ✅ 유지 | — |
| [src/video.py](../ella-telegram/src/video.py) | 338 | 0 | ✅ 유지 | — |

### 1.1 `src/grok.py` — NSFW 프롬프트 어셈블리의 핵심
- `SYSTEM_PROMPT` (라인 ~159–250): Danbooru 태그 생성 룰
  - **Rule 8 / 8-OVERRIDE / 8-NSFW**: arousal+대화 맥락 기반 콘텐츠 레벨 판정 — 옷 벗기기, 성행위 태그
  - **Rule 9 / 9-MALE_NUDITY / 9-2 multi-person**: 성행위 클로스업, 다인 성행위 룰
  - **Rule 10**: `adult` 태그 강제, 미성년 감지 시 `BLOCKED`
  - **TEAR RULE** (라인 193–199): 쾌락의 눈물 금지 룰
  - 조치: ♻️ 룰 8/9/9-2 재작성 — "옷은 항상 풀세트, 신체 노출/성행위/체액 태그 전면 금지"; Rule 10의 BLOCKED 분기는 `input_filter.py`로 이관
- `VIDEO_ANALYZER_PROMPT` (라인 ~79–157): `safety_level` 5단계 분류 (SFW/SUGGESTIVE/NSFW/EXPLICIT/BLOCKED)
  - 조치: ♻️ `safety_level`을 항상 `SFW`로 하드코딩, pose tier 선택 로직 제거
- `VIDEO_SYSTEM_PROMPT` (라인 ~46–55): `wan_nsfw_i2v_prompting_guide.md` 로드
  - 조치: 🗑️ 가이드 파일 자체 삭제, SFW i2v 가이드로 대체 또는 제너릭 모션 가이드만 사용
- `[arousal:N]` / `[RELIEF]` 토큰 핸들링: 프롬프트 입력에서 흥분 스탯과 해소 신호 처리
  - 조치: ✂️ 토큰 자체를 입력에서 제거하고 파서 무시

### 1.2 `src/history.py` — Arousal 시스템의 데이터 계층
- **DB 스키마 (라인 ~276, ~361)**:
  - `character_stats` 테이블에 `arousal INTEGER DEFAULT 0`
  - `body_nsfw_json TEXT` 컬럼 (nipple/pubic/genital/anus/fluids JSON 저장)
- **기본값 (라인 14–25)**: 캐릭터별 기본 arousal=0
- **Stat delta (라인 30)**: `"arousal": {"up": 10, "down": -10}`
- **Arousal decay 로직 (라인 1553–1601)**: `_apply_arousal_decay()` — 시간 기반 흥분 감소, 저주 발정(curse heat) 중에는 감소 정지
- **메모리 캐시 (라인 1545)**: 캐시 객체에 arousal/heat 필드 포함
- 조치: ✂️
  - 마이그레이션 스크립트로 `arousal`, `body_nsfw_json`, `heat_active` 컬럼 drop (또는 새 fork DB 시작 시 스키마에서 빼기)
  - `_apply_arousal_decay()` 및 호출부 전부 제거
  - 기본값 dict에서 `arousal` 키 삭제, `STAT_DELTAS`에서도 제거

### 1.3 `src/handlers_imagegen.py` — `/random NSFW` & body_nsfw 머지
- 라인 41, 75, 88–100: `/random NSFW` 인라인 버튼 + dual-mode 분기
  - `roll_nsfw_scene()` / `roll_sfw_scene()` 임포트
  - 조치: ✂️ NSFW 버튼/콜백 제거, SFW 경로만 남김
- 라인 296, 325, 532, 548, 561: `body_nsfw` 필드 머지 (캐릭터 저장 상태 → SFW body 태그와 결합)
  - 조치: ✂️ `body_nsfw` 필드/머지 제거
- 라인 823–1030: random callback handler dual-path
  - 조치: ✂️ NSFW mode branch + 내부 LoRA 오버라이드 전부 제거
- 라인 932–952: NSFW 씬에서 `lora` section + trigger 적용
  - 조치: ✂️ `nsfw_lora_overrides` / `nsfw_lora_trigger` 삭제

### 1.4 `src/handlers_char.py` — Arousal 스탯 통합
- 라인 ~150–450: `update_character_stats()` arousal delta, heat cycle 트리거(캐릭터 발정), arousal 임계값별 IMAGE_AUTONOMY (>30 → 📷 버튼, >60 → 자동 전송)
- 라인 ~550–650: arousal 값을 Grok 태그 생성기에 `[arousal:N]`로 주입
- 라인 ~700–900: `[RELIEF]` 시그널 처리 + climax 후 arousal 리셋
- 조치: ✂️ arousal/heat/RELIEF 관련 코드 전부 제거; `fixation+mood+location`만 남김

### 1.5 `src/handlers_main.py` — `/scene` admin 명령
- 라인 946–1003: `/scene [key|off|list|status]` admin 전용 NSFW/SFW 씬 강제 오버라이드
  - `set_forced_nsfw_scene()`, `list_nsfw_scene_keys()`, `get_forced_nsfw_scene()` 호출
- 조치: ✂️ NSFW 분기 제거 (SFW 강제 오버라이드만 유지)

### 1.6 `src/prompt.py` — 행동 레이어 선택
- 라인 186, 451–460, 552–560, 595–730: arousal 기반 IMAGE_AUTONOMY 스케일링 (0/30/60/80 cutoff), arousal speech, arousal response, **Layered Lust** (char09 박수연 3-layer 발정 구조)
- 라인 602–655: "Layered Lust" — surface restraint → deep desire 3 단계
- 조치: ✂️ Layered Lust 전체 블록 삭제; `IMAGE_AUTONOMY=1` 하드코딩; arousal 분기 전부 제거

### 1.7 `src/trait_pools.py` — NSFW 신체 태그 + 씬 풀
- 라인 228–272: `BODY_NSFW_NIPPLE`, `BODY_NSFW_PUBIC`, `BODY_NSFW_GENITAL`, `BODY_NSFW_ANUS`, `BODY_NSFW_FLUIDS` (60+ 태그)
  - 조치: 🗑️ 5개 상수 전부 삭제
- 라인 400–488: `UNDERWEAR_SETS`
  - 일부 명백한 NSFW 키: `crotchless`, `cupless_set`, `open_crotch`, `pasties_only`, `c_string`
  - 조치: ✂️ 노출형 세트 제거, 일반 bra/panties 세트만 유지 또는 속옷 자체를 일반 의상에 통합
- 라인 641–819: NSFW 씬 로딩 & 롤링
  - `_load_nsfw_scenes()`, `roll_nsfw_scene()`, `NSFW_SCENES` 글로벌
  - `FORCE_NSFW_SCENE` env var
  - `set_forced_nsfw_scene()`, `list_nsfw_scene_keys()`
  - 조치: ✂️ NSFW 함수/글로벌 전부 삭제, SFW 버전만 유지

### 1.8 `src/pose_scene_classifier.py` — NSFW 씬 분류기 (전체가 NSFW)
- 대화 → NSFW 씬 키 매칭 분류기 (`hetero_sex`, `toy_solo`, `solo_nsfw`, `mating_press`, `nipple_play`, `fellatio`, `anal_position`, `squirting`, `bondage`, `double_penetration`, `creampie` 등)
- SFW 맥락 → null 반환 (Rule 1)
- `NSFW_SCENES` 카탈로그를 catalog로 사용
- 조치: 🗑️ 파일 자체 삭제 또는 🔇 `POSE_CLASSIFIER_ENABLED=0`으로 비활성. 새 fork에서는 호출 부위까지 정리하는 것을 권장.

### 1.9 `src/pose_motion_presets.py`
- specificity: `specific`(포즈 전용) vs `general_nsfw`(NSFW 폴백) 2-tier 구조
- 조치: ✂️ `general_nsfw` 폴백 tier 제거; `text-only` tier만 유지

### 1.10 `src/video_context.py`
- 4 lines NSFW 매치: `nsfw_scene_key`를 비디오 생성 컨텍스트에 저장
- 조치: ✂️ `nsfw_scene_key` 키 삭제

### 1.11 `src/comfyui.py`
- 라인 52: `EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos, embedding:illustrious/lazynsfw"`
  - `lazynsfw` embedding이 모든 prompt에 prefix로 들어감
- 조치: ✂️ `lazynsfw` 부분 제거 → `"embedding:illustrious/lazypos"` (또는 SFW 전용 embedding으로 교체)

### 1.12 `src/input_filter.py` (170 lines, 0 NSFW 매치이지만 보호 로직 포함)
- 라인 37–43: 미성년자/loli/shota/age 0–18 차단 정규식 (한국어 "아동/어린이/소아/미성년" 포함)
- 조치: ✅ 그대로 유지 — SFW 버전에서도 안전망으로 필요

---

## 2. 설정 파일 (`config/*.json`)

### 2.1 `config/nsfw_scenes.json` (488 lines, 100% NSFW)
- 20+ 명시적 성행위 씬 카탈로그 (`hetero_sex`, `toy_solo`, `solo_nsfw`, `mating_press`, `reverse_suspended_congress`, `nipple_play`, `sex_machine`, `fellatio`, `anal_position`, `squirting`, `bondage`, `double_penetration`, `creampie` 등)
- 각 씬에 `pose_pool`, `camera_pool`, `scene_tags` (vaginal_penetration, ejaculation 등)
- 조치: 🗑️ 파일 전체 삭제 (또는 별도 백업, fork repo로 가져오지 않음)
- 부수 파일: `config/nsfw_scenes.json.bak` 도 동일하게 가져오지 않음

### 2.2 `config/sfw_scenes.json` (1,339 lines)
- NSFW 키워드 직접 매치 0건이지만, 포즈/카메라 풀이 SFW 의도와 다른 항목이 있을 수 있음
- 조치: 🔍 AUDIT — 50+ 엔트리 한 줄씩 검토, suggest/tease/lingerie/underwear-focused 등 경계 항목 제거 또는 톤다운

### 2.3 `config/lora_presets.json` (783 lines, 7 NSFW 매치)
- `specificity: "specific"` (포즈 전용) vs `"general"` (catch-all NSFW LoRA) 듀얼 tier 구조
- NSFW 전용 LoRA: `mating_press`, `reverse_suspended_congress`, `sex_machine`, `fellatio`, `anal_position`, `squirting`, `creampie`, `double_penetration` 등
- Tier 2 fallback: `general_nsfw` LoRA preset
- 조치: ✂️ NSFW 전용 LoRA preset 전부 삭제, 유틸성 LoRA(스타일/조명/품질)만 유지

### 2.4 `config/pose_motion_presets.json` (66 lines, 4 NSFW 매치)
- 스키마: 각 preset에 `sfw` / `nsfw` / `explicit` tier 구조
- 조치: ✂️ `nsfw` / `explicit` tier dict 제거, `sfw` tier만 유지하거나 텍스트 fallback만 사용

### 2.5 `config/dasiwa_aio_defaults.json` (59 lines)
- `style=NSFW` LoRA preset 참조, `movement=(orgasm) LoRA` 참조
- 조치: ✂️ NSFW 스타일 LoRA / orgasm LoRA 참조 제거

### 2.6 `config/system_prompt.json` (5 NSFW 매치, 그러나 master_prompt 길이 큼)
- **Section 2 (PHOTO SENDING)**: `[SEND_IMAGE]` 트리거 시 명시적 행위 묘사 (penetration/oral/cum shot/masturbation/fingering/afterglow)
  - 조치: ♻️ "이미지 전송 시 SFW 시나리오만(일상/취미/풍경/표정/스타일/포즈) 묘사" 룰로 재작성
- **Section 5 (PHYSICAL REALISM NSFW)**: 친밀감 중 신체 감각 묘사(맥박/근육 긴장/신체 영역)
  - 조치: 🗑️ 섹션 전체 삭제
- **Section 5-1 (CLIMAX/RELIEF)**: `[RELIEF]` 태그, 절정 후 arousal 리셋
  - 조치: 🗑️ 섹션 전체 삭제
- 조치 종합: ♻️ master_prompt 재작성

### 2.7 `config/profile_keys.json` (21 lines, 0 매치)
- 조치: ✅ 유지

### 2.8 `config/CLAUDE.md`
- 조치: 🔍 AUDIT — config 폴더 가이드 문서이므로 NSFW 관련 설명 부분만 갱신

---

## 3. 캐릭터 데이터 (`behaviors/`, `persona/`, `images/`)

### 3.1 `behaviors/char*.json` — Arousal 행동 테이블
| 파일 | NSFW/arousal 매치 |
|---|---:|
| char01.json | 5 |
| char02.json | 5 |
| char03.json | 5 |
| char04.json | 5 |
| char05.json | 5 |
| char06.json | 5 |
| char07.json | 21 |
| char08.json | 24 |
| char09.json | 6 |
| char10.json | 5 |
| char_test.json | 5 |

각 파일에 다음 블록 존재 (정도 차이):
- `arousal_speech`: arousal 레벨별 NSFW 대화 템플릿
- `arousal_response`: arousal 스탯별 반응 패턴
- `heat_cycle`: 주기적 발정 (char06, char09에서 활성화)
- `mood_triggers`: 친밀감 컨텍스트 mood 전환
- `curse_heat`: char09 저주 발정 트리거

조치: ✂️ 11개 파일 모두에서 `arousal_speech`, `arousal_response`, `heat_cycle`, `curse_heat` 블록 제거. 기본 personality / speech_style / mood_list / stat_limits(단, arousal 한계는 빼기) 만 유지. char07/char08는 NSFW 비중이 가장 높으므로 더 신중한 검토 필요.

### 3.2 `persona/char*.json` — 캐릭터 카드
| 파일 | 매치 |
|---|---:|
| char01.json | 3 |
| char02.json | 4 |
| char03.json | 2 |
| char04.json | 4 |
| char05.json | 3 |
| char06.json | 1 |
| char07.json | 5 |
| char08.json | 2 |
| char09.json | 5 |
| char10.json | 3 |
| char_test.json | 1 |
| character.json | 2 |
| character_backup.json | 0 |

조치: 🔍 AUDIT — 외형/기본 personality는 유지, 성격 설명에 들어간 sexual descriptors 제거. char07/char09 우선 검토.

### 3.3 `images/char*.json` — 외형 태그
- 11개 파일 모두 `body_nsfw` 필드 1건씩 보유
- 조치: ✂️ 모든 파일에서 `body_nsfw` 필드 삭제, `appearance_tags` / `body_shape`만 유지 (단 `body_shape`도 noticeable cleavage 등 경계 표현은 일반화)

### 3.4 `character_card_schema.json`
- 조치: 🔍 AUDIT — `body_nsfw` 필드 정의가 있으면 스키마에서 제거

---

## 4. ComfyUI 워크플로우 (`comfyui_workflow/*`)

**스코프 주의**: checkpoint 파일명(모델 가중치)은 검토 대상 아님. **워크플로우 로직** 및 **NSFW 명시 LoRA 참조**만 검토.

| 파일 | 비고 |
|---|---|
| [comfyui_workflow/main_character_build.json](../ella-telegram/comfyui_workflow/main_character_build.json) | 🔍 AUDIT — checkpoint 외 LoRA 슬롯에 NSFW LoRA 참조 여부 확인 |
| [comfyui_workflow/main_character_build_highqual.json](../ella-telegram/comfyui_workflow/main_character_build_highqual.json) | 🔍 AUDIT — 동일 |
| [comfyui_workflow/main_character_build_archived.json](../ella-telegram/comfyui_workflow/main_character_build_archived.json) | 🔍 AUDIT — archived지만 사용 시 동일 |
| [comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json](../ella-telegram/comfyui_workflow/DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json) | 🔍 AUDIT — i2v 워크플로우, safety_level 게이팅 로직이 워크플로우 내부에 있는지 확인 |
| [comfyui_workflow/audiogen-workflow.json](../ella-telegram/comfyui_workflow/audiogen-workflow.json) | ✅ 오디오 (대상 외) |
| `comfyui_workflow/CLAUDE.md` | 🔍 NSFW 사용 가이드 부분 갱신 |

---

## 5. 문서 (`docs/`, root `*.md`, `src/*.md`)

### 5.1 `danbooru_tag_strategy.md` (14 KB, root)
- Section 10: "NSFW Danbooru 태그 변환 가이드"
- `rating:explicit`, NSFW negative prompt, 명시적 성행위 태그
- 조치: 🗑️ 파일 자체 삭제 또는 SFW 가이드로 대체

### 5.2 `src/wan_nsfw_i2v_prompting_guide.md` (20 KB)
- WAN 2.2 i2v용 NSFW 모션 프롬프트 가이드 — `grok.py`가 직접 로드
- 조치: 🗑️ 삭제 후 SFW i2v 모션 가이드로 대체 또는 grok.py에서 가이드 미참조로 변경

### 5.3 `src/danbooru_prompting_guide.md` (40 KB)
- 조치: 🔍 AUDIT — 명시적 NSFW 섹션만 제거, 일반 태그 가이드 부분은 유지

### 5.4 `docs/nsfw_rules.json` (5 KB)
- char01–05, char09의 sexual personality / trigger / kink / NSFW speech pattern
- 조치: 🗑️ 파일 전체 삭제

### 5.5 `docs/character_sheets.md` (15 KB)
- 조치: 🔍 AUDIT — arousal/NSFW 스탯 문서화 부분 제거

### 5.6 `docs/character_card_instruction.md` (25 KB)
- 조치: 🔍 AUDIT — `body_nsfw` 필드 설명 / arousal stat 문서화 제거

### 5.7 `docs/terms_of_service.md`
- 조치: ♻️ SFW 약관으로 재작성

### 5.8 `docs/video-improve1.md`
- 조치: 🔍 AUDIT

### 5.9 root `plan.md`, `plan_char_save_and_charbot_lora.md`, `plan_video_improve2.md`, `research.md`, `backlog.md`, `STATUS.md`
- 광범위한 NSFW 기능 로드맵 (LoRA tier, arousal-gated fallback, Layered Lust, CSAM 검출 등)
- 조치: 🔍 새 fork에는 가져가지 않음 (ella-chat-publish는 자체 plan/status 새로 작성)

### 5.10 root `CLAUDE.md` (50 KB)
- ella-telegram 전체 문서. NSFW 시스템 다수 기술
- 조치: ♻️ 새로 작성 (SFW용 ella-chat-publish CLAUDE.md를 별도 작성)

### 5.11 `src/CLAUDE.md`, `config/CLAUDE.md`, `comfyui_workflow/CLAUDE.md`, `deploy/CLAUDE.md`
- 조치: 🔍 NSFW 관련 가이드 부분만 갱신해서 가져옴

---

## 6. 환경 변수 / 설정 (`/.env.example`, `.env`)

### `.env.example` 라인 119–128
```
# NSFW Pose Scene Classifier (캐릭터 봇)
#POSE_CLASSIFIER_ENABLED=1
#POSE_CLASSIFIER_MODEL=grok-4-1-fast-non-reasoning
#POSE_CLASSIFIER_THRESHOLD=0.7
#POSE_CLASSIFIER_TIMEOUT=5
```

또한 `trait_pools.py`에서 사용:
- `FORCE_NSFW_SCENE` (옵션 env)
- `FORCE_SFW_SCENE` (옵션 env)

조치:
- 🗑️ `POSE_CLASSIFIER_*` 항목 전부 제거 (분류기 파일을 삭제하므로)
- 🗑️ `FORCE_NSFW_SCENE` 제거
- ✅ `FORCE_SFW_SCENE` 유지

`.env` (실 운영값)는 fork 시 가져오지 않음 (시크릿 + NSFW 강제 설정 가능성).

---

## 7. 도구/스크립트 (`tools/`, `scripts/`, `deploy/`)

### 7.1 `tools/generate_scene_descriptions_ko.py`
- NSFW 씬 한국어 설명 생성기로 추정
- 조치: 🔍 AUDIT — NSFW 씬 입력에만 동작하면 🗑️ 삭제, SFW 씬에도 쓰이면 SFW 입력만 사용하도록 ✂️

### 7.2 `tools/grok_*.json`, `tools/test_grok_*.py`
- Grok 비교 테스트 결과 — `grok_danbooru_results.json` 등 NSFW 태그 결과가 들어있을 수 있음
- 조치: 🔍 AUDIT — fork에 가져오지 않는 것 권장

### 7.3 `scripts/generate_job_facts.py`
- 직업 fact 생성 (SFW로 추정)
- 조치: 🔍 AUDIT (가벼운 검토만)

### 7.4 `deploy/`
- systemd unit, install.sh, runpod 배포 스크립트
- 조치: 🔍 AUDIT — `deploy/runpod-video/`가 NSFW i2v용 LoRA 체크포인트를 다운로드하는 로직을 포함하면 SFW 모델 다운로드로 변경

---

## 8. 정리되지 않은 데이터 폴더

- `data/`, `output/`, `logs/`, `images/` (생성 결과물 폴더)
  - 조치: 🗑️ fork 시 가져오지 않음 (런타임 산출물)

---

## 9. 요약 통계

- **NSFW 키워드 매치 라인 수 합계 (소스)**: ~440 lines
- **NSFW 키워드 매치 라인 수 합계 (config/json)**: ~80 lines
- **DELETE 대상 파일**: 5건 (`config/nsfw_scenes.json`, `config/nsfw_scenes.json.bak`, `docs/nsfw_rules.json`, `src/wan_nsfw_i2v_prompting_guide.md`, `danbooru_tag_strategy.md`)
- **DELETE 또는 DISABLE 대상 파일**: 1건 (`src/pose_scene_classifier.py`)
- **REWRITE 대상 파일**: 4건 (`src/grok.py`, `config/system_prompt.json`, `docs/terms_of_service.md`, root `CLAUDE.md`)
- **STRIP 대상 파일**: 약 25건
- **AUDIT 대상 파일**: 약 30건
- **추정 변경 라인 수**: 2,000–2,500 lines

---

## 10. SFW Fork 작업 권장 순서

1. **새 디렉터리 골격 생성** (`/Users/junheeyoon/Code/ella-chat-publish`):
   - 원본의 디렉터리 구조 복제, but 제외 항목은 처음부터 안 가져옴 (NSFW 데이터/문서/시크릿)
2. **DB 스키마부터 정리**: `history.py`에서 `arousal`, `body_nsfw_json`, `heat_active` 컬럼 제거 → 마이그레이션이 필요 없는 새 DB로 시작
3. **`trait_pools.py` 정리**: BODY_NSFW_* / NSFW 씬 함수 제거 → 다른 모듈이 이를 import하지 않게 됨
4. **`pose_scene_classifier.py` 삭제** + 호출부 정리 (handlers_imagegen.py, handlers_main.py, prompt.py)
5. **`grok.py` 룰 재작성**: SYSTEM_PROMPT의 Rule 8/9/9-2/10 + VIDEO_ANALYZER_PROMPT의 safety_level 분기
6. **`system_prompt.json` 재작성**: master_prompt section 2/5/5-1
7. **`handlers_*` 정리**: arousal/heat/RELIEF/random NSFW 분기 전부 제거
8. **`prompt.py` 정리**: Layered Lust / arousal autonomy / arousal speech 제거
9. **캐릭터 데이터 정리**: behaviors/persona/images의 NSFW 필드 제거
10. **`comfyui.py` embedding prefix 정리** (`lazynsfw` 제거)
11. **`.env.example` 정리** + 새 `CLAUDE.md` 작성
12. **End-to-end 테스트**: 캐릭터 챗 / 이미지 생성 / 비디오 생성이 모두 SFW만 산출하는지 검증
13. **Negative test**: NSFW 트리거 입력(예: "옷 벗어줘") 입력 시 SFW로 강건하게 거절/우회하는지 확인

---

## 11. 미해결/추가 검토 필요

- [ ] `src/danbooru_prompting_guide.md` 내부의 SFW vs NSFW 섹션 비율 정확히 측정
- [ ] `comfyui_workflow/main_character_build*.json` 워크플로우 노드별 LoRA 슬롯 검토
- [ ] `deploy/runpod-video/` 모델 다운로드 스크립트의 i2v 모델이 NSFW 전용인지 확인
- [ ] `tools/generate_scene_descriptions_ko.py`의 입력/출력 분석 (재사용 가능 여부)
- [ ] character_card_schema.json의 NSFW 필드 정의 위치
- [ ] `images/*.json`의 `body_shape` 필드가 SFW 안전한지 (예: noticeable cleavage 표현)
- [ ] `behaviors/char07.json`, `behaviors/char08.json` (NSFW 비중 최상위) 별도 정밀 검토
