# `docs/` — Project documentation (SFW fork)

캐릭터 카드 작성 가이드, 약관, 비디오 설계 노트 등 운영 문서를 모아둔다. 모든 문서는 fork 시점에 SFW 기준으로 수정 또는 재작성되었다.

## 파일

- **`character_card_instruction.md`** — 캐릭터 카드 (`persona/` + `behaviors/` + `images/`) 작성 가이드. Phase 3-5 E3에서 NSFW 필드(`body_nsfw`, `arousal_speech`, `arousal_response`, `curse_heat` 등) 부분이 strip되었고, fork 스키마(`character_card_schema.json`)에 맞춘 SFW 갱신본이다.
- **`character_sheets.md`** — 캐릭터 시트 작성용 템플릿/체크리스트. Phase 3-5 E3에서 SFW 작성 가이드/템플릿으로 rewrite 됨. NSFW 캐릭터 시트는 fork에 미존재.
- **`terms_of_service.md`** — 봇 사용 약관. Phase 3-5 E3에서 SFW 약관으로 rewrite 됨. payment / billing / Stars 관련 섹션은 Phase 6에서 결제 시스템 제거와 함께 삭제.
- **`video-improve1.md`** — 비디오 생성 (i2v) 설계 / 디버깅 노트. Phase 3-5 E3에서 -48% 단축. NSFW / CSAM 안전 관련 design history 부분은 historical 표기 후 본문에서 strip — 현재 fork 의 single-tier wan-2.6 경로만 반영한다.

## SFW invariant

- 어떤 문서도 NSFW 작성 가이드 / NSFW 카드 예시 / 결제 흐름을 포함하지 않는다.
- `character_card_instruction.md` 의 필드 목록은 `character_card_schema.json` 과 동기화 — 스키마 갱신 시 이 문서도 같이 갱신.
- 새 docs 파일을 추가할 때는 SFW 톤 유지 + 결제/유료 등급 분기 미존재 사실을 반영한다.
