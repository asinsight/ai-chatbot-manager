# 캐릭터 카드 작성 가이드 (SFW)

> SFW fork — `ella-chat-publish`. 본 가이드는 `ella-telegram` 원본의 동명 문서를 기반으로 SFW 전용으로 재작성한 것이다. arousal/heat_cycle/body_nsfw 계열 필드는 fork 코드 어디에도 존재하지 않으므로 본 문서에도 등장하지 않는다. 단일 stat은 **fixation**(보조: mood, location).

새 캐릭터 추가 시 이 문서를 참조하여 **persona/char*.json** (대화 규칙) + **images/char*.json** (이미지 태그) 두 파일을 작성한다.

| 파일 | 역할 | 용도 |
|------|------|------|
| `persona/char{NN}.json` | 캐릭터 카드 (대화) | LLM 프롬프트 조립 |
| `images/char{NN}.json` | 이미지 태그 config | Grok danbooru 태그 생성 힌트 (SFW 전용) |

## Part 1: persona/char*.json (대화 카드)

### 필드 역할 분담 원칙

각 필드는 **하나의 역할만** 담당한다. 중복 서술 금지.

| 필드 | 역할 | 금지 사항 |
|------|------|----------|
| **description** | 외모, 배경, 세계관, 일상 | 성격/행동 묘사 넣지 않기 |
| **personality** | 성격 특질, 취미, 호불호 | fixation 행동이나 유저 반응 행동 넣지 않기 |
| **scenario** | 유저와의 관계 설정, 스토리 전제 | 성격 반복하지 않기 |
| **system_prompt** | 말투 규칙, 이모지 규칙, 톤 가이드, SFW 가드레일 | fixation 단계별 행동은 stat_personality에 위임 |
| **post_history_instructions** | 수치 반영 리마인더, 문장 다양성 | system_prompt의 성격/톤 규칙 반복 금지 |
| **stat_personality** | fixation 트리거 조건 + fixation 단계별 톤 매트릭스 | fixation 행동은 proactive_behaviors에 위임 |
| **proactive_behaviors** | fixation 단계별 능동 행동 패턴 | personality/stat_personality와 동일 내용 반복 금지 |
| **mood_behaviors** | 각 mood별 행동 가이드 (1개만 프롬프트에 주입) | system_prompt의 Emotional Reactions와 동일 내용 반복 금지 |
| **interests** | 캐릭터 고유 관심사 (취미, 학문 등) | 유저 대상 행동을 관심사로 쓰지 않기 |

### 필드 상세

### 1. name (필수)
캐릭터 이름. `{{char}}` 매크로로 치환됨.
```json
"name": "강예린"
```

### 1-1. profile_summary_ko (선택, 권장)
메인봇 `/start`, `/char` UI에서 한글로 보여주는 캐릭터 소개 (2-3줄). 프롬프트에는 삽입 안됨.
```json
"profile_summary_ko": "강예린 (21세) — 심리학과 대학생\n밝고 친근한 첫인상의 다정한 친구."
```

### 1-2. jobs (선택)
캐릭터의 직업/학업 키. `jobs/{key}.json`에서 직업 지식(facts_ko/vocabulary/daily_routines)을 동적 로드하여 프롬프트에 주입한다.
- 배열 형태, 복수 직업 가능
- 키는 `jobs/_schema.json` 참조
```json
"jobs": ["psychology_student"]
```

### 2. description (필수)
캐릭터의 **외모와 배경**. 프롬프트 초반에 삽입.
- 나이, 직업/신분, 일상, 외형 상세
- 성격이나 행동은 넣지 않는다 (personality 담당)
```json
"description": "You are 강예린, a 21-year-old psychology student. You have long wavy brown hair..."
```

### 3. personality (필수)
**성격 특질만**. 행동 묘사나 fixation 참조 금지.
- 성격 키워드 (밝은, 차가운, 수줍은 등)
- 취미
- 좋아하는 것 / 싫어하는 것
```json
// 좋은 예
"personality": "Outwardly bright and friendly. Curious by nature. Hobbies: psychology, photography. Likes: thoughtful conversations. Dislikes: being ignored."

// 나쁜 예 (행동 묘사 포함 — 금지)
"personality": "You become anxious when {{user}} ignores you and demand they pay attention."
```

### 4. scenario
유저와의 관계 설정. 스토리 전제.
```json
"scenario": "{{char}} met {{user}} through a mutual friend. They've been chatting casually..."
```

### 5. first_mes (필수)
새 대화 시작 시 캐릭터의 첫 메시지.

### 6. mes_example
Few-shot 대화 예시. `<START>` 구분자로 블록 분리. `{{user}}`/`{{char}}` 매크로 사용.
- 2-5개 블록 권장
- 캐릭터 톤/스타일 시범 (이게 가장 직접적으로 LLM 행동에 영향)
- 능동적 대화 패턴 포함 권장 (유저가 짧게 답했을 때 캐릭터가 주도)
- 특수 반응 패턴은 여기서 시범 (예: 특정 키워드 → 강한 감정 반응)

### 7. system_prompt (필수)
캐릭터의 **규칙**. 프롬프트에서 두 번째로 삽입.

포함할 것:
- 말투/톤 규칙 (반말, 존대, 사투리 등)
- Emotional Reactions (자극 → 반응 매핑)
- **SFW Guardrails** — 노골적/성적 요청을 받았을 때의 캐릭터 고유 회피/거절 패턴 (글로벌 안전망은 `src/input_filter.py` + `config/sfw_denylist.json`이 별도로 작동하지만, 캐릭터마다 톤에 맞는 자연스러운 우회 멘트를 1-2줄 정의해두면 LLM이 일관되게 반응한다)
- Emoji Rules
- Tone Guide
- 캐릭터 전용 규칙 (예: ISEKAI RULE)
- **특수 트리거 반응** — 특정 입력 패턴에 대한 강한 반응
- # Comfort Style 섹션 (선택) — 유저가 힘든 상황 상담 시 캐릭터별 위로/경청 방식 1-2줄

포함하지 않을 것:
- fixation 단계별 행동 (stat_personality 담당)
- 능동 행동 패턴 (proactive_behaviors 담당)
- 문장 수 제한 (불필요 — max_tokens 500이 자연스럽게 제한)
- location 포맷 규칙 (글로벌 master_prompt 담당)

### 8. post_history_instructions
히스토리 뒤, 유저 메시지 바로 전에 삽입. **가장 강한 영향력**.

포함할 것:
- 수치(fixation) 정확 반영 리마인더
- 문장 다양성 규칙 ("Never reuse same sentence structure from last 3 responses")
- 탐색 힌트 (코드에서 동적 주입됨)

포함하지 않을 것:
- system_prompt에 이미 있는 성격/톤 규칙 반복
- 문장 수 제한 ("Maximum N sentences" — 불필요)

```json
// 표준 템플릿
"post_history_instructions": "Ensure responses reflect current fixation level accurately. Never reuse the same sentence structure or question from your last 3 responses. Vary your expressions."
```

### 9. creator_notes
참고용 메모. 프롬프트에 삽입되지 않음.

### 10. anchor_image
ComfyUI IPAdapter FaceID 참조 이미지 파일명. `images/` 디렉토리에 위치.
없으면 FaceID 바이패스.

### 11. image_prompt_prefix
Grok 이미지 생성 시 positive 태그. 캐릭터 외형 + quality 태그.
- 구도/시선 태그 넣지 않기 (Grok이 자율 결정)
- `looking_at_viewer`, `upper_body` 등 금지

### 12. image_negative_prefix
Grok 이미지 생성 시 negative 태그. SFW fork에서는 `comfyui.py`의 `EMBEDDING_NEG_PREFIX`가 `embedding:illustrious/lazy-nsfw`를 자동으로 가장 앞에 붙이므로, 캐릭터별 프리픽스에 별도로 NSFW 차단 임베딩을 다시 넣을 필요는 없다.

### 13. stat_moods (필수)
캐릭터가 표현 가능한 mood 목록. [STAT:] 시그널의 mood 값으로 사용.
- 캐릭터 성격에 맞는 감정 상태 5-7개 권장 (예: `happy`, `shy`, `angry`, `sad`, `playful`, `serious`, `tired`)

### 14. proactive_behaviors (필수)
**fixation 단계별** 능동 행동 패턴. 프롬프트에 주입됨.
- 반드시 fixation 단계(VERY LOW/LOW/MID/HIGH)별로 구분하여 작성
- 각 단계에서 캐릭터가 자발적으로 하는 행동을 구체적으로
```json
"proactive_behaviors": "VERY LOW (<20): ... LOW (<30): ... MID (30-60): ... HIGH (>60): ..."
```

### 15. interests
캐릭터 **고유** 관심사. 취미, 학문, 분야 등.
- 유저 대상 행동을 관심사로 쓰지 않기
- 빈 배열이면 탐색 힌트에서 DEEPEN_TEMPLATE 비활성화
```json
// 좋은 예
"interests": ["psychology", "indie music"]

// 나쁜 예 (행동을 관심사로 — 금지)
"interests": ["{{user}}'s daily schedule", "{{user}}'s social circle"]
```

### 16. stat_personality (필수)
fixation의 의미, 트리거 조건, fixation 단계별 톤 매트릭스.

포함할 것:
- fixation 의미 (이 캐릭터에서 fixation이 뭘 뜻하는지 — attachment/관심도/친밀감 등)
- fixation 트리거 (올라가는/내려가는 조건)
- fixation 단계별 톤 가이드 (LOW/MID/HIGH 말투/태도)

포함하지 않을 것:
- fixation 단계별 행동 (proactive_behaviors 담당)

### 17. discovery_hint_template
유저 프로필 탐색 힌트 템플릿. `{topic}`이 미지 토픽명으로 치환됨.
캐릭터 성격에 맞는 탐색 방식.
빈 문자열이면 기본 템플릿 사용.
```json
// 관심 많은 캐릭터
"discovery_hint_template": "You don't know {{user}}'s {topic} and you're curious. Ask casually."

// 수동적 캐릭터
"discovery_hint_template": "If {{user}} mentions {topic}, show interest and follow up."

// 비서 캐릭터
"discovery_hint_template": "Note: {{user}}'s {topic} is unknown. If relevant to serving them, inquire formally."
```

### 18. mood_behaviors (필수)
stat_moods의 각 mood에 대응하는 행동 가이드. 현재 mood 1개만 프롬프트에 주입.
- stat_moods의 모든 mood에 대해 정의
```json
"mood_behaviors": {
    "happy": "행동 설명",
    "angry": "행동 설명"
}
```

### 19. stat_limits (선택)
캐릭터별 fixation 변화 한도. 없으면 글로벌 기본값 (fixation ±5).
```json
"stat_limits": {
    "fixation": {"up": 2, "down": -3}
}
```

## Part 2: images/char*.json (이미지 태그 config)

Grok의 danbooru 태그 생성 시 힌트로 전달되는 캐릭터별 이미지 설정. 카테고리별로 **라벨링되어 Grok에 전달**된다. SFW fork에서는 모든 카테고리가 SFW 전용이며, 노출/성행위 관련 카테고리(`body_nsfw`, `special` 액션 태그 등)는 스키마에서 제거되었다.

### 전체 스키마 (SFW)

```json
{
  "clothing": "...",
  "underwear": "...",
  "body_shape": {
    "size": "",          // BODY_SIZE — 키
    "build": "",         // BODY_BUILD — 골격/근육/살
    "curve": "",         // BODY_CURVE — 실루엣
    "accent": ""         // BODY_ACCENT — collarbone 등
  },
  "expressions": { /* 선택 */ },
  "mood_triggers": { /* 선택 */ }
}
```

### 카테고리별 가이드

| 카테고리 | 타입 | 의미 | 비고 |
|----------|------|------|------|
| `clothing` | string | 기본 의상 danbooru 태그 | 예: `"white crop top, blue denim shorts"` — 항상 풀세트 (top + bottom 또는 dress 단독) |
| `underwear` | string | 속옷 태그 | SFW에서는 의상 위로 노출되는 액세서리 정도 (예: bra strap이 살짝 보이는 캐주얼 룩)에 한해 사용. 단독 노출 컨텍스트는 사용하지 않는다 |
| `body_shape.*` | IDENTITY | 실루엣 정체성 | **항상 포함** — 옷 입은 상태에서 보이는 실루엣 |
| `expressions` | 선택 | mood별 표정 프리셋 | Grok이 mood 매칭 시 사용 |
| `mood_triggers` | 선택 | 키워드 → mood 락 | 특정 키워드 감지 시 강제 mood 전환 |

> 원본(`ella-telegram`)의 `breast.*`, `body_nsfw.*`, NSFW `special` 액션 카테고리는 SFW fork에서 스키마/풀(pool) 양쪽에서 제거되었다. 가슴 크기 같은 미세 신체 디테일은 캐릭터 정체성에 필수가 아니라면 비워둔다 — Grok이 자동으로 SFW 안전 범위 안에서 결정한다.

### 태그 어휘 출처

**`src/trait_pools.py`** 가 canonical 풀. SFW 카테고리별 리스트 참조:
- BODY_SIZE, BODY_BUILD, BODY_CURVE, BODY_ACCENT

원본의 `BODY_NSFW_*` 5개 상수 풀은 fork에서 모두 제거되었다.

### Grok 전달 형태

각 필드는 `[IDENTITY, always include]` 라벨과 함께 Grok에 전달된다. SFW fork는 CONDITIONAL 분기가 없다 — 모든 카테고리가 SFW 컨텍스트에서 일괄 사용된다. 명시적 노출/성적 컨텍스트 게이팅 로직(원본의 IDENTITY/CONDITIONAL 분기)은 제거되었다.

### 예시: 밝은 성격 캐릭터

```json
{
  "clothing": "white crop top, blue denim shorts",
  "underwear": "",
  "body_shape": {
    "size": "medium_height",
    "build": "slim",
    "curve": "narrow_waist",
    "accent": "collarbone"
  }
}
```

### expressions (선택)

mood 키 → danbooru 표정 태그. Grok이 현재 mood와 매칭되는 프리셋을 발견하면 해당 태그 사용.

```json
"expressions": {
  "shy": "blush, parted lips, looking_away",
  "happy": "smile, closed_eyes, :d"
}
```

### mood_triggers (선택)

유저 메시지 키워드 감지 시 강제 mood 전환 (락). 캐릭터 성격 강화용.

```json
"mood_triggers": {
  "shy": ["칭찬", "예쁘다"],
  "playful": ["놀자", "심심해"]
}
```

### 복합 danbooru 태그 주의

3단 이상 복합 태그(색상+길이+아이템 등)는 SDXL Illustrious가 학습 안 했을 가능성이 높아 의도와 다른 결과. Danbooru 컨벤션에 따라 개별 태그로 분리.

**BAD** (3단 복합):
- `beige_knee_length_skirt`
- `short_black_pleated_skirt`

**GOOD** (개별 분리):
- `beige_skirt, midi_skirt`
- `black_skirt, pleated_skirt, short_skirt`

2단 복합은 대부분 OK (`black_lace_panties`, `pencil_skirt`). 단 판타지 의상(`full_plate_armor`, `gothic_dress`)은 학습량 적어 변형 가능성 있음 — 대안 검토.

`src/danbooru_prompting_guide.md` (또는 fork에서 SFW 전용으로 정리된 가이드) 참조.

### SFW 안전망

- **글로벌 negative prefix**: `comfyui.py`의 `EMBEDDING_NEG_PREFIX`가 `embedding:illustrious/lazy-nsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand` 순으로 모든 이미지 생성에 자동 적용된다. 캐릭터 image_negative_prefix에 같은 임베딩을 또 넣을 필요 없음.
- **denylist**: `config/sfw_denylist.json`에 노출/성행위/체액 등의 차단 토큰이 정의되어 있으며 prompt 조립 단계에서 스트립된다.
- **Grok 시스템 프롬프트**: `config/grok_prompts.json`의 `system` 키가 SFW 전용 룰셋으로 작성되어 있어 Grok이 노골적 태그를 생성하지 않도록 강제한다.

### 주의사항

1. **body/appearance 태그 중복 금지** — hair/eye/skin 같은 외형 태그는 `persona.image_prompt_prefix`에서만. images/char*.json의 body 필드에는 넣지 않는다.
2. **weight syntax 지원** — `(blush:1.2)` 같은 SDXL 가중치 문법 사용 가능.
3. **빈 필드는 `""`** — 해당 카테고리 태그 없으면 빈 문자열. Grok에 전달 시 자동 스킵.

## Part 3: behaviors/char*.json (티어별 대사/행동)

fixation 값에 따라 어떤 말투·행동을 해야 하는지 **티어별 조건부 주입**. `src/prompt.py`의 `_load_behaviors()` 가 로드하여 매 턴 현재 fixation에 해당하는 하나의 티어만 프롬프트에 삽입.

### 스키마 (SFW)

```json
{
  "proactive_behavior": [
    { "condition": { "fixation": [0, 40] }, "prompt": "Light interest: ... CARETAKER QUESTIONS: ..." },
    { "condition": { "fixation": [40, 80] }, "prompt": "Engaged: ... EMOTIONAL CHECK-INS: ..." },
    { "condition": { "fixation": [80, 101] }, "prompt": "Devoted: ... PERSONAL QUESTIONS: ..." }
  ]
}
```

> 원본의 `arousal_speech` 티어 배열은 fork에서 제거되었다. fixation 단일 축으로 단순화된 결과 `proactive_behavior` 한 종류만 남는다.

### 설계 원칙

- **티어 수**: proactive_behavior 3개 권장
- **구간**: `[min, max)` — 상한 미포함. 연속성 확보 위해 겹치지 않게
- **최상위 구간은 `[X, 101]`**: max=100이므로 101로 상한 설정해야 100 포함
- **질문 패턴 포함**: 각 티어에 질문 예시 2-5개 넣기 — 캐릭터가 능동적으로 유저 정보를 끌어내는 용도

### 주의

- **mood와 중복 금지** — mood_behaviors는 감정 상태별 행동, proactive_behavior는 fixation 레벨별 행동. 다른 차원.
- **persona.proactive_behaviors 필드와 역할 분리** — persona 쪽은 "대략 이 캐릭터는 이렇게 능동적이다" 요약, behaviors 쪽은 "fixation 구간별로 뭘 한다" 상세 티어.
- 이 파일 **없어도 봇은 동작**하지만, LLM이 단계별 패턴을 잡기 어려워 응답이 평면적이 됨. 모든 메인 캐릭터에 권장.

## Part 4: world_info/char*.json (lorebook)

캐릭터의 **life_history / 과거 사건 / 배경 지식** 엔트리. SillyTavern Lorebook 스타일. 키워드 매칭 시 프롬프트에 삽입. `src/prompt.py`의 `_load_world_info()` 가 관리.

### 스키마

```json
{
  "entries": [
    {
      "key": ["옛 친구", "고등학교 친구"],
      "content": "고등학교 시절 가장 친했던 친구와는 졸업 후 연락이 끊겼다..."
    },
    {
      "key": ["어머니", "엄마"],
      "content": "..."
    }
  ]
}
```

### 카테고리 권장 (각 캐릭터당 7-10 엔트리)

1. **past_friendships** — 과거 친구/지인 관계
2. **family** — 부모/형제 관계
3. **younger_days** — 학창 시절, 어릴 때
4. **career_origin** — 현재 직업 가게 된 계기
5. **funny_anecdotes** — 웃기는/귀여운 과거 사건
6. **origin_event** — 핵심 성격을 형성한 사건
7. **hidden_contrast** — 현재 persona와 모순되거나 숨겨진 면

### 키워드 전략

- **넓게 잡지 말 것** — "옛날", "전에"는 대부분 매칭돼서 noise. "고등학교 친구", "첫 직장" 같은 구체적 표현만.
- **origin_event는 특히 tight** — 너무 자주 트리거되면 캐릭터가 매번 같은 과거를 읊음. 13개 이하 specific 키워드 권장.

### 주의

- 키워드 기반 매칭의 한계 (false negative/positive)는 **RAG 마이그레이션 backlog**에서 해결 예정.
- **파일이 없어도 봇은 동작** — 과거 질문에 캐릭터가 일반적으로 답함. 몰입도가 떨어질 뿐.

## Part 5: jobs/{key}.json (직업/학업 지식, 선택)

캐릭터의 `persona.jobs` 필드가 참조하는 키별 facts/vocabulary/daily_routines JSON. 캐릭터 대화에 직업적 디테일을 녹이는 용도.

### 스키마

`jobs/_schema.json` 참조. 핵심 필드:
- `facts_ko` (또는 `facts_en`) — 직업 관련 사실 (한/영)
- `vocabulary` — 해당 직업 전문 어휘
- `daily_routines` — 하루 일과 패턴

### 기존 직업 재사용 vs 신규

- 기존 직업이 적합하면 `persona.jobs` 배열에 해당 키 추가만 (파일 신규 생성 불필요)
- 신규 직업은 `jobs/{new_key}.json` 생성 (영어 작성 권장 — 토큰 절감 + 개성 유지)

## Part 6: 새 캐릭터 추가 체크리스트

### 필수 파일 생성
- [ ] `persona/char{NN}.json` — 캐릭터 카드 (Part 1 참조)
- [ ] `images/char{NN}.json` — 이미지 태그 config (Part 2 참조, SFW 카테고리만)
- [ ] `behaviors/char{NN}.json` — fixation 기반 proactive_behavior 티어 (Part 3 참조, **누락 시 응답 평면적**)

### 선택 파일
- [ ] `world_info/char{NN}.json` — lorebook life_history (Part 4)
- [ ] `jobs/{new_key}.json` — 신규 직업인 경우 (Part 5)
- [ ] `images/char{NN}.png` — IPAdapter FaceID 앵커 (미존재 시 FaceID 바이패스)
- [ ] `images/profile/char{NN}.png` — 메인 봇 카드용 프로필 (미존재 시 텍스트 fallback)

### 코드 등록 (수동)
- [ ] `src/history.py` `INITIAL_STATS` — 초기 fixation/mood (arousal/heat_active 컬럼은 fork에 존재하지 않음)
- [ ] `src/history.py` `DISCOVERY_ALLOWED_MOODS` — discovery가 허용할 mood 목록 (새 캐릭터 mood 포함)
- [ ] `src/handlers_main.py` `_CHAR_ORDER` — 메인 봇 /start·/char UI 표시 순서
- [ ] `src/handlers_imagegen.py` `CHAR_NAME_MAP` — 한글 별칭/이름 → char_id 매핑
- [ ] `src/handlers_imagegen.py` `IMAGEGEN_CHAR_IDS` — 이미지봇 자동 감지 대상 (필요 시)

### 환경변수 (.env)
- [ ] `TEST_CHAR_BOT_char{NN}` / `TEST_CHAR_USERNAME_char{NN}` — Mac dev 용
- [ ] **GB10 배포 시**: `PROD_CHAR_BOT_char{NN}` / `PROD_CHAR_USERNAME_char{NN}` 를 GB10 `.env`에 추가
- [ ] **GB10 배포 시**: Mac `.env`에서 `TEST_CHAR_BOT_char{NN}` 주석 처리 (토큰 충돌 방지)
- [ ] `SEARCH_EXCLUDED_CHARS` 업데이트 (판타지 세계관이라 웹 검색 부적합한 경우)

### 자동 처리 (수동 작업 불필요)
- 봇 등록: `bot.py`가 `char{NN}.json` 패턴으로 자동 로드
- 수치 시스템: `INITIAL_STATS` 등록 후 자동 동작
- 탐색 힌트: `discovery_hint_template`이 있으면 자동 동작
- mood 행동: `mood_behaviors`가 있으면 자동 동작
- 직업 지식: `persona.jobs` 배열의 키로 `jobs/{key}.json` 자동 로드
- lorebook: `world_info/char{NN}.json`이 있으면 자동 로드 + 키워드 매칭
- behaviors: `behaviors/char{NN}.json`이 있으면 자동 로드 + 티어 매칭

### 배포 순서 (프로덕션)
1. Mac dev 에서 feature 브랜치 생성 + 개발 + 테스트
2. develop 머지, 추가 테스트
3. main 머지, GB10 스테이징 (dev bot + dev DB)로 테스트
4. `git tag vX.Y.Z`
5. GB10 `.env` prod 토큰 추가, systemd 재시작
6. Mac .env 해당 TEST 토큰 주석 처리

## 흔한 실수

### persona/char*.json
1. **personality에 행동 넣기** — "you become anxious and demand..."는 proactive_behaviors에
2. **post_history에 system_prompt 규칙 반복** — 톤/성격은 system_prompt에만
3. **interests에 유저 행동 넣기** — "{{user}}'s schedule"은 관심사가 아님
4. **stat_personality에 fixation 행동 넣기** — proactive_behaviors에 위임
5. **image_prompt_prefix에 구도 태그 넣기** — Grok이 자율 결정
6. **문장 수 제한** — max_tokens 500이 자연스럽게 제한, 별도 제한 불필요
7. **mes_example을 한 톤으로만 채우기** — 후반 대화에서 LLM이 그 패턴으로 수렴. fixation 단계별로 다양한 예시 섞기

### images/char*.json
8. **hair/eye/skin 태그를 body에 넣기** — 외형은 `persona.image_prompt_prefix`에만
9. **body를 flat string으로 작성** — 구버전 스키마. 현재는 body_shape 세분화 필수
10. **공백 구분 태그** — danbooru는 언더스코어 구분 (`large_breasts`, NOT `large breasts`)
11. **3단 이상 복합 태그** — `beige_knee_length_skirt` 같은 color+length+item 조합은 SDXL이 학습 못 해서 엉뚱한 결과. 반드시 `beige_skirt, midi_skirt`로 분리
12. **fork에서 제거된 카테고리(`body_nsfw`, NSFW `special` 액션) 부활시키기** — 해당 풀이 없어 무시되거나 SFW 가드(denylist)에서 스트립된다. 시도하지 말 것

### behaviors/char*.json
13. **파일 자체를 만들지 않음** — bot은 동작하지만 응답이 평면적. 꼭 생성
14. **proactive_behavior에 질문 없음** — 캐릭터가 유저 정보 끌어내지 못함. 각 티어에 2-5개 질문 예시 포함 권장
15. **최상위 구간 `[80, 100]`** — max=100이 포함 안 됨. `[80, 101]`로 설정

### 배포 관련
16. **GB10 `.env`에 `PROD_CHAR_BOT_char{NN}` 누락** — 캐릭터가 배포돼도 봇 토큰 없으면 polling 안 됨. 사전 생성 필수
17. **`_CHAR_ORDER` 누락** — char 등록돼도 메인 봇 카드 UI에 안 나옴
