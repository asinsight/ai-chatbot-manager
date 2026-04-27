"""handlers_common.py — 메인봇/캐릭터봇 핸들러 공통 유틸리티."""

import logging
import os

from src.history import (
    save_message, get_history, get_active_character, set_active_character,
    clear_history, get_message_count, get_latest_summary, save_summary,
    delete_old_messages, get_full_profile, set_profile, get_memories,
    save_memory, delete_oldest_events, _get_connection,
    get_usage, get_daily_image_count, get_daily_video_count,
)
from src.summary import summarize_messages, extract_memory_and_profile
from src.input_filter import strip_signals
from src.profile_keys import canonicalize as _canon_key


def check_admin(user_id: int) -> bool:
    """유저가 Admin인지 확인한다 (.env 기반)."""
    admin_ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    return str(user_id) in [x.strip() for x in admin_ids]


def get_admin_ids() -> list[int]:
    """설정된 Admin 유저 ID 리스트."""
    raw = os.getenv("ADMIN_USER_IDS", "")
    ids = []
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids


async def notify_admins_video(
    context,
    *,
    triggering_user_id: int,
    source: str,        # "char_bot" or "imagegen"
    char_id: str = "",  # char01~10 or "imagegen"
    status: str,        # "started" / "success" / "failed" / "blocked"
    pose_key: str = "",
    safety_level: str = "",
    motion_prompt: str = "",
    audio_prompt: str = "",
    extra: str = "",
) -> None:
    """영상 생성 이벤트를 모든 Admin에게 알린다.

    **VIDEO_DEBUG_DUMP=1 env 가드** — 디버깅 모드일 때만 전송 (평소엔 메시지 스팸 방지).
    실패는 silently swallow.
    """
    if os.getenv("VIDEO_DEBUG_DUMP", "0") != "1":
        return
    admin_ids = get_admin_ids()
    if not admin_ids:
        return

    icon_map = {"started": "🎬", "success": "✅", "failed": "❌", "blocked": "🚫"}
    icon = icon_map.get(status, "📹")
    lines = [
        f"{icon} Video {status} — {source}",
        f"User: `{triggering_user_id}`",
    ]
    if char_id:
        lines.append(f"Char: `{char_id}`")
    if pose_key:
        lines.append(f"Pose: `{pose_key}` | Safety: `{safety_level or 'N/A'}`")
    if motion_prompt:
        mp = motion_prompt[:400] + ("…" if len(motion_prompt) > 400 else "")
        lines.append(f"Motion: {mp}")
    if audio_prompt:
        ap = audio_prompt[:200] + ("…" if len(audio_prompt) > 200 else "")
        lines.append(f"Audio: {ap}")
    if extra:
        lines.append(extra)
    msg = "\n".join(lines)

    for aid in admin_ids:
        try:
            await context.bot.send_message(chat_id=aid, text=msg, parse_mode="Markdown")
        except Exception:
            try:
                # Markdown 파싱 실패 시 plain text로 재시도
                await context.bot.send_message(chat_id=aid, text=msg[:4000])
            except Exception as _e:
                logger.warning("admin video notify 실패: admin=%s err=%s", aid, _e)

logger = logging.getLogger(__name__)

# 티어별 이미지 한도 상수
FREE_MAX_IMAGES = int(os.getenv("FREE_MAX_IMAGES", "2"))  # 0 = 완전 차단, 1+ = 월 N장 허용
STANDARD_MAX_IMAGES = int(os.getenv("STANDARD_MAX_IMAGES", "30"))
PREMIUM_MAX_IMAGES = int(os.getenv("PREMIUM_MAX_IMAGES", "60"))
STANDARD_DAILY_IMAGES = int(os.getenv("STANDARD_DAILY_IMAGES", "5"))
PREMIUM_DAILY_IMAGES = int(os.getenv("PREMIUM_DAILY_IMAGES", "10"))

# 티어별 비디오 한도 상수
FREE_MAX_VIDEOS = int(os.getenv("FREE_MAX_VIDEOS", "0"))
STANDARD_MAX_VIDEOS = int(os.getenv("STANDARD_MAX_VIDEOS", "0"))
PREMIUM_MAX_VIDEOS = int(os.getenv("PREMIUM_MAX_VIDEOS", "10"))
STANDARD_DAILY_VIDEOS = int(os.getenv("STANDARD_DAILY_VIDEOS", "0"))
PREMIUM_DAILY_VIDEOS = int(os.getenv("PREMIUM_DAILY_VIDEOS", "5"))


def check_image_limit(user_id: int, tier: str) -> str | None:
    """이미지 한도 체크. 초과 시 안내 메시지 반환, 통과 시 None.

    Admin 유저는 항상 None (바이패스).
    """
    if check_admin(user_id):
        return None

    if tier == "free":
        if FREE_MAX_IMAGES <= 0:
            return "_(무료 이미지 기능이 비활성화되어 있습니다.)_"
        usage = get_usage(user_id)
        if usage["images"] >= FREE_MAX_IMAGES:
            return f"_(무료 이미지 한도({FREE_MAX_IMAGES}장)에 도달했습니다. 더 많은 이미지를 원하시면 구독해주세요!)_"
    elif tier in ("standard", "premium"):
        # 일일 한도 체크
        daily_limit = STANDARD_DAILY_IMAGES if tier == "standard" else PREMIUM_DAILY_IMAGES
        daily_count = get_daily_image_count(user_id)
        if daily_limit > 0 and daily_count >= daily_limit:
            return f"_(오늘 이미지 한도({daily_limit}장)에 도달했습니다. 내일 다시 이용해주세요!)_"
        # 월별 한도 체크
        monthly_limit = STANDARD_MAX_IMAGES if tier == "standard" else PREMIUM_MAX_IMAGES
        if monthly_limit > 0:
            usage = get_usage(user_id)
            if usage["images"] >= monthly_limit:
                return f"_(이번 달 이미지 한도({monthly_limit}장)에 도달했습니다. 구독을 업그레이드하거나 다음 달에 이용해주세요!)_"
    return None


def check_video_limit(user_id: int, tier: str) -> str | None:
    """비디오 한도 체크. None이면 OK, 문자열이면 차단 메시지."""
    if check_admin(user_id):
        return None

    usage = get_usage(user_id)
    monthly_videos = usage.get("videos", 0)

    if tier == "free":
        if FREE_MAX_VIDEOS <= 0 or monthly_videos >= FREE_MAX_VIDEOS:
            return "🎬 영상 생성은 Premium 전용 기능이에요!\n/subscribe 로 구독해보세요 ✨"
    elif tier == "standard":
        if STANDARD_MAX_VIDEOS <= 0 or monthly_videos >= STANDARD_MAX_VIDEOS:
            return "🎬 영상 생성은 Premium 전용 기능이에요!\n/subscribe 로 업그레이드해보세요 ✨"
    elif tier == "premium":
        if monthly_videos >= PREMIUM_MAX_VIDEOS:
            return f"🎬 이번 달 영상 한도({PREMIUM_MAX_VIDEOS}개)를 다 사용했어요. 다음 달에 다시 만나요!"
        daily = get_daily_video_count(user_id)
        if daily >= PREMIUM_DAILY_VIDEOS:
            return f"🎬 오늘 영상 한도({PREMIUM_DAILY_VIDEOS}개)를 다 사용했어요. 내일 다시 만나요!"

    return None


def _get_character(context, user_id):
    """유저의 활성 캐릭터를 반환한다."""
    # 멀티봇: 캐릭터 봇이면 bot_data에 char_id가 고정
    if "char_id" in context.bot_data and "character" in context.bot_data:
        return context.bot_data["char_id"], context.bot_data["character"]
    # 레거시/메인봇: DB에서 조회
    characters = context.bot_data.get("characters", {})
    char_id = get_active_character(user_id)
    if char_id in characters:
        return char_id, characters[char_id]
    # fallback: 첫 번째 캐릭터
    first_id = next(iter(characters), None)
    if first_id:
        return first_id, characters[first_id]
    return "default", context.bot_data.get("character", {})


async def _run_summary(user_id: int, char_id: str, recent_keep: int) -> None:
    """비동기 요약 + 장기 기억/프로필 추출."""
    try:
        all_messages = get_history(user_id, limit=9999, character_id=char_id)
        if len(all_messages) <= recent_keep:
            return

        # 요약 대상: 최근 keep 제외한 나머지
        to_summarize = all_messages[:-recent_keep]
        existing_summary = get_latest_summary(user_id, char_id)

        # 기존 요약이 있으면 앞에 붙여서 연속성 유지 (최대 500자 — 누적 방지)
        max_prev_summary = int(os.getenv("SUMMARY_MAX_PREV_CHARS", "500"))
        if existing_summary:
            truncated = existing_summary[:max_prev_summary]
            to_summarize.insert(0, {"role": "system", "content": f"Previous summary: {truncated}"})

        # 1. 요약 생성
        summary = await summarize_messages(to_summarize)
        if summary and summary != "(summary unavailable)":
            save_summary(user_id, char_id, summary, len(to_summarize))
            deleted = delete_old_messages(user_id, char_id, keep_recent=recent_keep)
            logger.info("유저 %s 캐릭터 %s 요약 완료: %d개 메시지 압축, %d개 삭제", user_id, char_id, len(to_summarize), deleted)
        else:
            logger.warning("유저 %s 캐릭터 %s 요약 실패", user_id, char_id)

        # 1-1. 캐릭터 수치 DB flush (요약 트리거 시 캐시 기록)
        try:
            from src.history import flush_character_stats
            flush_character_stats(user_id, char_id)
        except Exception:
            pass

        # 2. 장기 기억 + 프로필 추출
        extracted = await extract_memory_and_profile(to_summarize, truncated if existing_summary else "")

        # relationship 저장 (덮어쓰기) — sanitize
        if extracted.get("relationship"):
            save_memory(user_id, char_id, "relationship", strip_signals(extracted["relationship"]))
            logger.info("유저 %s 캐릭터 %s relationship 업데이트", user_id, char_id)

        # events 저장 (추가)
        for event in extracted.get("events", []):
            if event.strip():
                save_memory(user_id, char_id, "event", strip_signals(event.strip()))
        delete_oldest_events(user_id, char_id, keep=10)

        # user_info → 프로필 저장 (manual이 아닌 항목만) — canonical key로 정규화
        for key, value in extracted.get("user_info", {}).items():
            if not value or not value.strip():
                continue
            canon = _canon_key(key)
            existing = get_full_profile(user_id, char_id)
            if canon in existing and existing[canon].get("source") == "manual":
                continue
            set_profile(user_id, "global", canon, strip_signals(value.strip()), source="auto")
            logger.info("유저 %s 프로필 자동 추출: %s=%s (LLM key='%s')", user_id, canon, value.strip(), key)

    except Exception as e:
        logger.error("요약/추출 실행 중 오류: %s", e)
