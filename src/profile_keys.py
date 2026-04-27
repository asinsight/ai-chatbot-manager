"""profile_keys.py — 유저 프로필 키 정규화(canonicalization).

LLM이 추출한 다양한 별칭(favorite_food, recent_meal, occupation 등)을
정해진 canonical key(food, job 등)로 매핑한다.

- config/profile_keys.json에서 canonical → aliases 매핑 로드
- 모듈 로드 시 alias → canonical 역방향 인덱스를 빌드 (O(1) 조회)
- 매핑 없는 키는 원본 그대로 반환하고 INFO 로그 (새 alias 발견용)
"""

import json
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "profile_keys.json"


def _config_path() -> str:
    """프로젝트 루트 기준 config/profile_keys.json 경로."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config", _CONFIG_FILENAME)


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """config/profile_keys.json 로드 (캐시)."""
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning("profile_keys config not found at %s; canonicalize is a no-op", path)
        return {"canonical_keys": {}}
    except Exception as e:
        logger.error("profile_keys config load failed (%s): %s", path, e)
        return {"canonical_keys": {}}
    if not isinstance(data, dict) or "canonical_keys" not in data:
        logger.warning("profile_keys config malformed; expected 'canonical_keys' top-level key")
        return {"canonical_keys": {}}
    return data


@lru_cache(maxsize=1)
def _alias_index() -> dict:
    """alias(소문자) → canonical 역방향 인덱스."""
    cfg = _load_config()
    canonical_keys = cfg.get("canonical_keys", {}) or {}
    index: dict[str, str] = {}
    for canonical, aliases in canonical_keys.items():
        if not isinstance(canonical, str) or not canonical:
            continue
        # canonical 자기 자신도 자동 포함
        index[canonical.lower()] = canonical
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias:
                    index[alias.lower()] = canonical
    return index


def canonicalize(key: str) -> str:
    """alias를 canonical key로 치환한다.

    매칭 실패 시 원본 key를 그대로 반환하고 INFO 로그를 남긴다 (새 alias 발견 지원).
    대소문자 무시.
    """
    if not key or not isinstance(key, str):
        return key
    idx = _alias_index()
    canonical = idx.get(key.lower())
    if canonical is None:
        logger.info("profile key '%s' not in canonical list", key)
        return key
    return canonical


def get_canonical_keys() -> list[str]:
    """canonical 키 리스트 반환. EXTRACT_PROMPT에서 LLM에게 전달."""
    cfg = _load_config()
    canonical_keys = cfg.get("canonical_keys", {}) or {}
    return list(canonical_keys.keys())
