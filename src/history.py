"""SQLite-backed per-user chat history module.

Supports multiple characters: per-character history is separated by the
character_id column, and the active character per user is tracked in
user_settings.
"""

import json
import os
import re
import sqlite3

# ── Character stat system constants ──

INITIAL_STATS = {
    "char01": {"fixation": 20, "mood": "happy"},
    "char02": {"fixation": 20, "mood": "shy"},
    "char03": {"fixation": 20, "mood": "happy"},
    "char04": {"fixation": 20, "mood": "shy"},
    "char05": {"fixation": 20, "mood": "neutral"},
    "char06": {"fixation": 20, "mood": "happy"},
    "char07": {"fixation": 20, "mood": "arrogant"},
    "char08": {"fixation": 0, "mood": "strict"},
    "char_test": {"fixation": 20, "mood": "happy"},
    "char09": {"fixation": 30, "mood": "affectionate"},
    "char10": {"fixation": 30, "mood": "silent"},
}

STAT_LIMITS = {
    "fixation": {"up": 5, "down": -5},
}
STAT_RANGE = {"min": 0, "max": 100}


# Compute data/chat.db path relative to the project root
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_DB_PATH = os.path.join(_DATA_DIR, "chat.db")


def _get_connection() -> sqlite3.Connection:
    """Return a SQLite connection."""
    return sqlite3.connect(_DB_PATH)


def init_db() -> None:
    """Initialize the DB — create the data/ directory, tables/indexes, and run migrations.

    Call this once at bot.py startup.
    """
    os.makedirs(_DATA_DIR, exist_ok=True)

    # saved_characters v3 migration (DROP the old schema before CREATE TABLE)
    # CREATE TABLE IF NOT EXISTS is a no-op when the table already exists, so
    # new columns wouldn't be added. We detect the old schema, DROP it first,
    # and let the CREATE TABLE below recreate it.
    try:
        _migrate_saved_chars_v3()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Saved characters v3 migration failed: %s", _mig_e)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL")

        # --- chat_history table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_id
            ON chat_history(user_id)
            """
        )

        # Migration: add character_id column to existing table
        try:
            cursor.execute(
                "ALTER TABLE chat_history ADD COLUMN character_id TEXT DEFAULT 'default'"
            )
        except sqlite3.OperationalError:
            # Column already exists — ignore
            pass

        # Composite index that includes character_id
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_character
            ON chat_history(user_id, character_id)
            """
        )

        # --- user_settings table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                active_character TEXT NOT NULL DEFAULT 'char01'
            )
            """
        )

        # --- chat_summary table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                character_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                message_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_summary_user_character
            ON chat_summary(user_id, character_id)
            """
        )

        # --- user_profile table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id INTEGER NOT NULL,
                character_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, character_id, key)
            )
            """
        )

        # --- long_term_memory table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                character_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ltm_user_character
            ON long_term_memory(user_id, character_id)
            """
        )

        # Migration: extend user_settings
        for col_sql in [
            "ALTER TABLE user_settings ADD COLUMN username TEXT",
            "ALTER TABLE user_settings ADD COLUMN age_verified BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN terms_agreed BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        ]:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        # --- usage table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                telegram_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                turns INTEGER DEFAULT 0,
                images INTEGER DEFAULT 0,
                videos INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, month)
            )
            """
        )

        # --- user_outfit table ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_outfit (
                telegram_id INTEGER,
                character_id TEXT,
                clothing TEXT,
                underwear TEXT,
                source TEXT DEFAULT 'preset',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, character_id)
            )
            """
        )

        # --- Daily image usage ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_daily (
                telegram_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                images INTEGER DEFAULT 0,
                PRIMARY KEY (telegram_id, date)
            )
            """
        )

        # --- Character stats (character_stats) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS character_stats (
                user_id INTEGER NOT NULL,
                character_id TEXT NOT NULL,
                fixation INTEGER DEFAULT 20,
                mood TEXT DEFAULT 'neutral',
                location TEXT DEFAULT '',
                total_turns INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, character_id)
            )
            """
        )

        # Add videos column to usage_daily (migration)
        try:
            cursor.execute("ALTER TABLE usage_daily ADD COLUMN videos INTEGER DEFAULT 0")
        except Exception:
            pass  # already exists

        # --- location_context (global location cache, P10 Phase 2) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS location_context (
                location_key TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                danbooru_background TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Pose preset usage stats — counts how often each pose_key (pose_motion_presets key) was chosen.
        # Table name is a schema-level identifier so we keep `lora_preset_usage` for backward compat.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lora_preset_usage (
                pose_key TEXT PRIMARY KEY,
                call_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # --- saved_characters (image-generator character store, Feature 1) ---
        # Up to 3 slots per user. Name (alphanumeric/underscore) + danbooru
        # appearance/outfit tags.
        # seed / anchor image are NOT stored (PM decision) — regeneration uses
        # a random seed and reproduces the look from tags only.
        # Nested schema (P15-3 v3, mirrors images/char*.json):
        #   appearance_tags : flat string (eye/hair/face/skin/age/species)
        #   clothing        : flat string (outerwear/shoes/accessories)
        #   underwear       : flat string (intimate wear)
        #   body_shape_json : {"size", "build", "curve", "accent", "ass"}
        #   breast_json     : {"size", "feature"}
        # _migrate_saved_chars_v3 runs just before init_db enters and DROPs
        # the table if it detects an old schema.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_characters (
                user_id         INTEGER NOT NULL,
                slot            INTEGER NOT NULL,
                name            TEXT NOT NULL,
                appearance_tags TEXT NOT NULL,
                clothing        TEXT,
                underwear       TEXT,
                body_shape_json TEXT,
                breast_json     TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, slot)
            )
            """
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_chars_user_name ON saved_characters(user_id, name)"
        )

        conn.commit()
    finally:
        conn.close()

    # Location-key normalization migration (idempotent)
    try:
        _migrate_location_keys()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Location key migration failed: %s", _mig_e)

    # user_profile key canonicalization migration (idempotent)
    try:
        _migrate_profile_keys()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Profile key migration failed: %s", _mig_e)


def save_message(
    user_id: int, role: str, content: str, character_id: str = "default"
) -> None:
    """Save a single message to history."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_id, role, content, character_id) "
            "VALUES (?, ?, ?, ?)",
            (user_id, role, content, character_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_history(
    user_id: int, limit: int = 20, character_id: str = "default"
) -> list[dict]:
    """Return the last N messages for a user/character, oldest → newest.

    Args:
        user_id: Telegram user id
        limit: number of messages to fetch. Overridable via HISTORY_LIMIT env var.
        character_id: character id. Defaults to 'default'.

    Returns:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """
    # If HISTORY_LIMIT env var is set, use it instead of the default
    env_limit = os.environ.get("HISTORY_LIMIT")
    if env_limit is not None and limit == 20:
        limit = int(env_limit)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # Fetch the latest N rows then sort chronologically
        cursor.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content, created_at
                FROM chat_history
                WHERE user_id = ? AND character_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            ) sub
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, character_id, limit),
        )
        rows = cursor.fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]
    finally:
        conn.close()


def clear_history(user_id: int, character_id: str | None = None) -> None:
    """Clear a user's history (used by /clear).

    Args:
        user_id: Telegram user id
        character_id: if set, clear only that character's history.
                      If None, clear all of the user's history (legacy compat).
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        if character_id is not None:
            cursor.execute(
                "DELETE FROM chat_history WHERE user_id = ? AND character_id = ?",
                (user_id, character_id),
            )
        else:
            cursor.execute(
                "DELETE FROM chat_history WHERE user_id = ?",
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()


def get_active_character(user_id: int) -> str:
    """Return the user's active character id. Defaults to 'char01' if unset."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT active_character FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else "char01"
    finally:
        conn.close()


def set_active_character(user_id: int, character_id: str) -> None:
    """Set the user's active character id."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_settings (user_id, active_character) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET active_character = excluded.active_character",
            (user_id, character_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_summary(user_id: int, character_id: str, summary: str, message_count: int) -> None:
    """Persist a summary."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_summary (user_id, character_id, summary, message_count) "
            "VALUES (?, ?, ?, ?)",
            (user_id, character_id, summary, message_count),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_summary(user_id: int, character_id: str) -> str | None:
    """Return the latest summary for the user/character. None if none exists."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT summary FROM chat_summary "
            "WHERE user_id = ? AND character_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, character_id),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def delete_old_messages(user_id: int, character_id: str, keep_recent: int = 10) -> int:
    """Delete old messages after summarization completes. Keeps the latest keep_recent rows.

    Returns:
        Number of messages deleted.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # Fetch the ids of the most recent keep_recent rows
        cursor.execute(
            "SELECT id FROM chat_history "
            "WHERE user_id = ? AND character_id = ? "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT ?",
            (user_id, character_id, keep_recent),
        )
        keep_ids = [row[0] for row in cursor.fetchall()]

        if not keep_ids:
            return 0

        placeholders = ",".join("?" * len(keep_ids))
        cursor.execute(
            f"DELETE FROM chat_history "
            f"WHERE user_id = ? AND character_id = ? AND id NOT IN ({placeholders})",
            (user_id, character_id, *keep_ids),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def get_message_count(user_id: int, character_id: str) -> int:
    """Return the message count for the user/character."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chat_history "
            "WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


# ── User Profile ─────────────────────────────────────────────


def set_profile(user_id: int, character_id: str, key: str, value: str, source: str = "manual") -> None:
    """Set a user-profile entry (upsert)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_profile (user_id, character_id, key, value, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(user_id, character_id, key) DO UPDATE SET "
            "value = excluded.value, source = excluded.source, updated_at = CURRENT_TIMESTAMP",
            (user_id, character_id, key, value, source),
        )
        conn.commit()
    finally:
        conn.close()


def get_profile(user_id: int, character_id: str) -> dict:
    """Return the profile for a given scope as a dict. {"key": {"value": "...", "source": "..."}, ...}"""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key, value, source FROM user_profile "
            "WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        )
        return {row[0]: {"value": row[1], "source": row[2]} for row in cursor.fetchall()}
    finally:
        conn.close()


def get_full_profile(user_id: int, character_id: str) -> dict:
    """Merge global + per-character profile and return it. Per-character takes precedence; manual outranks auto."""
    global_profile = get_profile(user_id, "global")
    char_profile = get_profile(user_id, character_id) if character_id != "global" else {}

    merged = {}
    for key, data in global_profile.items():
        merged[key] = data
    for key, data in char_profile.items():
        # Per-character entries override global ones
        merged[key] = data

    return merged


# ── Long-term Memory ─────────────────────────────────────────


def save_memory(user_id: int, character_id: str, memory_type: str, content: str) -> None:
    """Persist a long-term memory entry. relationship overwrites; event appends."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        if memory_type == "relationship":
            # Keep only one relationship row — delete the existing one first
            cursor.execute(
                "DELETE FROM long_term_memory "
                "WHERE user_id = ? AND character_id = ? AND memory_type = 'relationship'",
                (user_id, character_id),
            )
        cursor.execute(
            "INSERT INTO long_term_memory (user_id, character_id, memory_type, content) "
            "VALUES (?, ?, ?, ?)",
            (user_id, character_id, memory_type, content),
        )
        conn.commit()
    finally:
        conn.close()


def get_memories(user_id: int, character_id: str) -> list[dict]:
    """Return all long-term memories for the user/character."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT memory_type, content, updated_at FROM long_term_memory "
            "WHERE user_id = ? AND character_id = ? "
            "ORDER BY updated_at ASC",
            (user_id, character_id),
        )
        return [{"type": row[0], "content": row[1], "updated_at": row[2]} for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_oldest_events(user_id: int, character_id: str, keep: int = 10) -> int:
    """Delete old event memories and keep at most `keep` rows."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM long_term_memory "
            "WHERE user_id = ? AND character_id = ? AND memory_type = 'event' "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, character_id, keep),
        )
        keep_ids = [row[0] for row in cursor.fetchall()]

        if not keep_ids:
            return 0

        placeholders = ",".join("?" * len(keep_ids))
        cursor.execute(
            f"DELETE FROM long_term_memory "
            f"WHERE user_id = ? AND character_id = ? AND memory_type = 'event' "
            f"AND id NOT IN ({placeholders})",
            (user_id, character_id, *keep_ids),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


# ── Admin ──


def is_admin(user_id: int) -> bool:
    """Check whether the user is an admin."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_admin FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False
    finally:
        conn.close()


def set_admin(user_id: int, admin: bool) -> None:
    """Set the user's admin flag. Inserts a user_settings row if missing."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_settings (user_id, is_admin) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_admin = excluded.is_admin",
            (user_id, int(admin)),
        )
        conn.commit()
    finally:
        conn.close()


# ── Usage tracking ──


def increment_usage(user_id: int, field: str) -> None:
    """Increment monthly usage by 1. field: 'turns', 'images', 'videos'."""
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO usage (telegram_id, month, {field}) VALUES (?, ?, 1) "
            f"ON CONFLICT(telegram_id, month) DO UPDATE SET {field} = {field} + 1",
            (user_id, month),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage(user_id: int) -> dict:
    """Return the current month's usage."""
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT turns, images, videos FROM usage WHERE telegram_id = ? AND month = ?",
            (user_id, month),
        )
        row = cursor.fetchone()
        if row:
            return {"turns": row[0], "images": row[1], "videos": row[2]}
        return {"turns": 0, "images": 0, "videos": 0}
    finally:
        conn.close()


def get_daily_image_count(user_id: int) -> int:
    """Return today's image usage count."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT images FROM usage_daily WHERE telegram_id = ? AND date = ?",
            (user_id, today),
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def increment_daily_images(user_id: int) -> None:
    """Increment today's image usage count by 1."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usage_daily (telegram_id, date, images) VALUES (?, ?, 1) "
            "ON CONFLICT(telegram_id, date) DO UPDATE SET images = images + 1",
            (user_id, today),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_video_count(user_id: int) -> int:
    """Return today's video usage count."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT videos FROM usage_daily WHERE telegram_id = ? AND date = ?",
            (user_id, today),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else 0
    finally:
        conn.close()


def increment_daily_videos(user_id: int) -> None:
    """Increment today's video usage count by 1."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usage_daily (telegram_id, date, videos) VALUES (?, ?, 1) "
            "ON CONFLICT(telegram_id, date) DO UPDATE SET videos = COALESCE(videos, 0) + 1",
            (user_id, today),
        )
        conn.commit()
    finally:
        conn.close()


# ── Stats ──


def get_stats() -> dict:
    """Return overall stats."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_settings")
        total_users = cursor.fetchone()[0]
        return {
            "total_users": total_users,
        }
    finally:
        conn.close()


# ── Onboarding ──


def is_onboarded(user_id: int) -> bool:
    """Return True iff both age_verified and terms_agreed are set."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT age_verified, terms_agreed FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        return bool(row[0]) and bool(row[1])
    finally:
        conn.close()


def set_onboarded(user_id: int) -> None:
    """Set age_verified=1, terms_agreed=1. Inserts a user_settings row if missing."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        if cursor.fetchone():
            cursor.execute(
                "UPDATE user_settings SET age_verified = 1, terms_agreed = 1 WHERE user_id = ?",
                (user_id,),
            )
        else:
            cursor.execute(
                "INSERT INTO user_settings (user_id, age_verified, terms_agreed) VALUES (?, 1, 1)",
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()


# ── Outfit ──


def get_outfit(user_id: int, char_id: str) -> dict | None:
    """Look up the user's per-character custom outfit. Returns None if absent."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT clothing, underwear, source FROM user_outfit "
            "WHERE telegram_id = ? AND character_id = ?",
            (user_id, char_id),
        )
        row = cursor.fetchone()
        if row:
            return {"clothing": row[0], "underwear": row[1], "source": row[2]}
        return None
    finally:
        conn.close()


def set_outfit(user_id: int, char_id: str, clothing: str, underwear: str = "", source: str = "custom") -> None:
    """Save the user's per-character outfit (overwrite)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_outfit (telegram_id, character_id, clothing, underwear, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(telegram_id, character_id) "
            "DO UPDATE SET clothing = excluded.clothing, underwear = excluded.underwear, "
            "source = excluded.source, updated_at = CURRENT_TIMESTAMP",
            (user_id, char_id, clothing, underwear, source),
        )
        conn.commit()
    finally:
        conn.close()


def reset_outfit(user_id: int, char_id: str) -> None:
    """Reset the user's per-character outfit (revert to preset)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_outfit WHERE telegram_id = ? AND character_id = ?",
            (user_id, char_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── Location Context (global cache, P10 Phase 2) ──


def _normalize_location_key(key: str) -> str:
    """Normalize a location key. Used by every save/get.
    - strip, lowercase
    - non-[a-z0-9_] → underscore
    - collapse consecutive underscores
    - strip leading/trailing underscores
    """
    if not key:
        return ""
    s = key.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)  # Korean/whitespace/special chars → _
    s = re.sub(r"_+", "_", s)            # collapse consecutive _
    return s.strip("_")


def get_location_context(location_key: str) -> dict | None:
    """Look up location context. Returns None if absent.

    Returns:
        {"description": str, "danbooru_background": str} or None
    """
    key = _normalize_location_key(location_key)
    if not key:
        return None
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT description, danbooru_background FROM location_context WHERE location_key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row:
            return {"description": row[0], "danbooru_background": row[1]}
        return None
    finally:
        conn.close()


_LIGHTING_STRIP_EXACT = {
    "natural_light", "sunlight", "moonlight", "candlelight",
    "starlight", "daylight", "soft_light",
}
_LIGHTING_STRIP_WORDS = {
    "lighting", "ambient", "ambience", "ambiance", "glow",
    "fluorescent", "shadows", "shadow", "dappled", "atmosphere",
    "steamy", "lamp", "lamps", "spotlight", "spotlights",
}


def _strip_lighting_tags(danbooru_background: str) -> str:
    """Strip lighting / lamp / ambient tags entirely (final defence at save time).

    Per CLAUDE.md: never persist colour-grading or light-source tags. Even if
    Grok ignores the prompt instructions, this catches it.
    """
    if not danbooru_background:
        return danbooru_background
    tags = [t.strip() for t in danbooru_background.split(",") if t.strip()]
    kept = []
    for tag in tags:
        t = tag.lower()
        if t in _LIGHTING_STRIP_EXACT:
            continue
        if t.endswith("_light") or t.endswith("_lights"):
            continue
        words = set(t.split("_"))
        if words & _LIGHTING_STRIP_WORDS:
            continue
        kept.append(tag)
    return ", ".join(kept)


def save_location_context(location_key: str, description: str, danbooru_background: str) -> None:
    """Upsert location context (global cache shared by every user).

    Always strips lighting / lamp / ambient tags before saving (CLAUDE.md rule).
    """
    key = _normalize_location_key(location_key)
    if not key:
        return
    clean_bg = _strip_lighting_tags(danbooru_background)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO location_context (location_key, description, danbooru_background, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(location_key) DO UPDATE SET "
            "description = excluded.description, "
            "danbooru_background = excluded.danbooru_background, "
            "updated_at = CURRENT_TIMESTAMP",
            (key, description, clean_bg),
        )
        conn.commit()
    finally:
        conn.close()


def increment_lora_usage(pose_key: str) -> None:
    """Increment the pose-preset call counter by 1 (upsert).

    SFW fork: tracks usage of pose_motion_presets.json SFW poses.
    The function and table names (increment_lora_usage / lora_preset_usage) are
    schema-level identifiers retained for backward compatibility.

    - pose_key: a key in pose_motion_presets.json (`generic`, `portrait_static_sfw`, `standing`, etc.)
    """
    if not pose_key or not isinstance(pose_key, str):
        return
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO lora_preset_usage (pose_key, call_count, last_used_at) "
            "VALUES (?, 1, CURRENT_TIMESTAMP) "
            "ON CONFLICT(pose_key) DO UPDATE SET "
            "call_count = call_count + 1, "
            "last_used_at = CURRENT_TIMESTAMP",
            (pose_key.strip(),),
        )
        conn.commit()
    finally:
        conn.close()


def get_lora_usage_stats() -> list[dict]:
    """Return every LoRA preset call record sorted by call_count descending.

    Returns: [{"pose_key": str, "call_count": int, "last_used_at": str}, ...]
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pose_key, call_count, last_used_at "
            "FROM lora_preset_usage "
            "ORDER BY call_count DESC, last_used_at DESC"
        )
        rows = cursor.fetchall()
        return [
            {"pose_key": r[0], "call_count": r[1], "last_used_at": r[2]}
            for r in rows
        ]
    finally:
        conn.close()


def _migrate_location_keys() -> None:
    """Consolidate location_key in the DB under _normalize_location_key.

    - location_context: for duplicate groups, keep the row with the latest updated_at and delete the rest.
    - location_context: even for single rows, rewrite the key if stored != normalized.
    - character_stats.location: rewrite every value to its normalized form.

    Idempotent: when stored == normalized this is a no-op.
    """
    import logging as _logging
    log = _logging.getLogger(__name__)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # 1. Merge duplicate location_context rows
        cursor.execute(
            "SELECT location_key, description, danbooru_background, updated_at FROM location_context"
        )
        rows = cursor.fetchall()
        groups: dict[str, list] = {}
        for row in rows:
            norm = _normalize_location_key(row[0])
            if not norm:
                continue
            groups.setdefault(norm, []).append(row)

        merged = 0
        renormalized = 0
        for norm, group in groups.items():
            if len(group) > 1:
                # Keep only the row with the latest updated_at — delete the rest.
                # updated_at NULL → bubbles to the front (treated as oldest).
                sorted_rows = sorted(
                    group,
                    key=lambda r: (r[3] or ""),
                    reverse=True,
                )
                keeper = sorted_rows[0]
                losers = sorted_rows[1:]
                # Delete every existing row first so the keeper's key can also be rewritten to normalized form, then upsert the keeper
                for row in group:
                    cursor.execute(
                        "DELETE FROM location_context WHERE location_key = ?",
                        (row[0],),
                    )
                cursor.execute(
                    "INSERT INTO location_context (location_key, description, danbooru_background, updated_at) "
                    "VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
                    (norm, keeper[1], keeper[2], keeper[3]),
                )
                merged += len(losers)
            else:
                row = group[0]
                if row[0] != norm:
                    # Single row but needs key rewriting — delete and reinsert (INSERT OR REPLACE handles a post-normalization key collision)
                    cursor.execute(
                        "DELETE FROM location_context WHERE location_key = ?",
                        (row[0],),
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO location_context (location_key, description, danbooru_background, updated_at) "
                        "VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
                        (norm, row[1], row[2], row[3]),
                    )
                    renormalized += 1

        # 2. Normalize character_stats.location
        cursor.execute(
            "SELECT rowid, location FROM character_stats WHERE location IS NOT NULL AND location <> ''"
        )
        stats_rows = cursor.fetchall()
        stats_renormalized = 0
        for rowid, loc in stats_rows:
            norm = _normalize_location_key(loc)
            if norm != (loc or ""):
                cursor.execute(
                    "UPDATE character_stats SET location = ? WHERE rowid = ?",
                    (norm, rowid),
                )
                stats_renormalized += 1

        conn.commit()

        total_renormalized = renormalized + stats_renormalized
        if merged or total_renormalized:
            log.info(
                "Location key migration: %d groups processed, %d duplicates merged, %d keys renormalized.",
                len(groups), merged, total_renormalized,
            )
        else:
            log.debug(
                "Location key migration: %d groups processed, 0 duplicates merged, 0 keys renormalized (idempotent no-op).",
                len(groups),
            )
    finally:
        conn.close()


def _migrate_profile_keys() -> None:
    """Consolidate user_profile.key under canonicalize(key).

    - Alias rows are renamed to the canonical key (UPDATE).
    - If a canonical row already exists for the same (user_id, character_id),
      keep only the latest updated_at row and DELETE the alias row.
    - When stored == canonicalize(stored) this is a no-op (idempotent).
    """
    import logging as _logging
    log = _logging.getLogger(__name__)

    # Avoid circular import — lazy-load
    from src.profile_keys import canonicalize

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, character_id, key, value, source, updated_at FROM user_profile"
        )
        rows = cursor.fetchall()

        normalized = 0
        conflicts = 0

        for user_id, character_id, key, value, source, updated_at in rows:
            canon = canonicalize(key)
            if canon == key:
                continue  # already canonical — skip

            # Check whether a canonical row exists for the same (user_id, character_id)
            cursor.execute(
                "SELECT value, source, updated_at FROM user_profile "
                "WHERE user_id = ? AND character_id = ? AND key = ?",
                (user_id, character_id, canon),
            )
            existing = cursor.fetchone()

            if existing is None:
                # Simple rename — update the alias row's key to the canonical key
                # (PK is part of the row — UPDATE rewrites it)
                cursor.execute(
                    "UPDATE user_profile SET key = ?, updated_at = updated_at "
                    "WHERE user_id = ? AND character_id = ? AND key = ?",
                    (canon, user_id, character_id, key),
                )
                normalized += 1
            else:
                # Conflict — keep the row with the latest updated_at, delete the rest
                existing_value, existing_source, existing_updated = existing
                # None-safe comparison (NULL is treated as oldest)
                alias_ts = updated_at or ""
                canon_ts = existing_updated or ""
                if alias_ts > canon_ts:
                    # alias is newer — overwrite the canonical row with the alias values, then delete the alias row
                    cursor.execute(
                        "UPDATE user_profile SET value = ?, source = ?, updated_at = ? "
                        "WHERE user_id = ? AND character_id = ? AND key = ?",
                        (value, source, updated_at, user_id, character_id, canon),
                    )
                cursor.execute(
                    "DELETE FROM user_profile "
                    "WHERE user_id = ? AND character_id = ? AND key = ?",
                    (user_id, character_id, key),
                )
                conflicts += 1

        conn.commit()

        if normalized or conflicts:
            log.info(
                "Profile key migration: %d keys normalized, %d conflicts resolved.",
                normalized, conflicts,
            )
        else:
            log.debug(
                "Profile key migration: 0 keys normalized, 0 conflicts resolved (idempotent no-op)."
            )
    finally:
        conn.close()


def _migrate_saved_chars_v3() -> None:
    """Recreate saved_characters under the nested JSON schema — DROP & CREATE on old v1/v2 schemas.

    Dev-branch only — no prod data exists, so no need for lossless migration.
    Aligns with images/char*.json's 14 sub-attribute structure.

    Detection: missing body_shape_json column = old schema → DROP. The init_db
    CREATE TABLE recreates the new schema (idempotent: second call is a no-op).
    """
    import logging as _logging
    log = _logging.getLogger(__name__)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(saved_characters)")
        cols = {row[1] for row in cursor.fetchall()}
        if not cols:
            log.debug("saved_characters table missing — init_db CREATE will handle.")
            return
        if "body_shape_json" in cols:
            log.debug("saved_characters v3 schema already in place (idempotent no-op).")
            return
        log.warning("saved_characters: old schema detected — DROP & CREATE under v3 nested JSON schema.")
        cursor.execute("DROP TABLE saved_characters")
        conn.commit()
    finally:
        conn.close()


# ── Character stats (in-memory cache + deferred DB writes) ──

# In-memory cache: {(user_id, char_id): {"fixation": int, "mood": str, "location": str, "_dirty": bool, "_last_activity": float}}
_stats_cache: dict[tuple[int, str], dict] = {}
# Flush timers: {(user_id, char_id): asyncio.Task}
_flush_timers: dict[tuple[int, str], object] = {}
# Flush delay (seconds)
STATS_FLUSH_DELAY = 300  # 5 minutes


def get_character_stats(user_id: int, character_id: str) -> dict:
    """Look up character stats. Hits the in-memory cache first; otherwise loads from DB → cache."""
    import time as _time
    key = (user_id, character_id)

    # Cache hit
    if key in _stats_cache:
        cached = _stats_cache[key]
        result = {k: v for k, v in cached.items() if not k.startswith("_")}
        result["total_turns"] = cached.get("_total_turns", 0)
        result["mood_lock"] = cached.get("_mood_lock")
        return result

    # Load from DB
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fixation, mood, location, updated_at, total_turns FROM character_stats "
            "WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        )
        row = cursor.fetchone()
        if row:
            stats = {"fixation": row[0], "mood": row[1], "location": row[2] or ""}
            stats["_dirty"] = False
            stats["_last_activity"] = _time.time()
            stats["_total_turns"] = row[4] if len(row) > 4 else 0
            _stats_cache[key] = stats
            result = {k: v for k, v in stats.items() if not k.startswith("_")}
            result["total_turns"] = stats.get("_total_turns", 0)
            result["mood_lock"] = stats.get("_mood_lock")
            return result

        # Otherwise insert per-character initial values
        initial = INITIAL_STATS.get(character_id, {"fixation": 20, "mood": "neutral"})
        cursor.execute(
            "INSERT INTO character_stats (user_id, character_id, fixation, mood) "
            "VALUES (?, ?, ?, ?)",
            (user_id, character_id, initial["fixation"], initial["mood"]),
        )
        conn.commit()
        cache_entry = dict(initial)
        cache_entry.setdefault("location", "")
        cache_entry["_dirty"] = False
        cache_entry["_last_activity"] = _time.time()
        cache_entry["_total_turns"] = 0
        _stats_cache[key] = cache_entry
        result = dict(initial)
        result["location"] = ""
        result["total_turns"] = 0
        result["mood_lock"] = None
        return result
    finally:
        conn.close()


def update_character_stats(
    user_id: int, character_id: str,
    fixation_delta: int = 0, mood: str = "",
    location: str = "",
    stat_limits: dict | None = None,
) -> None:
    """Update stats. Writes to the cache only (DB write is deferred).

    - fixation_delta: clamped per-message (per-character stat_limits, else global STAT_LIMITS).
    - mood/location: empty string → keep the previous value.
    - DB flush happens after 5 minutes or when summarization is triggered.
    - stat_limits: per-character limit dict; falls back to global STAT_LIMITS.
    """
    # Look up current values (cache or DB)
    current = get_character_stats(user_id, character_id)
    key = (user_id, character_id)

    # Delta clamp (per-message change limit) — per-character limits take precedence
    limits = stat_limits if stat_limits else STAT_LIMITS
    fix_up = limits.get("fixation", STAT_LIMITS["fixation"])["up"]
    fix_down = limits.get("fixation", STAT_LIMITS["fixation"])["down"]

    fixation_delta = max(fix_down, min(fix_up, fixation_delta))

    new_fixation = current["fixation"] + fixation_delta

    # Range clamp (0–100)
    new_fixation = max(STAT_RANGE["min"], min(STAT_RANGE["max"], new_fixation))

    # mood/location: empty string → keep previous
    new_mood = mood if mood else current["mood"]
    # Always store location in normalized form (avoid DB duplicates)
    new_location = _normalize_location_key(location) if location else current.get("location", "")

    # Enforce mood_lock — when locked, the LLM cannot change the mood
    prev = _stats_cache.get(key, {})
    if prev.get("_mood_lock"):
        new_mood = prev["_mood_lock"]["mood"]

    # Cache-only write (deferred DB write) — preserve mood_lock
    import time as _time
    _stats_cache[key] = {
        "fixation": new_fixation,
        "mood": new_mood,
        "location": new_location,
        "_dirty": True,
        "_last_activity": _time.time(),
        "_mood_lock": prev.get("_mood_lock"),
        "_total_turns": prev.get("_total_turns", 0),
    }

    # Schedule the auto-flush timer (5 minutes from now)
    _schedule_flush(user_id, character_id)


def increment_total_turns(user_id: int, character_id: str) -> int:
    """Increment the per-character cumulative turn count by 1 and return the new value."""
    current = get_character_stats(user_id, character_id)
    key = (user_id, character_id)
    cached = _stats_cache.get(key, {})
    new_turns = cached.get("_total_turns", 0) + 1
    cached["_total_turns"] = new_turns
    cached["_dirty"] = True
    _stats_cache[key] = cached
    _schedule_flush(user_id, character_id)
    return new_turns


def flush_character_stats(user_id: int, character_id: str) -> None:
    """Flush cached stats to the DB immediately. Called on summarization trigger or timer expiry."""
    key = (user_id, character_id)
    cached = _stats_cache.get(key)
    if not cached or not cached.get("_dirty"):
        return

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE character_stats SET fixation = ?, mood = ?, location = ?, "
            "total_turns = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND character_id = ?",
            (cached["fixation"], cached["mood"], cached.get("location", ""),
             cached.get("_total_turns", 0),
             user_id, character_id),
        )
        conn.commit()
        cached["_dirty"] = False
    finally:
        conn.close()


def flush_all_stats() -> None:
    """Flush every dirty cache entry to the DB. Called at bot shutdown."""
    for (uid, cid), cached in _stats_cache.items():
        if cached.get("_dirty"):
            flush_character_stats(uid, cid)


def _schedule_flush(user_id: int, character_id: str) -> None:
    """Arm an auto-flush timer 5 minutes from now. Resets any existing timer."""
    import asyncio
    key = (user_id, character_id)

    # Cancel any existing timer
    old_timer = _flush_timers.get(key)
    if old_timer and not old_timer.done():
        old_timer.cancel()

    async def _delayed_flush():
        await asyncio.sleep(STATS_FLUSH_DELAY)
        flush_character_stats(user_id, character_id)
        _flush_timers.pop(key, None)

    try:
        loop = asyncio.get_event_loop()
        _flush_timers[key] = loop.create_task(_delayed_flush())
    except RuntimeError:
        # No event loop — flush synchronously
        flush_character_stats(user_id, character_id)


# ── Data deletion ──


def delete_all_user_data(user_id: int) -> dict:
    """Delete every piece of data belonging to a user (GDPR /deletedata).

    Returns:
        Dict mapping table name to the number of deleted rows.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        deleted = {}

        for table, col in [
            ("chat_history", "user_id"),
            ("chat_summary", "user_id"),
            ("user_profile", "user_id"),
            ("long_term_memory", "user_id"),
            ("character_stats", "user_id"),
            ("user_outfit", "telegram_id"),
            ("usage", "telegram_id"),
            ("usage_daily", "telegram_id"),
            ("saved_characters", "user_id"),
        ]:
            cursor.execute(f"DELETE FROM {table} WHERE {col} = ?", (user_id,))
            deleted[table] = cursor.rowcount

        # Delete the user_settings row too (also clears onboarding state)
        cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        deleted["user_settings"] = cursor.rowcount

        conn.commit()
        return deleted
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Saved Characters (image-generator character store, Feature 1)
# ═══════════════════════════════════════════════════════════════════════

import re as _re_saved

_SAVED_CHAR_NAME_RE = _re_saved.compile(r"^[a-zA-Z0-9_]{1,20}$")
SAVED_CHAR_MAX_SLOTS = 3


def is_valid_saved_char_name(name: str) -> bool:
    """Validate a character name — 1–20 chars of alphanumerics/underscore."""
    return bool(name) and bool(_SAVED_CHAR_NAME_RE.match(name))


def _deserialize_nested(raw: str | None, default_keys: tuple[str, ...]) -> dict:
    """Deserialize a JSON string into a dict. On parse failure or empty input, return a dict with default_keys all empty."""
    if not raw:
        return {k: "" for k in default_keys}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {k: "" for k in default_keys}
    if not isinstance(data, dict):
        return {k: "" for k in default_keys}
    return {k: (str(data.get(k, "")).strip() if data.get(k) is not None else "") for k in default_keys}


_BODY_SHAPE_KEYS = ("size", "build", "curve", "accent", "ass")
_BREAST_KEYS = ("size", "feature")


def save_character(
    user_id: int,
    slot: int,
    name: str,
    appearance_tags: str,
    clothing: str = "",
    underwear: str = "",
    body_shape: dict | None = None,
    breast: dict | None = None,
) -> None:
    """Save/overwrite a character (upsert by user_id + slot).

    Nested schema (P15-3 v3, mirrors images/char*.json):
        appearance_tags : flat string (eye/hair/face/skin/age/species)
        clothing        : flat string (outerwear, shoes, accessories)
        underwear       : flat string (intimate wear)
        body_shape      : {"size": "", "build": "", "curve": "", "accent": "", "ass": ""}
        breast          : {"size": "", "feature": ""}
    """
    if not (1 <= slot <= SAVED_CHAR_MAX_SLOTS):
        raise ValueError(f"slot must be 1-{SAVED_CHAR_MAX_SLOTS}, got {slot}")
    if not is_valid_saved_char_name(name):
        raise ValueError(f"invalid name: {name!r}")

    body_shape_json = json.dumps(body_shape or {}, ensure_ascii=False)
    breast_json = json.dumps(breast or {}, ensure_ascii=False)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO saved_characters (
                user_id, slot, name,
                appearance_tags, clothing, underwear,
                body_shape_json, breast_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, slot) DO UPDATE SET
                name = excluded.name,
                appearance_tags = excluded.appearance_tags,
                clothing = excluded.clothing,
                underwear = excluded.underwear,
                body_shape_json = excluded.body_shape_json,
                breast_json = excluded.breast_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id, slot, name,
                appearance_tags, clothing, underwear,
                body_shape_json, breast_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_saved_char(r: tuple) -> dict:
    """Convert a saved_characters row into a nested dict."""
    return {
        "slot": r[0],
        "name": r[1],
        "appearance_tags": r[2],
        "clothing": r[3] or "",
        "underwear": r[4] or "",
        "body_shape": _deserialize_nested(r[5], _BODY_SHAPE_KEYS),
        "breast": _deserialize_nested(r[6], _BREAST_KEYS),
        "created_at": r[7],
        "updated_at": r[8],
    }


def list_saved_characters(user_id: int) -> list[dict]:
    """Return the user's saved characters (ascending slot order)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT slot, name, appearance_tags, clothing, underwear,
                   body_shape_json, breast_json,
                   created_at, updated_at
            FROM saved_characters WHERE user_id = ? ORDER BY slot ASC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        return [_row_to_saved_char(r) for r in rows]
    finally:
        conn.close()


def get_saved_character_by_name(user_id: int, name: str) -> dict | None:
    """Look up a saved character by name (case-sensitive)."""
    if not name:
        return None
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT slot, name, appearance_tags, clothing, underwear,
                   body_shape_json, breast_json,
                   created_at, updated_at
            FROM saved_characters WHERE user_id = ? AND name = ?
            """,
            (user_id, name),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return _row_to_saved_char(r)
    finally:
        conn.close()


def get_saved_character_by_slot(user_id: int, slot: int) -> dict | None:
    """Look up a saved character by slot."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT slot, name, appearance_tags, clothing, underwear,
                   body_shape_json, breast_json,
                   created_at, updated_at
            FROM saved_characters WHERE user_id = ? AND slot = ?
            """,
            (user_id, slot),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return _row_to_saved_char(r)
    finally:
        conn.close()


def delete_saved_character(user_id: int, slot: int) -> bool:
    """Delete the character in the given slot. Returns True on successful delete."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM saved_characters WHERE user_id = ? AND slot = ?",
            (user_id, slot),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def find_available_slot(user_id: int) -> int | None:
    """Find an available slot (1–3). Returns None if all slots are taken."""
    existing = {c["slot"] for c in list_saved_characters(user_id)}
    for s in range(1, SAVED_CHAR_MAX_SLOTS + 1):
        if s not in existing:
            return s
    return None
