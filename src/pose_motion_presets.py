"""pose_motion_presets.py — preset lookup (SFW text-only).

Catalog keyed by pose_key, consulted by the 2-stage Grok pipeline (Analyzer →
Composer) when assembling WAN 2.2 i2v motion prompts.

Loads `config/pose_motion_presets.json` once at import time.

Schema: each preset is a flat object — `primary`, `camera`, `audio`,
`ambient_fallback`, `anchor_risk` are required. SFW single-tier layout.

Keys with an underscore (`_`) prefix are docs/templates — excluded from
list_keys() and not reachable via lookup. The 'generic' key is the catch-all
fallback (required).

Public API:
    lookup(pose_key, safety_level) -> dict | None
    list_keys() -> list[str]
    list_keys_by_tier() -> dict[str, list[str]]   # only the single "text" tier

Example:
    from src.pose_motion_presets import lookup, list_keys

    preset = lookup("generic", "sfw")
    # Returns the text preset — primary/camera/audio/...
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
    """Validate a single pose_motion_presets.json entry (flat schema)."""
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
    """Validate the entire pose_motion_presets.json. The 'generic' key is required."""
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
# Load (fail-fast)
# ─────────────────────────────────────────────────────────────

with open(_TEXT_PRESETS_PATH, "r", encoding="utf-8") as _f:
    _PRESETS: dict = _load_and_validate_text(json.load(_f))

# Public key list (underscore keys excluded)
_PUBLIC_KEYS: list[str] = sorted([k for k in _PRESETS if not k.startswith("_")])

logger.info("Loaded pose motion presets — total=%d", len(_PUBLIC_KEYS))
logger.debug("Preset keys: %s", _PUBLIC_KEYS)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def _is_safe(safety_level: str) -> bool:
    """SFW fork — only `blocked` is rejected; everything else is allowed."""
    if not isinstance(safety_level, str):
        return True
    return safety_level.strip().lower() != "blocked"


def lookup(pose_key: str, safety_level: str) -> dict | None:
    """Look up a preset by pose_key + safety_level.

    - underscore keys / unknown keys → fall back to `generic` text preset
    - safety_level == "blocked" → None
    - Return schema: {primary, camera, audio, ambient_fallback, anchor_risk, ...}
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
    """Return all public pose_keys (sorted)."""
    return list(_PUBLIC_KEYS)


def list_keys_by_tier() -> dict[str, list[str]]:
    """Bundle every SFW pose_key under a single tier called 'text'.

    The SFW fork has no LoRA tier — this function returns a single tier purely
    so call sites stay compatible.

    Returns:
        {"text": ["generic", "portrait_static_sfw", ...]}
    """
    return {"text": list(_PUBLIC_KEYS)}
