"""profile_keys.py — user profile key canonicalization.

Maps the various aliases that the LLM may emit (favorite_food, recent_meal,
occupation, etc.) onto a fixed set of canonical keys (food, job, etc.).

- Loads canonical → aliases mapping from config/profile_keys.json
- Builds a reverse alias → canonical index at module load time (O(1) lookup)
- Returns the original key as-is and emits an INFO log when no mapping
  is found (helpful for spotting new aliases)
"""

import json
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "profile_keys.json"


def _config_path() -> str:
    """Path to config/profile_keys.json relative to the project root."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config", _CONFIG_FILENAME)


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load config/profile_keys.json (cached)."""
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
    """Reverse index: alias (lowercased) → canonical."""
    cfg = _load_config()
    canonical_keys = cfg.get("canonical_keys", {}) or {}
    index: dict[str, str] = {}
    for canonical, aliases in canonical_keys.items():
        if not isinstance(canonical, str) or not canonical:
            continue
        # Include the canonical key as its own alias automatically
        index[canonical.lower()] = canonical
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias:
                    index[alias.lower()] = canonical
    return index


def canonicalize(key: str) -> str:
    """Replace an alias with its canonical key.

    On a miss, returns the original key unchanged and logs at INFO level
    (helps surface new aliases to add). Case-insensitive.
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
    """Return the list of canonical keys. Passed to the LLM in EXTRACT_PROMPT."""
    cfg = _load_config()
    canonical_keys = cfg.get("canonical_keys", {}) or {}
    return list(canonical_keys.keys())
