# `behaviors/` — Per-character behavior tables (SFW fork)

캐릭터별 행동 규칙 JSON. `persona/`가 캐릭터의 *정체성*을 다룬다면 `behaviors/`는 fixation 수치와 mood에 따른 *행동 분기*를 다룬다. `src/prompt.py`가 시스템 프롬프트를 조립할 때 활성 캐릭터의 behavior 파일을 읽어 현재 fixation 구간/mood에 매칭되는 줄만 system prompt에 주입한다.

## 파일 명명 규칙

`charNN.json` 형식 (NN = 두 자리 0-padded). 현재 fork에 들어 있는 카드:

| 파일 | 캐릭터 | 비고 |
|---|---|---|
| `char05.json` | Jiwon Han — 31세 임원 비서 (영어로 응답) | i18n 단계에서 char05 만 남기고 나머지 8명 (char01-04, char06-09) 모두 삭제. 추가 캐릭터는 다음 빈 번호로 등록 |

## 파일 구조

각 파일은 두 키 중 하나 이상을 가진다 (캐릭터마다 채우는 범위가 다르다):

| 키 | 용도 |
|---|---|
| `proactive_behavior` | fixation 구간별 능동 행동 가이드 (배열). 각 항목 = `{ "condition": {"fixation": [low, high]}, "prompt": "..." }`. 보통 4단계: `[0,20]` VERY LOW / `[20,50]` LOW / `[50,80]` MEDIUM / `[80,101]` HIGH. |
| `mood_behaviors` | 현재 mood 값별 행동 가이드 (객체). key = mood 문자열, value = 짧은 가이드 문장. `persona/` 의 같은 이름 필드와 중복될 수 있음 — 둘 다 있으면 prompt 조립 단계에서 적절히 머지. |
| `mood_triggers` | mood 전이 트리거 (배열). `{ "trigger": "...", "mood": "..." }`. SFW 상황(피로/관심/긴장 등)만 트리거로 사용. |

`persona/` 카드 내 `proactive_behaviors`, `mood_behaviors`, `mood_triggers`, `stat_limits` 필드는 `character_card_schema.json`에서도 정의되어 있어 둘 중 어느 위치에 두어도 무방하다 — 현 fork에서는 짧은 string/object 형태는 persona 카드에, 분기 테이블이 큰 경우(예: 4단계 fixation 구간)는 `behaviors/`로 분리한다.

## SFW invariant

- **arousal_speech / arousal_response 부재** — 원본의 arousal 수치 기반 말투 분기는 fork에서 제거됨.
- **heat_cycle / curse_heat 부재** — 발열 주기/저주 사이클 트리거는 미존재.
- **RELIEF / Layered Lust 부재** — 3-tier lust 구조와 [RELIEF] 시그널 미존재.
- 분기 키는 `fixation` 구간 + `mood` 문자열만 사용한다. `arousal` 키를 새로 도입하지 말 것.

## 새 캐릭터 추가 절차

1. 다음 비어 있는 `charNN` 번호 선택 (현재 `char10` 부터 사용 가능)
2. `behaviors/charNN.json` 작성 — 최소 `proactive_behavior` 4단계 정도는 채우는 것을 권장
3. 같은 번호로 `persona/charNN.json`, `images/charNN.json` 도 작성
4. `character_card_schema.json`을 만족하는지 검증 (필요 시 `python -m json.tool` 로 syntax 체크)
5. `docs/character_card_instruction.md` / `docs/character_sheets.md` 의 SFW 작성 가이드를 따른다 — NSFW 필드(`body_nsfw`, `arousal_speech` 등)는 schema에서도 미존재하므로 절대 추가하지 말 것

## 빈 템플릿

```json
{
  "proactive_behavior": [
    {"condition": {"fixation": [0, 20]},  "prompt": "VERY LOW: ..."},
    {"condition": {"fixation": [20, 50]}, "prompt": "LOW: ..."},
    {"condition": {"fixation": [50, 80]}, "prompt": "MEDIUM: ..."},
    {"condition": {"fixation": [80, 101]},"prompt": "HIGH: ..."}
  ]
}
```
