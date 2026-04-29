# `docs/` — Project documentation (SFW fork)

캐릭터 카드 작성 가이드 등 운영 문서를 모아둔다. 모든 문서는 fork 시점에 SFW 기준으로 수정 또는 재작성되었다.

## 파일

- **`character_card_instruction.md`** — 캐릭터 카드 (`persona/` + `behaviors/` + `images/`) 작성 가이드. Phase 3-5 E3에서 NSFW 필드(`body_nsfw`, `arousal_speech`, `arousal_response`, `curse_heat` 등) 부분이 strip되었고, fork 스키마(`character_card_schema.json`)에 맞춘 SFW 갱신본이다.
- **`character_sheets.md`** — 캐릭터 시트 작성용 템플릿/체크리스트. Phase 3-5 E3에서 SFW 작성 가이드/템플릿으로 rewrite 됨. NSFW 캐릭터 시트는 fork에 미존재.
- **`features/`** — 마일스톤별 feature plan MD. 각 feature 브랜치 시작 시 작성. 현재: `M0_admin_skeleton.md`, `M1_env_connections.md`.

## SFW invariant

- 어떤 문서도 NSFW 작성 가이드 / NSFW 카드 예시 / 결제 흐름을 포함하지 않는다.
- `character_card_instruction.md` 의 필드 목록은 `character_card_schema.json` 과 동기화 — 스키마 갱신 시 이 문서도 같이 갱신.
- 새 docs 파일을 추가할 때는 SFW 톤 유지 + 결제/유료 등급 분기 미존재 사실을 반영한다.
