# `persona/` — Per-character persona cards (SFW fork)

캐릭터의 *정체성*을 보유하는 JSON 카드. SillyTavern V2 character card 포맷의 SFW-only 변형으로, `character_card_schema.json` (repo root)이 스키마를 정의한다. `src/prompt.py` 가 활성 캐릭터의 persona 카드를 읽어 system_prompt에 description / personality / scenario / mes_example 등을 주입한다.

## 파일 명명 규칙

`charNN.json` (behaviors / images 와 같은 번호 공유). 현재 fork:

| 파일 | 캐릭터 | 비고 |
|---|---|---|
| `char05.json` | Jiwon Han — 31세 임원 비서 (영어로 응답) | i18n 단계에서 char05 만 남기고 나머지 (char01-04, char06-09) 모두 삭제 |

## 핵심 필드

`character_card_schema.json` 정의 기준. 필수: `name`, `description`, `first_mes`, `system_prompt`. 그 외는 빈 값 허용.

| 필드 | 의미 |
|---|---|
| `name` | 캐릭터 이름. 프롬프트 내 `{{char}}` 매크로로 치환됨 |
| `profile_summary_ko` | 한 줄 한국어 요약 (UI/관리용) |
| `description` | 외모/배경/성격 자유 서술 (영어 OK, SFW 한정) |
| `personality` | 성격 키워드/짧은 문장 |
| `scenario` | 현재 RP 상황 설정 |
| `first_mes` | 첫 인사 메시지 |
| `mes_example` | `<START>` 구분 few-shot 대화 예시 |
| `system_prompt` | Speech style / Response Rules / Tone Guide / Emoji Rules — 캐릭터의 코어 지시문 |
| `post_history_instructions` | 히스토리 뒤에 붙는 리마인더 |
| `creator_notes` | 제작 메모 (프롬프트 미주입) |
| `anchor_image` | ComfyUI IPAdapter FaceID 레퍼런스 파일명 |
| `image_prompt_prefix` / `image_negative_prefix` | 이미지 생성 시 positive/negative 프리픽스 |
| `stat_personality` | fixation의 캐릭터별 의미/증감 조건 설명 (프롬프트 주입) |
| `stat_moods` | 표현 가능한 mood 문자열 배열 |
| `mood_behaviors` / `mood_triggers` | `behaviors/` 와 같은 의미 — persona 측에 두는 경우 짧은 inline 사용 |
| `proactive_behaviors` | 짧은 능동 행동 요약 (보통 "Follows behaviors/ rules based on fixation level." 류) |
| `interests` | 능동 탐구 주제 배열 |
| `discovery_hint_template` | 미지 토픽 탐색 힌트. 빈 문자열이면 기본 DISCOVERY_TOPICS 템플릿 사용 |
| `jobs` | 직업 키 배열. `jobs/<key>.json` 매칭용 (현재 fork의 jobs/ 폴더 데이터는 비어 있음) |
| `stat_limits` | `{ "fixation": { "up": N, "down": -N } }` — 캐릭터별 fixation 변화 한도 |

## 매크로

- `{{user}}` — 런타임 화자 사용자. chat 처리 시 치환.
- `{{char}}` — `name` 필드 값으로 치환.

`description`, `scenario`, `first_mes`, `mes_example`, `system_prompt`, `proactive_behaviors`, `mood_behaviors`, `interests` 등 어디에서나 사용 가능.

## SFW invariant

- 성적 personality descriptor 부재. 원본 카드의 sexual personality / kink / arousal speech / arousal response 류 필드는 fork 스키마에 없으며, `additionalProperties: false`로 추가 자체가 차단된다.
- `body_nsfw_json` 류 필드 없음 (이미지 생성 외형은 `images/charNN.json`에서 다루고, 그쪽에도 노출 태그는 미존재).
- `system_prompt`에 성행위/노출/체액 관련 지시문 포함 금지. SFW 안전망은 `config/grok_prompts.json`의 `system` Danbooru 룰과 `config/sfw_denylist.json`로 다중 방어된다.

## 새 캐릭터 추가 절차

1. `charNN` 번호 선정 (behaviors / images 와 동일 번호)
2. `persona/charNN.json` 작성 — 최소 4개 필수 필드는 채우고, 권장: `mes_example` 3블록 이상, `stat_moods` 4-5개, `interests` 3개 이상
3. `character_card_schema.json`으로 검증 — 필드명 오타 / 타입 미스매치 시 schema 위반
4. `docs/character_card_instruction.md`의 SFW 작성 가이드를 따른다
