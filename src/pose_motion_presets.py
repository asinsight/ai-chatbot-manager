"""pose_motion_presets.py — Preset 룩업 (SFW 텍스트 전용).

2-stage Grok 파이프라인(Analyzer → Composer)이 WAN 2.2 i2v 모션 프롬프트를
조립할 때 참조하는 pose_key 기반 카탈로그.

`config/pose_motion_presets.json` 한 파일을 import 시점에 로드한다.

스키마: 각 preset은 평탄한(flat) 객체 — `primary`, `camera`, `audio`,
`ambient_fallback`, `anchor_risk` 필수. SFW 단일 tier 구조.

언더스코어(`_`) prefix key는 도큐/템플릿 — list_keys()에서 제외, lookup 불가.
'generic' key는 catch-all fallback (필수).

Public API:
    lookup(pose_key, safety_level) -> dict | None
    list_keys() -> list[str]
    list_keys_by_tier() -> dict[str, list[str]]   # 단일 tier "text"만 반환

Example:
    from src.pose_motion_presets import lookup, list_keys

    preset = lookup("generic", "sfw")
    # 텍스트 프리셋 반환 — primary/camera/audio/...
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TEXT_PRESETS_PATH = Path(__file__).parent.parent / "config" / "pose_motion_presets.json"

_VALID_RISK = {"low", "medium", "high"}
_REQUIRED_FIELDS = ("primary", "camera", "audio")


# ─────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────


def _validate_text_entry(key: str, preset: dict) -> None:
    """pose_motion_presets.json 단일 entry 검증 (평탄 스키마)."""
    for field in _REQUIRED_FIELDS:
        val = preset.get(field)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"preset '{key}': '{field}' must be a non-empty string"
            )
    ambient = preset.get("ambient_fallback")
    if not isinstance(ambient, str) or not ambient.strip():
        raise ValueError(f"preset '{key}': 'ambient_fallback' must be a non-empty string")
    risk = preset.get("anchor_risk")
    if risk not in _VALID_RISK:
        raise ValueError(
            f"preset '{key}': 'anchor_risk' must be one of {sorted(_VALID_RISK)}, got {risk!r}"
        )


def _load_and_validate_text(raw: dict) -> dict:
    """pose_motion_presets.json 전체 검증. 'generic' key 필수."""
    if not isinstance(raw, dict) or not raw:
        raise ValueError("pose_motion_presets.json: top-level must be a non-empty object")
    if "generic" not in raw:
        raise ValueError("pose_motion_presets.json: missing required 'generic' preset")
    for key, preset in raw.items():
        if key.startswith("_"):
            continue
        if not isinstance(preset, dict):
            raise ValueError(f"preset '{key}': must be an object")
        _validate_text_entry(key, preset)
    return raw


# ─────────────────────────────────────────────────────────────
# 로드 (fail-fast)
# ─────────────────────────────────────────────────────────────

with open(_TEXT_PRESETS_PATH, "r", encoding="utf-8") as _f:
    _PRESETS: dict = _load_and_validate_text(json.load(_f))

# Public key 목록 (언더스코어 제외)
_PUBLIC_KEYS: list[str] = sorted([k for k in _PRESETS if not k.startswith("_")])

logger.info("Loaded pose motion presets — total=%d", len(_PUBLIC_KEYS))
logger.debug("Preset keys: %s", _PUBLIC_KEYS)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def _is_safe(safety_level: str) -> bool:
    """SFW fork — blocked만 거부하고 그 외엔 모두 허용."""
    if not isinstance(safety_level, str):
        return True
    return safety_level.strip().lower() != "blocked"


def lookup(pose_key: str, safety_level: str) -> dict | None:
    """pose_key + safety_level로 preset 조회.

    - 언더스코어 키 / 미등록 키 → `generic` 텍스트 fallback
    - safety_level=blocked → None
    - 반환 스키마: {primary, camera, audio, ambient_fallback, anchor_risk, ...}
    """
    if not _is_safe(safety_level):
        return None
    if isinstance(pose_key, str) and not pose_key.startswith("_") and pose_key in _PRESETS:
        key = pose_key
    else:
        key = "generic"
    preset = _PRESETS[key]

    return {
        "primary": preset["primary"],
        "camera": preset["camera"],
        "audio": preset["audio"],
        "motion_addon": preset.get("motion_addon", ""),
        "ambient_fallback": preset["ambient_fallback"],
        "anchor_risk": preset["anchor_risk"],
        "notes": preset.get("notes"),
        "examples": list(preset.get("examples", [])),
        "avoid_patterns": list(preset.get("avoid_patterns", [])),
        "pose_key_resolved": key,
    }


def list_keys() -> list[str]:
    """모든 public pose_key 반환 (정렬됨)."""
    return list(_PUBLIC_KEYS)


def list_keys_by_tier() -> dict[str, list[str]]:
    """단일 tier 'text'에 모든 SFW pose_key를 묶어 반환.

    SFW fork에서는 LoRA tier가 없으므로 호출부 호환을 위해 단일 tier만 반환한다.

    Returns:
        {"text": ["generic", "portrait_static_sfw", ...]}
    """
    return {"text": list(_PUBLIC_KEYS)}
