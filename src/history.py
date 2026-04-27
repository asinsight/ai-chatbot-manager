"""SQLite 기반 유저별 채팅 히스토리 관리 모듈.

멀티 캐릭터 지원: character_id 컬럼으로 캐릭터별 히스토리 분리,
user_settings 테이블로 유저별 활성 캐릭터 관리.
"""

import json
import os
import re
import sqlite3

# ── 캐릭터 수치 시스템 상수 ──

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


# 프로젝트 루트 기준 data/chat.db 경로 계산
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_DB_PATH = os.path.join(_DATA_DIR, "chat.db")


def _get_connection() -> sqlite3.Connection:
    """SQLite 커넥션을 반환한다."""
    return sqlite3.connect(_DB_PATH)


def init_db() -> None:
    """DB 초기화 — data/ 디렉토리 생성, 테이블/인덱스 생성, 마이그레이션.

    bot.py 시작 시 한 번 호출한다.
    """
    os.makedirs(_DATA_DIR, exist_ok=True)

    # saved_characters v3 마이그레이션 (CREATE TABLE 전에 구식 schema DROP)
    # CREATE TABLE IF NOT EXISTS는 기존 테이블이 남아있으면 no-op이라 신규 컬럼이
    # 추가되지 않는다 — 따라서 구식 schema 감지 시 먼저 DROP한 뒤 CREATE TABLE에 위임.
    try:
        _migrate_saved_chars_v3()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Saved characters v3 migration failed: %s", _mig_e)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # WAL 모드 활성화
        cursor.execute("PRAGMA journal_mode=WAL")

        # --- chat_history 테이블 ---
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

        # 마이그레이션: 기존 테이블에 character_id 컬럼 추가
        try:
            cursor.execute(
                "ALTER TABLE chat_history ADD COLUMN character_id TEXT DEFAULT 'default'"
            )
        except sqlite3.OperationalError:
            # 이미 컬럼이 존재하면 무시
            pass

        # character_id 포함 복합 인덱스
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_character
            ON chat_history(user_id, character_id)
            """
        )

        # --- user_settings 테이블 ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                active_character TEXT NOT NULL DEFAULT 'char01'
            )
            """
        )

        # --- chat_summary 테이블 ---
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

        # --- user_profile 테이블 ---
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

        # --- long_term_memory 테이블 ---
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

        # 마이그레이션: user_settings 확장
        for col_sql in [
            "ALTER TABLE user_settings ADD COLUMN username TEXT",
            "ALTER TABLE user_settings ADD COLUMN tier TEXT DEFAULT 'free'",
            "ALTER TABLE user_settings ADD COLUMN age_verified BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN terms_agreed BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "ALTER TABLE user_settings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE user_settings ADD COLUMN tier_started TIMESTAMP",
            "ALTER TABLE user_settings ADD COLUMN tier_expires TIMESTAMP",
        ]:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        # --- usage 테이블 ---
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

        # --- payments 테이블 ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                stars_amount INTEGER NOT NULL,
                tier_granted TEXT NOT NULL,
                days_granted INTEGER NOT NULL,
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                telegram_charge_id TEXT
            )
            """
        )

        # --- user_outfit 테이블 ---
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

        # --- 쿠폰 테이블 ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS coupons (
                code TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                days INTEGER NOT NULL,
                max_uses INTEGER NOT NULL DEFAULT 0,
                used_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
            """
        )

        # --- 쿠폰 사용 기록 (1인 1회) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS coupon_redemptions (
                code TEXT NOT NULL,
                telegram_id INTEGER NOT NULL,
                redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (code, telegram_id)
            )
            """
        )

        # --- 일일 이미지 사용량 ---
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

        # --- 캐릭터 수치 (character_stats) ---
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

        # usage_daily에 videos 컬럼 마이그레이션
        try:
            cursor.execute("ALTER TABLE usage_daily ADD COLUMN videos INTEGER DEFAULT 0")
        except Exception:
            pass  # 이미 존재

        # usage_daily에 turns 컬럼 마이그레이션 (Free 티어 일일 턴 제한)
        try:
            cursor.execute("ALTER TABLE usage_daily ADD COLUMN turns INTEGER DEFAULT 0")
        except Exception:
            pass  # 이미 존재

        # --- location_context (글로벌 로케이션 캐시, P10 Phase 2) ---
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

        # LoRA preset usage stats — 각 pose_key(lora_presets key)가 몇 번 선택됐는지
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lora_preset_usage (
                pose_key TEXT PRIMARY KEY,
                call_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # --- saved_characters (이미지 제네레이터 캐릭터 저장, Feature 1) ---
        # 유저별 최대 3개 슬롯. 이름(영문/숫자/언더스코어) + danbooru 외형/의상 태그.
        # seed/anchor 이미지는 저장하지 않음 (PM 결정) — 재소환 시 랜덤 시드, 태그로만 재현.
        # nested 스키마 (P15-3 v3, images/char*.json와 동일 구조):
        #   appearance_tags : flat string (eye/hair/face/skin/age/species)
        #   clothing        : flat string (outerwear/shoes/accessories)
        #   underwear       : flat string (intimate wear)
        #   body_shape_json : {"size", "build", "curve", "accent", "ass"}
        #   breast_json     : {"size", "feature"}
        # init_db 진입 직전 _migrate_saved_chars_v3가 구식 schema 감지 시 DROP 처리.
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

    # 로케이션 키 정규화 마이그레이션 (idempotent)
    try:
        _migrate_location_keys()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Location key migration failed: %s", _mig_e)

    # user_profile 키 canonicalization 마이그레이션 (idempotent)
    try:
        _migrate_profile_keys()
    except Exception as _mig_e:
        import logging as _logging
        _logging.getLogger(__name__).warning("Profile key migration failed: %s", _mig_e)


def save_message(
    user_id: int, role: str, content: str, character_id: str = "default"
) -> None:
    """메시지 한 건을 히스토리에 저장한다."""
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
    """유저의 특정 캐릭터와의 최근 N개 메시지를 시간순(오래된 → 최신)으로 반환한다.

    Args:
        user_id: 텔레그램 유저 ID
        limit: 가져올 메시지 수. 환경변수 HISTORY_LIMIT 으로도 설정 가능.
        character_id: 캐릭터 ID. 기본값 'default'.

    Returns:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """
    # 환경변수가 설정되어 있으면 기본값 대신 사용
    env_limit = os.environ.get("HISTORY_LIMIT")
    if env_limit is not None and limit == 20:
        limit = int(env_limit)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # 최신 N개를 가져온 뒤 시간순으로 정렬
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
    """유저의 히스토리를 삭제한다. (/clear 커맨드용)

    Args:
        user_id: 텔레그램 유저 ID
        character_id: 지정하면 해당 캐릭터 히스토리만 삭제.
                      None이면 유저의 전체 히스토리 삭제 (하위 호환).
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
    """유저의 활성 캐릭터 ID를 반환한다. 미설정 시 'char01'."""
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
    """유저의 활성 캐릭터 ID를 설정한다."""
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
    """요약문을 저장한다."""
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
    """유저의 특정 캐릭터와의 최신 요약문을 반환한다. 없으면 None."""
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
    """요약 완료 후 오래된 메시지를 삭제한다. 최근 keep_recent개만 유지.

    Returns:
        삭제된 메시지 수
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # 최근 keep_recent개의 id를 가져온다
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
    """유저의 특정 캐릭터와의 메시지 수를 반환한다."""
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
    """유저 프로필 항목을 설정한다. (upsert)"""
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
    """특정 범위의 프로필을 dict로 반환한다. {"key": {"value": "...", "source": "..."}, ...}"""
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
    """글로벌 + 캐릭터별 프로필을 merge하여 반환한다. 캐릭터별이 우선, manual이 auto보다 우선."""
    global_profile = get_profile(user_id, "global")
    char_profile = get_profile(user_id, character_id) if character_id != "global" else {}

    merged = {}
    for key, data in global_profile.items():
        merged[key] = data
    for key, data in char_profile.items():
        # 캐릭터별은 글로벌을 덮어씀
        merged[key] = data

    return merged


# ── Long-term Memory ─────────────────────────────────────────


def save_memory(user_id: int, character_id: str, memory_type: str, content: str) -> None:
    """장기 기억을 저장한다. relationship은 덮어쓰기, event는 추가."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        if memory_type == "relationship":
            # relationship은 1개만 유지 — 기존 삭제 후 삽입
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
    """유저의 특정 캐릭터와의 장기 기억을 전부 반환한다."""
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
    """오래된 event 기억을 삭제하여 최대 keep개만 유지한다."""
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
    """유저가 Admin인지 확인한다."""
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
    """유저의 Admin 상태를 설정한다. user_settings 행이 없으면 생성."""
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


# ── 티어 ──


def get_user_tier(user_id: int) -> str:
    """유저의 티어를 반환한다. 미설정 시 'free'."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tier FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else "free"
    finally:
        conn.close()


def set_user_tier(user_id: int, tier: str, days: int) -> None:
    """유저의 티어를 설정한다."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_settings (user_id, tier, tier_started, tier_expires) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, datetime('now', '+' || ? || ' days')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "tier = excluded.tier, tier_started = CURRENT_TIMESTAMP, "
            "tier_expires = datetime(MAX(COALESCE(user_settings.tier_expires, '2000-01-01'), datetime('now')), '+' || ? || ' days')",
            (user_id, tier, days, days),
        )
        conn.commit()
    finally:
        conn.close()


# ── Usage 추적 ──


def increment_usage(user_id: int, field: str) -> None:
    """월별 사용량을 1 증가시킨다. field: 'turns', 'images', 'videos'."""
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
    """현재 월의 사용량을 반환한다."""
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
    """오늘의 이미지 사용량을 반환한다."""
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
    """오늘의 이미지 사용량을 1 증가시킨다."""
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


def get_daily_turn_count(user_id: int) -> int:
    """오늘의 대화 턴 사용량을 반환한다 (Free 티어 일일 제한용)."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT turns FROM usage_daily WHERE telegram_id = ? AND date = ?",
            (user_id, today),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0
    finally:
        conn.close()


def increment_daily_turns(user_id: int) -> None:
    """오늘의 대화 턴 사용량을 1 증가시킨다."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usage_daily (telegram_id, date, turns) VALUES (?, ?, 1) "
            "ON CONFLICT(telegram_id, date) DO UPDATE SET turns = turns + 1",
            (user_id, today),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_video_count(user_id: int) -> int:
    """오늘의 비디오 사용량을 반환한다."""
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
    """오늘의 비디오 사용량을 1 증가시킨다."""
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


# ── 결제 ──


def save_payment(user_id: int, stars: int, tier: str, days: int, charge_id: str) -> None:
    """결제 내역을 저장한다."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (telegram_id, stars_amount, tier_granted, days_granted, telegram_charge_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, stars, tier, days, charge_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── 통계 ──


def get_stats() -> dict:
    """전체 통계를 반환한다."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_settings")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT tier, COUNT(*) FROM user_settings GROUP BY tier")
        tier_counts = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) FROM payments")
        total_payments = cursor.fetchone()[0]
        return {
            "total_users": total_users,
            "tier_counts": tier_counts,
            "total_payments": total_payments,
        }
    finally:
        conn.close()


# ── 온보딩 ──


def is_onboarded(user_id: int) -> bool:
    """age_verified + terms_agreed 둘 다 True인지 확인."""
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
    """age_verified=1, terms_agreed=1 설정. user_settings 행이 없으면 생성."""
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
    """유저의 캐릭터별 커스텀 의상 조회. 없으면 None."""
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
    """유저의 캐릭터별 의상 저장 (덮어쓰기)."""
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
    """유저의 캐릭터별 의상을 초기화 (preset으로 복귀)."""
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


# ── Location Context (글로벌 캐시, P10 Phase 2) ──


def _normalize_location_key(key: str) -> str:
    """Location key 정규화. 모든 save/get에서 사용.
    - strip, lowercase
    - 영숫자/언더스코어 외 → 언더스코어
    - 연속 언더스코어 축약
    - 양끝 언더스코어 제거
    """
    if not key:
        return ""
    s = key.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)  # 한글/공백/특수문자 → _
    s = re.sub(r"_+", "_", s)            # 연속 _ 축약
    return s.strip("_")


def get_location_context(location_key: str) -> dict | None:
    """로케이션 컨텍스트 조회. 없으면 None.

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
    """조명/램프/ambient 태그를 완전히 제거 (저장 시점 최종 방어선).

    CLAUDE.md 규칙: 색감/광원 태그 DB 저장 금지. Grok이 프롬프트 무시하고 넣어도 여기서 끊음.
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
    """로케이션 컨텍스트 upsert (글로벌 캐시, 모든 유저가 공유).

    저장 전 조명/램프/ambient 태그를 항상 strip (CLAUDE.md 규칙).
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
    """LoRA preset 호출 카운터를 1 증가 (upsert).

    - pose_key: lora_presets.json 키 (`cowgirl_position`, `general_nsfw` 등)
    - 텍스트 전용 preset(`generic`, `portrait_static_sfw`)도 기록 가능 — 호출부가 넘긴 모든 키를 저장.
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
    """모든 LoRA preset 호출 기록을 call_count 내림차순으로 반환.

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
    """DB의 location_key를 _normalize_location_key 기준으로 통합.

    - location_context: 중복 그룹의 경우 최신 updated_at 1개만 유지, 나머지 삭제.
    - location_context: 단일 행이어도 스토어된 키 ≠ 정규화 키라면 키 재작성.
    - character_stats.location: 전부 정규화 형태로 업데이트.

    idempotent: stored == normalized이면 no-op.
    """
    import logging as _logging
    log = _logging.getLogger(__name__)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # 1. location_context 중복 병합
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
                # 최신 updated_at 1개만 유지 — 나머지 삭제
                # updated_at NULL → 맨 앞으로 밀어냄 (가장 오래된 것으로 처리)
                sorted_rows = sorted(
                    group,
                    key=lambda r: (r[3] or ""),
                    reverse=True,
                )
                keeper = sorted_rows[0]
                losers = sorted_rows[1:]
                # 먼저 keeper의 키도 정규화 형태로 변경할 수 있도록, 모든 기존 행 삭제 후 keeper upsert
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
                    # 단일 행이지만 키 정규화 필요 — 기존 삭제 후 insert (혹시 정규화 후 키 충돌 시 대비해 INSERT OR REPLACE)
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

        # 2. character_stats.location 정규화
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
    """user_profile.key를 canonicalize(key) 기준으로 통합.

    - alias 행은 canonical 행으로 이름 변경 (UPDATE).
    - 같은 (user_id, character_id)에 canonical 행이 이미 있으면 updated_at 최신 것만 유지, alias 행 DELETE.
    - stored == canonicalize(stored)이면 no-op (idempotent).
    """
    import logging as _logging
    log = _logging.getLogger(__name__)

    # 순환 import 방지 — 지연 로드
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
                continue  # 이미 canonical — skip

            # canonical 행이 동일 (user_id, character_id)에 이미 있는지 체크
            cursor.execute(
                "SELECT value, source, updated_at FROM user_profile "
                "WHERE user_id = ? AND character_id = ? AND key = ?",
                (user_id, character_id, canon),
            )
            existing = cursor.fetchone()

            if existing is None:
                # 단순 rename — 기존 alias 행을 canonical로 업데이트
                # (PK 포함 — UPDATE로 key 변경)
                cursor.execute(
                    "UPDATE user_profile SET key = ?, updated_at = updated_at "
                    "WHERE user_id = ? AND character_id = ? AND key = ?",
                    (canon, user_id, character_id, key),
                )
                normalized += 1
            else:
                # 충돌 — updated_at 최신 row를 남기고 나머지 삭제
                existing_value, existing_source, existing_updated = existing
                # None-safe 비교 (NULL은 가장 오래된 것으로 처리)
                alias_ts = updated_at or ""
                canon_ts = existing_updated or ""
                if alias_ts > canon_ts:
                    # alias가 더 최신 — canonical 행을 alias 값으로 덮어쓰고 alias 행 삭제
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
    """saved_characters를 nested JSON 스키마로 재생성 — 구식 v1/v2 schema 감지 시 DROP & CREATE.

    DEV 브랜치 전용 — prod 데이터 없으므로 무손실 마이그레이션 불필요. images/char*.json과
    동일한 14 sub-attribute 구조로 통일.

    감지 기준: body_shape_json 컬럼 부재 = 구식 schema → DROP. 신규 schema는 init_db의
    CREATE TABLE이 처리한다 (idempotent: 두 번째 호출은 no-op).
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
        log.warning("saved_characters: 구식 schema 감지 — v3 nested JSON 스키마로 DROP & CREATE.")
        cursor.execute("DROP TABLE saved_characters")
        conn.commit()
    finally:
        conn.close()


# ── 쿠폰 ──


def create_coupon(code: str, tier: str, days: int, max_uses: int = 0, expires_at: str | None = None) -> None:
    """쿠폰을 생성한다. max_uses=0이면 무제한."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO coupons (code, tier, days, max_uses, expires_at) VALUES (?, ?, ?, ?, ?)",
            (code, tier, days, max_uses, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_coupon(code: str) -> dict | None:
    """쿠폰 정보를 반환한다. 없으면 None."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT code, tier, days, max_uses, used_count, created_at, expires_at FROM coupons WHERE code = ?",
            (code,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "code": row[0], "tier": row[1], "days": row[2],
                "max_uses": row[3], "used_count": row[4],
                "created_at": row[5], "expires_at": row[6],
            }
        return None
    finally:
        conn.close()


def list_coupons() -> list[dict]:
    """전체 쿠폰 목록을 반환한다."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT code, tier, days, max_uses, used_count, created_at, expires_at FROM coupons ORDER BY created_at DESC"
        )
        return [
            {
                "code": row[0], "tier": row[1], "days": row[2],
                "max_uses": row[3], "used_count": row[4],
                "created_at": row[5], "expires_at": row[6],
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def delete_coupon(code: str) -> bool:
    """쿠폰을 삭제한다. 삭제 성공 시 True."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM coupons WHERE code = ?", (code,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def redeem_coupon(code: str, user_id: int) -> tuple[bool, str]:
    """쿠폰을 사용한다. 원자적 검증 + 사용.

    Returns:
        (True, "premium 5일 부여") 또는 (False, "에러 메시지")
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # 쿠폰 존재 확인
        cursor.execute(
            "SELECT tier, days, max_uses, used_count, expires_at FROM coupons WHERE code = ?",
            (code,),
        )
        row = cursor.fetchone()
        if not row:
            return False, "유효하지 않은 쿠폰 코드입니다."

        tier, days, max_uses, used_count, expires_at = row

        # 만료 확인
        if expires_at:
            cursor.execute("SELECT datetime('now') > ?", (expires_at,))
            if cursor.fetchone()[0]:
                return False, "만료된 쿠폰입니다."

        # 사용 횟수 확인
        if max_uses > 0 and used_count >= max_uses:
            return False, "쿠폰 사용 횟수가 초과되었습니다."

        # 1인 1회 확인
        cursor.execute(
            "SELECT 1 FROM coupon_redemptions WHERE code = ? AND telegram_id = ?",
            (code, user_id),
        )
        if cursor.fetchone():
            return False, "이미 사용한 쿠폰입니다."

        # 사용 처리
        cursor.execute(
            "UPDATE coupons SET used_count = used_count + 1 WHERE code = ?",
            (code,),
        )
        cursor.execute(
            "INSERT INTO coupon_redemptions (code, telegram_id) VALUES (?, ?)",
            (code, user_id),
        )
        conn.commit()

        # 티어 부여 (별도 커넥션 사용하는 set_user_tier 호출)
        conn.close()
        set_user_tier(user_id, tier, days)

        return True, f"{tier.capitalize()} {days}일이 부여되었습니다."
    except Exception:
        conn.close()
        raise


# ── 캐릭터 수치 (메모리 캐시 + 지연 DB 쓰기) ──

# 메모리 캐시: {(user_id, char_id): {"fixation": int, "mood": str, "location": str, "_dirty": bool, "_last_activity": float}}
_stats_cache: dict[tuple[int, str], dict] = {}
# 플러시 타이머: {(user_id, char_id): asyncio.Task}
_flush_timers: dict[tuple[int, str], object] = {}
# 플러시 지연 시간 (초)
STATS_FLUSH_DELAY = 300  # 5분


def get_character_stats(user_id: int, character_id: str) -> dict:
    """캐릭터 수치 조회. 메모리 캐시 우선, 없으면 DB → 캐시 로드."""
    import time as _time
    key = (user_id, character_id)

    # 캐시 히트
    if key in _stats_cache:
        cached = _stats_cache[key]
        result = {k: v for k, v in cached.items() if not k.startswith("_")}
        result["total_turns"] = cached.get("_total_turns", 0)
        result["mood_lock"] = cached.get("_mood_lock")
        return result

    # DB에서 로드
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

        # 없으면 캐릭터별 초기값으로 생성
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
    """수치 업데이트. 캐시에만 반영 (DB 쓰기 지연).

    - fixation_delta: 메시지당 최대 clamp (캐릭터별 stat_limits 또는 글로벌 STAT_LIMITS)
    - mood/location이 빈 문자열이면 이전 값 유지
    - 5분 후 또는 요약 트리거 시 DB에 flush
    - stat_limits: 캐릭터별 한도 dict (없으면 글로벌 STAT_LIMITS 사용)
    """
    # 현재 값 조회 (캐시 또는 DB)
    current = get_character_stats(user_id, character_id)
    key = (user_id, character_id)

    # delta clamp (메시지당 변화량 제한) — 캐릭터별 한도 우선
    limits = stat_limits if stat_limits else STAT_LIMITS
    fix_up = limits.get("fixation", STAT_LIMITS["fixation"])["up"]
    fix_down = limits.get("fixation", STAT_LIMITS["fixation"])["down"]

    fixation_delta = max(fix_down, min(fix_up, fixation_delta))

    new_fixation = current["fixation"] + fixation_delta

    # 범위 clamp (0~100)
    new_fixation = max(STAT_RANGE["min"], min(STAT_RANGE["max"], new_fixation))

    # mood/location: 빈 문자열이면 이전 값 유지
    new_mood = mood if mood else current["mood"]
    # location은 항상 정규화 형태로 저장 (DB 중복 방지)
    new_location = _normalize_location_key(location) if location else current.get("location", "")

    # mood_lock 강제 — 잠긴 mood는 LLM이 변경 불가
    prev = _stats_cache.get(key, {})
    if prev.get("_mood_lock"):
        new_mood = prev["_mood_lock"]["mood"]

    # 캐시에만 반영 (DB 쓰기 지연) — mood_lock 보존
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

    # 5분 후 자동 flush 타이머 설정
    _schedule_flush(user_id, character_id)


def increment_total_turns(user_id: int, character_id: str) -> int:
    """캐릭터별 누적 턴 수를 +1 하고 현재 값을 반환한다."""
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
    """캐시된 수치를 DB에 즉시 기록. 요약 트리거 시 또는 타이머 만료 시 호출."""
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
    """모든 dirty 캐시를 DB에 기록. 봇 종료 시 호출."""
    for (uid, cid), cached in _stats_cache.items():
        if cached.get("_dirty"):
            flush_character_stats(uid, cid)


def _schedule_flush(user_id: int, character_id: str) -> None:
    """5분 후 자동 flush 타이머 설정. 기존 타이머 있으면 리셋."""
    import asyncio
    key = (user_id, character_id)

    # 기존 타이머 취소
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
        # 이벤트 루프 없으면 즉시 flush
        flush_character_stats(user_id, character_id)


# ── 데이터 삭제 ──


def delete_all_user_data(user_id: int) -> dict:
    """유저의 모든 데이터를 삭제한다. (GDPR /deletedata)

    payments, coupon_redemptions는 보존 (법적 보관 + 중복 방지).

    Returns:
        삭제된 행 수 딕셔너리
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

        # user_settings는 행 삭제 (온보딩 상태도 초기화)
        cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        deleted["user_settings"] = cursor.rowcount

        conn.commit()
        return deleted
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Saved Characters (이미지 제네레이터 캐릭터 저장, Feature 1)
# ═══════════════════════════════════════════════════════════════════════

import re as _re_saved

_SAVED_CHAR_NAME_RE = _re_saved.compile(r"^[a-zA-Z0-9_]{1,20}$")
SAVED_CHAR_MAX_SLOTS = 3


def is_valid_saved_char_name(name: str) -> bool:
    """캐릭터 이름 유효성 검사 — 영문/숫자/언더스코어 1-20자."""
    return bool(name) and bool(_SAVED_CHAR_NAME_RE.match(name))


def _deserialize_nested(raw: str | None, default_keys: tuple[str, ...]) -> dict:
    """JSON 문자열을 dict로 역직렬화. 파싱 실패/비어있으면 default_keys로 빈 dict 반환."""
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
    """캐릭터 저장/덮어쓰기 (upsert by user_id + slot).

    nested 스키마 (P15-3 v3, images/char*.json와 동일):
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
    """saved_characters 행을 nested dict로 변환."""
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
    """유저의 저장된 캐릭터 목록 (slot 오름차순)."""
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
    """이름으로 저장된 캐릭터 조회 (대소문자 구분)."""
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
    """슬롯으로 저장된 캐릭터 조회."""
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
    """슬롯의 캐릭터 삭제. 삭제 성공 시 True."""
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
    """빈 슬롯 찾기 (1-3). 다 차있으면 None."""
    existing = {c["slot"] for c in list_saved_characters(user_id)}
    for s in range(1, SAVED_CHAR_MAX_SLOTS + 1):
        if s not in existing:
            return s
    return None
