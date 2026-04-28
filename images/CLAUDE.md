# `images/` — Per-character image-config cards (SFW fork)

캐릭터의 이미지 생성용 외형/체형 태그 정의 JSON. ComfyUI 호출 시 `src/handlers_imagegen.py` → `src/grok.py` 가 이 파일을 읽어 캐릭터 외형 일관성을 유지하는 Danbooru 태그 풀을 positive 프롬프트에 주입한다.

## 파일 명명 규칙

`charNN.json` (behaviors / persona 와 같은 번호 공유). 현재 fork:

| 파일 | 캐릭터 | Phase |
|---|---|---|
| `char01.json` ~ `char08.json` | Phase 3-5에서 신규 작성된 SFW 캐릭터 8명 | 3-5 |
| `char09.json` | 오하늘 — 수줍은 꽃집 점원 | char09 추가 |

## 핵심 필드 (Danbooru tag 형식)

| 필드 | 의미 |
|---|---|
| `char_id` | `charNN` 자기 식별자 |
| `appearance_tags` | 얼굴/머리/피부 등 항상 적용되는 외형 태그. 콤마 구분 Danbooru 태그 문자열 |
| `clothing` | 기본 의상 셋 (상의/하의/겉옷/신발) |
| `alt_outfit` | 대체 의상 셋 (work-mode, off-day 등) |
| `underwear` | 속옷 셋 (전신 가운/원피스 등 underwear가 안 비치는 의상에서는 visual 태그로 안 들어감) |
| `body_shape.size` | 키/체격 키워드 (예: `average_height`, `slim`) |
| `body_shape.build` | 살집/근육감 키워드 |
| `body_shape.curve` | 허리 라인 키워드 |
| `body_shape.accent` | 부분 강조 태그 (예: `collarbone`) — framing 조건부 |
| `body_shape.ass` | 엉덩이 라인 태그 — framing 조건부 |
| `breast.size` | 가슴 사이즈 (예: `medium_breasts`) |
| `breast.feature` | 가슴 디테일 — framing 조건부 |

`body_shape.accent` / `body_shape.ass` / `breast.feature`는 카메라 각도(framing)에 따라 조건부로만 적용된다. 자세한 적용 룰은 `config/grok_prompts.json` 의 `random` Rule (positive 프롬프트 조립 단계)을 참고한다.

## SFW invariant

- **`body_nsfw` 필드 미존재.** Phase 2D D2 에서 `src/grok.py` 의 legacy `body_nsfw` load 코드가 제거되어 카드에 추가해도 어디서도 읽히지 않는다.
- 모든 `body_shape` / `breast` 값은 외형 일관성 키워드만 포함하며, 노출/체액/성행위 관련 태그는 사용하지 않는다.
- 현 8+1 캐릭터들은 `body_shape` 가 의도적으로 conservative — `slim` / `average_height` 위주로, 과장된 체형 표현을 피한다.
- ComfyUI 측 안전망: `EMBEDDING_NEG_PREFIX` 의 `lazynsfw` 임베딩이 모든 렌더에서 NSFW 시각 요소를 능동 억제 (`src/comfyui.py:47-48`).

## 빈 템플릿

```json
{
  "char_id": "charNN",
  "appearance_tags": "1girl, solo, adult, korean_woman, ...",
  "clothing": "...",
  "alt_outfit": "...",
  "underwear": "...",
  "body_shape": {
    "size": "average_height",
    "build": "slim",
    "curve": "natural_waist",
    "accent": "",
    "ass": ""
  },
  "breast": {
    "size": "medium_breasts",
    "feature": ""
  }
}
```
