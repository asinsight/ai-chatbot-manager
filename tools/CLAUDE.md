# `tools/` — Developer tooling (SFW fork)

개발자용 보조 도구(프롬프트 비교, 씬 디스크립션 생성, ad-hoc 검증 스크립트 등)를 둘 자리. **현재 fork 에서는 비어 있다** (`.gitkeep`만 존재).

## 원본 대비 차이

원본 `ella-telegram/tools/` 에는 `generate_scene_descriptions_ko.py` 와 Grok 비교 테스트 스크립트들이 있으나, 이들은 NSFW 씬 카탈로그 / NSFW 분류기 / arousal 스탯 등 fork 에서 제거된 의존성에 묶여 있어 모두 미이관. 같은 목적의 SFW 도구가 필요해지면 여기에 새로 작성한다.

## 추가 가이드

- 도구는 봇 런타임에 영향을 주지 않게 격리 (별도 venv / 별도 entrypoint).
- LLM API 키를 사용하는 도구는 `.env` 와 동일한 키를 읽되, 호출량은 dry-run / 샘플링으로 제한.
