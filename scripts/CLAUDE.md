# `scripts/` — Operational scripts (SFW fork)

운영용 단발성 스크립트(캐릭터 일괄 import, DB 마이그레이션 도우미, 데이터 시드 등)를 둘 자리. **현재 fork 에서는 비어 있다** (`.gitkeep`만 존재).

## 원본 대비 차이

원본 `ella-telegram/scripts/` 에 있는 `generate_job_facts.py`는 fork 에 미이관 — fork 의 `jobs/` 폴더 데이터 자체가 비어 있어 직업 fact 생성 스크립트를 돌릴 입력이 없다. 직업 데이터를 다시 채우게 되면 이 스크립트의 SFW 적합 버전을 새로 작성해 여기에 두면 된다.

## 추가 가이드

- 새 스크립트는 절대 경로 기반 + idempotent 하게 작성 (재실행 시 부수효과 없게).
- DB 를 건드리는 스크립트는 실행 전 `deploy/backup_db.sh` 를 호출하거나 dry-run 옵션을 지원할 것.
