"""Character bot handlers — 멀티봇 아키텍처에서 각 캐릭터 봇에 등록되는 핸들러.

각 봇의 bot_data에 char_id와 character가 설정되어 있다고 가정한다.
"""

import asyncio
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from src.handlers_common import _get_character, _run_summary, check_admin, check_image_limit, check_video_limit, notify_admins_video
from src.history import (
    save_message, get_history, get_message_count,
    get_full_profile, get_memories, get_latest_summary, clear_history,
    is_onboarded, get_user_tier, get_usage, increment_usage,
    get_outfit, set_outfit, reset_outfit,
    increment_daily_images, increment_daily_videos,
    get_daily_turn_count, increment_daily_turns,
    get_character_stats, update_character_stats,
    increment_total_turns, _stats_cache, _schedule_flush,
    _normalize_location_key,
)
from src.llm_queue import llm_queue, QueueFullError, QueueTimeoutError
from src.prompt import build_messages, replace_macros, SEARCH_EXCLUDED_CHARS
from src.grok import generate_danbooru_tags, _load_image_config
from src.comfyui import generate_image, check_queue
from src.watchdog import notify_image_timeout
from src.rate_limiter import rate_limiter
from src.input_filter import filter_input, is_non_character_image_request
from src.video_context import (
    store_video_context as _store_video_context,
    get_video_context as _get_video_context,
    cleanup_video_context as _cleanup_video_context,
)

logger = logging.getLogger(__name__)

MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "")

# 티어 제한 설정 (env로 조정 가능)
FREE_CHAR_IDS = [c.strip() for c in os.getenv("FREE_CHAR_IDS", "char06").split(",")]
FREE_MAX_TURNS = int(os.getenv("FREE_MAX_TURNS", "30"))

# P10 Phase 2 — Location research in-flight dedup (두 번 빠르게 요청되지 않도록)
_location_research_inflight: set[str] = set()


async def _research_location_bg(location_key: str) -> None:
    """백그라운드 로케이션 리서치 — 캐시 미스 시 Grok 검색 후 DB 저장.

    fire-and-forget 용도. 실패해도 메인 대화 플로우에 영향 없음.
    중복 인플라이트 방지를 위한 in-memory 가드 포함.
    """
    from src.history import get_location_context
    from src.grok_search import search_location

    key = _normalize_location_key(location_key or "")
    if not key:
        return

    # 이미 캐시에 있으면 즉시 종료 — 불필요한 API 호출 방지
    if get_location_context(key):
        return

    # 동시 요청 방지
    if key in _location_research_inflight:
        return
    _location_research_inflight.add(key)

    try:
        result = await search_location(key)
        if result:
            logger.info("Location research queued success: %s", key)
        else:
            logger.info("Location research queued no-result: %s", key)
    except Exception as e:
        logger.error("Location research background task failed (%s): %s", key, e)
    finally:
        _location_research_inflight.discard(key)


def _parse_outfit_signal(text: str) -> str | None:
    """LLM 응답에서 [OUTFIT: ...] 시그널을 추출한다. 없으면 None.

    SFW invariant (config/grok_prompts.json): clothing is always full and
    intact — the LLM should never emit a state-style outfit (e.g. partial
    undress). If one slips through, it flows into the standard Grok tag
    converter and gets persisted as a normal full-set; no NSFW state
    machinery exists to interpret it specially.
    """
    match = re.search(r"\[OUTFIT:\s*(.+?)\]", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _split_tags(text: str) -> list[str]:
    """콤마 구분 태그를 trim 된 리스트로 분리한다."""
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]


async def _convert_outfit_tags(description: str) -> dict | None:
    """자연어 의상 설명을 danbooru 태그로 변환한다. Grok 경량 호출."""
    from openai import AsyncOpenAI

    api_key = os.getenv("GROK_API_KEY", "")
    if not api_key:
        return None

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    model = os.getenv("GROK_MODEL_NAME", "grok-3-mini")

    prompt = (
        "Convert this clothing description to accurate Danbooru tags.\n"
        "Use only well-known Danbooru clothing/underwear tags.\n\n"
        f"Description: {description}\n\n"
        'Respond with JSON only: {"clothing": "tag1, tag2", "underwear": "tag1, tag2"}\n'
        'If underwear is not mentioned, set underwear to empty string.'
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            return None
        import json as _json
        data = _json.loads(json_match.group(0))
        return data if data.get("clothing") else None
    except Exception as e:
        logger.error("의상 태그 변환 실패: %s", e)
        return None


async def char_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 커맨드 핸들러 — 온보딩 체크 + 캐릭터 봇의 first_mes를 전송한다."""
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    user_name = update.effective_user.first_name or "User"
    user_id = update.effective_user.id

    # 온보딩 체크 — 미완료 시 메인 봇으로 안내
    if not is_onboarded(user_id):
        link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = (
            "서비스 이용을 위해 먼저 메인 봇에서 연령 확인 + 이용약관에 동의해 주세요.\n"
            "Please agree to age verification + terms of service in the main bot first."
        )
        if link:
            text += f"\n\n👉 {link}"
        await update.message.reply_text(text)
        return

    # 티어별 캐릭터 접근 제한
    tier = get_user_tier(user_id)
    if tier == "free" and char_id not in FREE_CHAR_IDS:
        main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = (
            "이 캐릭터는 프리미엄 구독이 필요합니다.\n"
            "This character requires a premium subscription."
        )
        if main_link:
            text += f"\n\n👉 {main_link}"
        await update.message.reply_text(text)
        return

    # first_mes 전송
    first_mes = character.get("first_mes", "")
    if first_mes:
        first_mes = replace_macros(first_mes, character["name"], user_name)

    # 프로필 사진 전송 (앵커 이미지)
    anchor_image = character.get("anchor_image", "")
    if anchor_image:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        image_path = os.path.join(base_dir, "images", "profile", anchor_image)
        if os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(photo=photo)

    greeting = first_mes or "안녕! 무엇이든 물어봐 :)"
    await update.message.reply_text(greeting)

    # first_mes를 히스토리에 저장 (다음 대화에서 맥락 유지)
    if first_mes:
        save_message(user_id, "assistant", first_mes, character_id=char_id)
        logger.info("유저 %s에게 first_mes 전송 및 히스토리 저장 (char=%s)", user_id, char_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텍스트 메시지 핸들러 — 히스토리 + 캐릭터 카드로 프롬프트를 조립하여 LLM 응답을 반환한다."""
    user_text = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "User"

    # Rate limit 체크
    allowed, reason = rate_limiter.check(user_id)
    if not allowed:
        if reason == "rate_limit":
            await update.message.reply_text("잠시만... 기다려봐. 너 말이 너무 빨라.")
        elif reason == "spam_blocked":
            await update.message.reply_text("잠시 후에 다시 말하자.")
        return

    # 프롬프트 인젝션 필터
    user_text, blocked, block_reason = await filter_input(user_text)
    if blocked:
        logger.warning("[security] 인젝션 차단: user=%s reason=%s text=%s", user_id, block_reason, update.message.text[:100])
        await update.message.reply_text("무슨 말이야? 잘 모르겠어~")
        return

    # 온보딩 체크
    if not is_onboarded(user_id):
        await update.message.reply_text("서비스 이용을 위해 /start를 눌러 연령 확인 + 이용약관에 동의해 주세요.")
        return

    char_id, character = _get_character(context, user_id)

    # 티어별 캐릭터 접근 제한
    tier = get_user_tier(user_id)
    if tier == "free" and char_id not in FREE_CHAR_IDS:
        await update.message.reply_text("이 캐릭터는 프리미엄 구독이 필요합니다.\nThis character requires a premium subscription.")
        return

    # Free 턴 제한 (일일 — 자정 리셋)
    if tier == "free":
        daily_turns = get_daily_turn_count(user_id)
        if daily_turns >= FREE_MAX_TURNS:
            main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
            text = (
                f"오늘 무료 대화 {FREE_MAX_TURNS}턴을 모두 사용했어요.\n"
                "내일 자정에 리셋되며, 프리미엄으로 업그레이드하면 무제한 대화가 가능합니다!\n\n"
                f"You've used all {FREE_MAX_TURNS} free turns for today.\n"
                "Resets at midnight. Upgrade to premium for unlimited conversations!"
            )
            if main_link:
                text += f"\n\n👉 {main_link}"
            await update.message.reply_text(text)
            return

    system_config = context.bot_data.get("system_config")

    # 캐릭터 수치 1회 조회 (이후 재사용) + 턴 카운트 즉시 증가
    _cached_stats = get_character_stats(user_id, char_id)
    turn_num = increment_total_turns(user_id, char_id)
    _cached_stats = get_character_stats(user_id, char_id)

    # 히스토리 + 프로필 + 기억 + 요약 조회 → 프롬프트 조립
    # chat_history는 RECENT_MESSAGES_KEEP 만큼만 LLM에 노출 (피크 토큰 제어)
    # 초과분은 다음 요약 주기에서 summary로 흡수됨
    history_limit = int(os.getenv("RECENT_MESSAGES_KEEP", "5"))
    chat_history = get_history(user_id, character_id=char_id, limit=history_limit)
    summary = get_latest_summary(user_id, char_id)
    profile = get_full_profile(user_id, char_id)
    memories = get_memories(user_id, char_id)
    messages = build_messages(
        character, chat_history, user_text, user_name, system_config,
        profile=profile, memories=memories, summary=summary,
        user_id=user_id, char_id=char_id,
        turn_count=get_message_count(user_id, char_id),
    )

    async def keep_typing():
        """LLM 응답 대기 중 3초마다 typing indicator를 전송한다."""
        while True:
            await update.message.chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(3)

    typing_task = asyncio.create_task(keep_typing())
    try:
        char_max_tokens = character.get("max_tokens", 250)
        reply = await llm_queue.enqueue(messages, user_id=user_id, task_type="chat", max_tokens=char_max_tokens)
    except QueueFullError:
        typing_task.cancel()
        await update.message.reply_text("지금 너무 많은 사람이 대화 중이야... 잠시 후에 다시 말해줘!")
        return
    except QueueTimeoutError:
        typing_task.cancel()
        await update.message.reply_text("응답이 너무 오래 걸리고 있어... 다시 시도해줘!")
        return
    finally:
        typing_task.cancel()

    # ── Grok Search two-pass ──
    search_match = re.search(r"\[SEARCH:\s*(.+?)\]", reply)
    if search_match and char_id not in SEARCH_EXCLUDED_CHARS:
        search_query = search_match.group(1).strip()
        logger.info("[SEARCH] 시그널 감지 (유저 %s): query='%s'", user_id, search_query)
        # 검색 + 2차 호출 전체에 typing indicator 유지
        typing_task_search = asyncio.create_task(keep_typing())
        try:
            try:
                from src.grok_search import search as grok_search
                search_results = await grok_search(search_query, user_id=user_id)
            except Exception as e:
                logger.warning("Grok Search 호출 실패: %s", e)
                search_results = ""

            if search_results:
                # 검색 결과 포함하여 프롬프트 재조립
                messages_with_search = build_messages(
                    character, chat_history, user_text, user_name,
                    system_config,
                    profile=profile, memories=memories, summary=summary,
                    user_id=user_id, char_id=char_id,
                    turn_count=get_message_count(user_id, char_id),
                    search_results=search_results,
                )
                try:
                    reply = await llm_queue.enqueue(
                        messages_with_search, user_id=user_id,
                        task_type="chat", max_tokens=char_max_tokens,
                    )
                except (QueueFullError, QueueTimeoutError):
                    reply = re.sub(r"\[SEARCH:\s*.+?\]", "", reply).strip()
                    if not reply:
                        reply = "음... 잠깐 찾아보려고 했는데 안 되네."
            else:
                # 검색 실패 — 시그널 제거하고 1차 응답 사용
                reply = re.sub(r"\[SEARCH:\s*.+?\]", "", reply).strip()
        finally:
            typing_task_search.cancel()

    # <think>...</think> 블록 제거 (reasoning 모델의 내부 사고 과정)
    reply = re.sub(r"</?think>", "", reply)
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
    if "<think>" in reply:
        reply = reply.split("<think>")[0]
    # 마크다운 포맷팅 제거 (*bold*, _italic_)
    reply = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", reply)
    reply = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", reply)
    reply = reply.strip()

    # 에러 체크
    if reply.startswith("[오류]"):
        logger.warning("LLM 오류 응답, 히스토리 저장 생략: %s", reply)
        await update.message.reply_text(reply)
        return

    # LLM 응답 디버그 로그
    logger.info("LLM 응답 (유저 %s): %s", user_id, reply)

    # [STAT: ...] 시그널 파싱 — DB 업데이트 (실패해도 메인 플로우 중단 안 함)
    # 형식: [STAT: fixation+3, mood:jealous, location:bedroom]
    try:
        stat_match = re.search(r'\[STAT:\s*(.+?)\]', reply)
        if stat_match:
            stat_str = stat_match.group(1)
            fixation_delta = 0
            stat_mood = ""
            stat_location = ""
            for part in stat_str.split(","):
                part = part.strip()
                if part.startswith("fixation"):
                    fd_match = re.search(r'[+-]\d+', part)
                    if fd_match:
                        fixation_delta = int(fd_match.group())
                elif part.startswith("mood:"):
                    stat_mood = part.split(":")[1].strip()
                elif part.startswith("location:"):
                    stat_location = _normalize_location_key(part.split(":", 1)[1])
            update_character_stats(user_id, char_id, fixation_delta, stat_mood, location=stat_location, stat_limits=character.get("stat_limits"))
            logger.info("캐릭터 수치 업데이트 (유저 %s, %s): fix=%+d, mood=%s, loc=%s",
                        user_id, char_id, fixation_delta, stat_mood or "(unchanged)", stat_location or "(unchanged)")

            # P10 Phase 2 — 새 location 감지 시 비동기 리서치 훅 (non-blocking)
            # 캐시 히트 체크는 _research_location_bg 내부에서 수행
            if stat_location:
                try:
                    asyncio.create_task(_research_location_bg(stat_location))
                except Exception as _e:
                    logger.debug("location research task spawn 실패: %s", _e)
    except Exception as e:
        logger.error("캐릭터 수치 파싱/업데이트 실패 (유저 %s): %s", user_id, e)

    # 이미지 시그널 파싱 — SEND_IMAGE / 사진을 보냈다 / photo sent만 매칭
    # [STAT:], [MOOD:], [OUTFIT:] 등 다른 시그널은 매칭하지 않음
    image_signal_pattern = r"\[(SEND_IMAGE|사진을 보냈다|photo sent):\s*(.+?)\]"
    image_match = re.search(image_signal_pattern, reply, re.IGNORECASE)
    # 2) 대괄호 없이 SEND_IMAGE: ... 형태
    if not image_match:
        bare_pattern = r"(?:SEND_IMAGE|사진을 보냈다|photo sent):\s*(.+?)$"
        image_match = re.search(bare_pattern, reply, re.IGNORECASE | re.MULTILINE)

    # 3) 코드 키워드 강제 트리거 — LLM이 시그널 안 넣어도 유저 요청이면 강제 생성
    force_image = False
    force_mood = None
    if not image_match:
        _IMAGE_KEYWORDS = ["사진", "셀카", "보여", "보내", "찍어", "멀리서", "가까이서", "다른 각도", "전신"]
        for kw in _IMAGE_KEYWORDS:
            if kw in user_text:
                force_image = True
                logger.info("키워드 강제 이미지 트리거: '%s' (유저 %s)", kw, user_id)
                break

    # 4) 캐릭터별 특수 무드 트리거 — mood_triggers 매칭 시 강제 이미지 + 표정 오버라이드
    if not image_match and not force_image:
        img_config = _load_image_config(char_id)
        mood_triggers = img_config.get("mood_triggers", {})
        for mood, keywords in mood_triggers.items():
            for kw in keywords:
                if kw in user_text:
                    force_image = True
                    force_mood = mood
                    logger.info("캐릭터 특수 트리거: mood=%s, keyword='%s' (유저 %s, %s)", mood, kw, user_id, char_id)
                    break
            if force_mood:
                break

    # 5) 수치 mood fallback — 키워드 트리거 없을 때 stat mood 사용
    if not force_mood and char_id:
        try:
            if _cached_stats["mood"] not in ("neutral", ""):
                force_mood = _cached_stats["mood"]
                logger.info("수치 mood fallback: mood=%s (유저 %s, %s)", force_mood, user_id, char_id)
        except Exception as e:
            logger.error("수치 mood fallback 실패: %s", e)

    # 대괄호 [...] + 닫히지 않은 [ + 대괄호 없는 시그널 전부 제거
    clean_reply = re.sub(r"\[[^\[\]]*?\]", "", reply)
    clean_reply = re.sub(r"\[.*$", "", clean_reply, flags=re.DOTALL)
    clean_reply = re.sub(r"(?:SEND_IMAGE|사진을 보냈다|photo sent):\s*.+?$", "", clean_reply, flags=re.IGNORECASE | re.MULTILINE)
    # 히스토리에서 따라쓴 (IMAGE_SENT: ...) 패턴 제거
    clean_reply = re.sub(r"\(IMAGE_SENT:\s*.+?\)", "", clean_reply, flags=re.IGNORECASE)
    # [MOOD:...] 태그 제거
    clean_reply = re.sub(r"\[MOOD:\w+\]", "", clean_reply)
    # [OUTFIT:...] 태그 제거
    clean_reply = re.sub(r"\[OUTFIT:\s*.+?\]", "", clean_reply, flags=re.IGNORECASE)
    # [STAT:...] 태그 제거 (location 포함)
    clean_reply = re.sub(r"\[STAT:\s*[^\]]*\]", "", clean_reply)
    # [LOCATION:...] 태그 제거 (혹시 별도로 나올 경우 대비)
    clean_reply = re.sub(r"\[LOCATION:\s*[^\]]*\]", "", clean_reply, flags=re.IGNORECASE)
    # [SEARCH:...] 태그 제거
    clean_reply = re.sub(r"\[SEARCH:\s*[^\]]*\]", "", clean_reply)
    clean_reply = clean_reply.strip()

    # 📷촬영 버튼 — fixation > 50 + 이미지 전송이 없을 때만 표시
    capture_keyboard = None
    if not image_match and not force_image:
        try:
            if _cached_stats["fixation"] > 50:
                capture_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📷촬영", callback_data="capture_scene")]
                ])
        except Exception:
            pass

    if clean_reply:
        # 행동(괄호)은 그대로, 대사는 bold 처리 (HTML)
        def _format_dialogue_bold(text: str) -> str:
            """괄호 밖 대사를 <b>로 감싸고, 괄호 안 행동묘사는 그대로 둔다."""
            parts = re.split(r'(\([^)]*\))', text)
            result = []
            for part in parts:
                if part.startswith('(') and part.endswith(')'):
                    result.append(part)
                else:
                    stripped = part.strip()
                    if stripped:
                        result.append(f"<b>{stripped}</b>")
                    elif part:
                        result.append(part)
            return ' '.join(result)

        formatted_reply = _format_dialogue_bold(clean_reply)
        try:
            await update.message.reply_text(formatted_reply, parse_mode="HTML", reply_markup=capture_keyboard)
        except Exception:
            # HTML 파싱 실패 시 plain text fallback
            await update.message.reply_text(clean_reply, reply_markup=capture_keyboard)

    # 히스토리 저장 (stage direction 포함된 전체 텍스트로 — 분리는 표시용일 뿐)
    save_message(user_id, "user", user_text, character_id=char_id)
    save_message(user_id, "assistant", clean_reply if clean_reply else reply, character_id=char_id)
    # 턴 카운트 (유저 메시지 1회 = 1턴) — total_turns는 이미 수신 시 증가
    increment_usage(user_id, "turns")  # 월간 통계 (Admin /stats)
    increment_daily_turns(user_id)  # 일일 카운터 (Free 티어 게이팅)

    # 의상 변경 감지 — LLM의 [OUTFIT: ...] 시그널 파싱
    # 이미지 생성 전에 처리해야 현재 이미지에도 반영됨
    # full outfit change만 허용 (full-set 의상 이름) → Grok 태그 변환
    outfit_raw = _parse_outfit_signal(reply)
    current_outfit_override = None
    if outfit_raw:
        # Sanity check — LLM이 캐릭터 default에 없는 태그를 발명했는지 로깅
        try:
            _default_clothing = _load_image_config(char_id).get("clothing", "").lower()
            _default_underwear = _load_image_config(char_id).get("underwear", "").lower()
            _emitted = [t.lower() for t in _split_tags(outfit_raw)]
            _novel = [t for t in _emitted if t not in _default_clothing and t not in _default_underwear]
            if _novel:
                logger.warning(
                    "의상 full-change novel tags (유저 %s, %s): %s — not in default wardrobe",
                    user_id, char_id, _novel,
                )
        except Exception:
            pass

        converted = await _convert_outfit_tags(outfit_raw)
        if converted:
            set_outfit(user_id, char_id, converted["clothing"], converted.get("underwear", ""), source="custom")
            current_outfit_override = converted
            logger.info("의상 변경 저장 (유저 %s, %s): %s", user_id, char_id, converted["clothing"])
        else:
            # Grok 변환 실패 시 원본 그대로 저장
            set_outfit(user_id, char_id, outfit_raw, "", source="custom")
            current_outfit_override = {"clothing": outfit_raw, "underwear": ""}
            logger.info("의상 변경 저장 (원본, 유저 %s, %s): %s", user_id, char_id, outfit_raw)

    # 티어별 이미지 제한 (Admin은 바이패스)
    if image_match or force_image:
        limit_msg = check_image_limit(user_id, tier)
        if limit_msg:
            # 한도 초과 시 이미지 스킵 (대화 응답은 계속 진행)
            logger.info("이미지 한도 초과 — 스킵: user=%s, tier=%s", user_id, tier)
            await update.message.reply_text(limit_msg, parse_mode="Markdown")
            image_match = None
            force_image = False

    # 캐릭터 외 이미지 요청 차단
    if (image_match or force_image) and is_non_character_image_request(user_text):
        logger.info("캐릭터 외 이미지 요청 차단 (유저 %s): %s", user_id, user_text[:80])
        image_match = None
        force_image = False

    # 이미지 시그널 또는 키워드 강제 트리거
    if image_match or force_image:
        # 수치 기반 거리두기 — fixation < 20이면 이미지 생성 스킵
        try:
            _img_stats = _cached_stats
            if _img_stats["fixation"] < 20:
                logger.info("거리두기 상태 — 이미지 생성 스킵 (fixation=%d, 유저 %s, %s)",
                            _img_stats["fixation"], user_id, char_id)
                image_match = None
                force_image = False
        except Exception as e:
            logger.error("이미지 수치 체크 실패: %s", e)

    if image_match or force_image:
        # 큐 체크를 먼저 — Grok API 호출 전에 거절
        queue_status = await check_queue()
        from src.comfyui import COMFYUI_MAX_QUEUE
        total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
        if total_queued >= COMFYUI_MAX_QUEUE:
            await update.message.reply_text("(이미지 요청이 많아서 지금은 생성할 수 없어... 잠시 후 다시 시도해줘!)")
        else:
            image_description = image_match.group(2) if image_match else user_text
            # 특수 무드가 있으면 이미지 설명에 무드 표정 힌트 추가
            if force_mood:
                image_description = f"{image_description} [mood:{force_mood}]"

            anchor_image = character.get("anchor_image", "")

            # 이미지 생성 중 typing
            async def keep_uploading():
                while True:
                    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                    await asyncio.sleep(3)

            upload_task = asyncio.create_task(keep_uploading())
            try:
                recent_history = get_history(user_id, limit=6, character_id=char_id)
                # 현재 장소 정보 추가 (대화 컨텍스트는 chat_history로 직접 전달되므로 중복 제거)
                _cur_location = _cached_stats.get("location", "")
                loc_hint = f" Current location: {_cur_location}." if _cur_location else ""
                combined_desc = f"{loc_hint} Image instruction: {image_description}"
                outfit = current_outfit_override or get_outfit(user_id, char_id)
                # P10 Phase 2 — location_context 배경 태그 주입 (캐시 히트 시만)
                _loc_bg = ""
                if _cur_location:
                    try:
                        from src.history import get_location_context as _glc
                        _loc_ctx = _glc(_normalize_location_key(_cur_location))
                        if _loc_ctx:
                            _loc_bg = _loc_ctx.get("danbooru_background", "") or ""
                    except Exception:
                        _loc_bg = ""
                tags = await generate_danbooru_tags(
                    recent_history, combined_desc, character=character, char_id=char_id,
                    outfit_override=outfit,
                    location_background=_loc_bg,
                )
                logger.info("Grok 태그 (유저 %s): pos=%s | neg=%s | orient=%s | skip_face=%s",
                            user_id, tags["pos_prompt"], tags["neg_prompt"],
                            tags.get("orientation"), tags.get("skip_face"))
                orientation = tags.get("orientation", "portrait")
                skip_face = tags.get("skip_face", False)
                image_path = await generate_image(
                    tags["pos_prompt"], tags["neg_prompt"], anchor_image, orientation, skip_face,
                )

                if image_path == "TIMEOUT":
                    await update.message.reply_text("(이미지 생성이 너무 오래 걸리고 있어... 나중에 다시 시도해줘!)")
                    # Admin에게 상세 알림
                    username = update.effective_user.username or update.effective_user.first_name or "unknown"
                    char_name = character.get("name", char_id)
                    try:
                        await notify_image_timeout(context.bot, user_id, username, char_id, char_name)
                    except Exception as e:
                        logger.error("이미지 타임아웃 Admin 알림 실패: %s", e)
                elif image_path:
                    # Premium 유저: 🎬 영상 생성 버튼 표시 (이미지 파일은 비디오 컨텍스트에서 관리)
                    tier = get_user_tier(user_id)
                    if tier == "premium" or check_admin(user_id):
                        video_ctx_id = _store_video_context(
                            user_id, char_id, image_path, image_description,
                            danbooru_tags=tags["pos_prompt"],
                        )
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{video_ctx_id}")
                        ]])
                        with open(image_path, "rb") as photo_file:
                            await update.message.reply_photo(photo=photo_file, reply_markup=keyboard)
                        # 이미지 파일은 비디오 컨텍스트에서 관리 (TTL 후 자동 삭제)
                    else:
                        with open(image_path, "rb") as photo_file:
                            await update.message.reply_photo(photo=photo_file)
                        os.unlink(image_path)
                    save_message(user_id, "assistant", f"(IMAGE_SENT: {image_description})", character_id=char_id)
                    increment_usage(user_id, "images")
                    increment_daily_images(user_id)
                    logger.info("유저 %s 자동 이미지 생성 완료", user_id)
            finally:
                upload_task.cancel()

    # 요약 트리거 — 메시지 수가 임계값 초과 시 비동기 요약 실행
    summary_threshold = int(os.getenv("SUMMARY_THRESHOLD", "20"))
    recent_keep = int(os.getenv("RECENT_MESSAGES_KEEP", "10"))
    msg_count = get_message_count(user_id, char_id)
    if msg_count > summary_threshold:
        asyncio.create_task(_run_summary(user_id, char_id, recent_keep))


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/image 커맨드 핸들러 — 대화 맥락 기반으로 이미지를 생성한다. (관리자 전용)"""
    # 관리자 체크
    admin_ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    if str(update.effective_user.id) not in admin_ids:
        await update.message.reply_text("이 기능은 관리자 전용입니다.")
        return

    custom_command = " ".join(context.args) if context.args else ""
    user_id = update.effective_user.id
    char_id, character = _get_character(context, user_id)
    anchor_image = character.get("anchor_image", "")

    recent_history = get_history(user_id, limit=6, character_id=char_id)

    async def keep_typing():
        """이미지 생성 대기 중 3초마다 upload_photo indicator를 전송한다."""
        while True:
            await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    outfit = get_outfit(user_id, char_id)
    # P10 Phase 2 — location_context 배경 태그 주입 (캐시 히트 시만)
    _img_loc_bg = ""
    try:
        _img_stats = get_character_stats(user_id, char_id)
        _img_loc = _normalize_location_key(_img_stats.get("location") or "")
        if _img_loc:
            from src.history import get_location_context as _glc2
            _img_ctx = _glc2(_img_loc)
            if _img_ctx:
                _img_loc_bg = _img_ctx.get("danbooru_background", "") or ""
    except Exception:
        _img_loc_bg = ""
    typing_task = asyncio.create_task(keep_typing())
    try:
        tags = await generate_danbooru_tags(
            recent_history, custom_command, character=character, char_id=char_id,
            outfit_override=outfit,
            location_background=_img_loc_bg,
        )
        logger.info("Grok 태그 (유저 %s /image): pos=%s | neg=%s | orient=%s | skip_face=%s",
                    user_id, tags["pos_prompt"][:150], tags["neg_prompt"][:80],
                    tags.get("orientation"), tags.get("skip_face"))
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"], anchor_image, orientation, skip_face,
        )

        if image_path:
            desc = custom_command if custom_command else "사진"
            # Admin은 항상 비디오 버튼 표시
            video_ctx_id = _store_video_context(
                user_id, char_id, image_path, desc,
                danbooru_tags=tags["pos_prompt"],
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{video_ctx_id}")
            ]])
            with open(image_path, "rb") as photo_file:
                await update.message.reply_photo(photo=photo_file, reply_markup=keyboard)
            save_message(user_id, "assistant", f"(IMAGE_SENT: {desc})", character_id=char_id)
            logger.info("유저 %s 이미지 생성 완료: %s", user_id, tags["pos_prompt"][:80])
        else:
            await update.message.reply_text("이미지 생성에 실패했어... 다시 시도해줘!")
    finally:
        typing_task.cancel()


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset 커맨드 — 이 캐릭터 봇의 히스토리를 초기화한다."""
    user_id = update.effective_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)

    clear_history(user_id, character_id=char_id)
    await update.message.reply_text(f"[{char_name}] 대화 히스토리가 초기화되었습니다.")
    logger.info("유저 %s의 캐릭터 %s 히스토리 초기화", user_id, char_id)


async def _unsupported_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텍스트 외 메시지 (사진, 파일, 스티커 등) — 안내 메시지 전송 후 자동 삭제."""
    msg = await update.message.reply_text("텍스트 메시지만 보낼 수 있어요! / Text messages only!")
    # 5초 후 안내 메시지 삭제 (채팅 오염 방지)
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except Exception:
        pass


# 의상 변경 감지 키워드

async def outfit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/outfit 커맨드 — 현재 의상 확인 / 리셋."""
    user_id = update.effective_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)

    args = context.args

    # /outfit reset — preset으로 복귀
    if args and args[0].lower() == "reset":
        reset_outfit(user_id, char_id)
        img_config = _load_image_config(char_id)
        default_clothing = img_config.get("clothing", "기본")
        await update.message.reply_text(f"({char_name}의 의상이 기본으로 초기화되었습니다: {default_clothing})")
        return

    # /outfit — 현재 의상 표시 + 프리셋 목록
    outfit = get_outfit(user_id, char_id)
    img_config = _load_image_config(char_id)

    if outfit and outfit["source"] == "custom":
        current = outfit["clothing"]
        current_underwear = outfit.get("underwear", "") or ""
        source_text = "커스텀"
    else:
        current = img_config.get("clothing", "없음")
        current_underwear = ""
        source_text = "기본"

    text = f"👗 {char_name}의 현재 의상\n\n"
    text += f"의상: {current}\n"
    if current_underwear:
        text += f"속옷: {current_underwear}\n"
    text += f"출처: {source_text}\n\n"

    # 프리셋 목록 (outfits 배열이 있으면 표시)
    outfits = img_config.get("outfits", [])
    if outfits:
        text += "프리셋:\n"
        keyboard = []
        for i, o in enumerate(outfits):
            text += f"  {i+1}. {o['name']}\n"
            keyboard.append([InlineKeyboardButton(o["name"], callback_data=f"outfit_{i}")])
        keyboard.append([InlineKeyboardButton("🔄 기본으로 리셋", callback_data="outfit_reset")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        text += "/outfit reset — 기본 의상으로 초기화"
        await update.message.reply_text(text)


async def outfit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """의상 프리셋 선택 콜백."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)
    img_config = _load_image_config(char_id)
    outfits = img_config.get("outfits", [])

    if query.data == "outfit_reset":
        reset_outfit(user_id, char_id)
        default_clothing = img_config.get("clothing", "기본")
        await query.edit_message_text(f"({char_name}의 의상이 기본으로 초기화되었습니다: {default_clothing})")
        return

    # outfit_0, outfit_1, etc.
    try:
        idx = int(query.data.split("_")[1])
        selected = outfits[idx]
    except (IndexError, ValueError):
        await query.edit_message_text("잘못된 선택입니다.")
        return

    set_outfit(user_id, char_id, selected["clothing"], selected.get("underwear", ""), source="custom")
    await query.edit_message_text(f"({char_name}의 의상이 변경되었습니다: {selected['name']})")
    logger.info("유저 %s 의상 변경: %s → %s", user_id, char_id, selected["name"])


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — 캐릭터 수치 조회 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return

    char_id = context.bot_data.get("char_id", "")
    char_name = context.bot_data.get("character", {}).get("name", char_id)
    args = context.args or []

    # /stats <user_id> → 특정 유저 조회 (Admin)
    target_user = int(args[0]) if args else update.effective_user.id

    stats = get_character_stats(target_user, char_id)
    text = (
        f"📊 캐릭터 수치 ({char_name})\n"
        f"유저: {target_user}\n\n"
        f"fixation: {stats['fixation']}/100\n"
        f"mood: {stats['mood']}\n"
        f"location: {stats.get('location') or '(없음)'}\n"
        f"total_turns: {stats.get('total_turns', 0)}"
    )
    await update.message.reply_text(text)


async def setstat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setstat — 캐릭터 수치 직접 설정 (Admin 전용).
    사용법: /setstat fixation 50, /setstat mood worship, /setstat total_turns 8
    """
    if not check_admin(update.effective_user.id):
        return

    user_id = update.effective_user.id
    char_id = context.bot_data.get("char_id", "")
    if not char_id:
        await update.message.reply_text("캐릭터 봇에서만 사용 가능합니다.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("사용법: /setstat <key> <value>\n예: /setstat fixation 50")
        return

    key = args[0].lower()
    value = args[1]

    cache_key = (user_id, char_id)
    stats = get_character_stats(user_id, char_id)
    cached = _stats_cache.get(cache_key, {})

    if key == "fixation":
        cached["fixation"] = max(0, min(100, int(value)))
    elif key == "mood":
        cached["mood"] = value
    elif key == "total_turns":
        cached["_total_turns"] = int(value)
    elif key == "location":
        cached["location"] = value
    else:
        await update.message.reply_text(f"알 수 없는 키: {key}\n사용 가능: fixation, mood, total_turns, location")
        return

    cached["_dirty"] = True
    _stats_cache[cache_key] = cached
    _schedule_flush(user_id, char_id)

    await update.message.reply_text(f"✅ {char_id} {key} = {value}")


async def capture_scene_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📷촬영 버튼 콜백 — 현재 장면을 이미지로 캡쳐."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    char_id = context.bot_data.get("char_id", "")
    character = context.bot_data.get("character", {})
    char_name = character.get("name", char_id)

    # 티어/한도 체크
    tier = get_user_tier(user_id)
    limit_msg = check_image_limit(user_id, tier)
    if limit_msg:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # 버튼 제거 + 진행 표시
    await query.edit_message_reply_markup(reply_markup=None)

    # 최근 대화 히스토리 로드 (auto-image와 동일한 limit=6)
    recent_history = get_history(user_id, limit=6, character_id=char_id)

    if not recent_history:
        return

    # Grok으로 태그 생성
    try:
        chat_id = query.message.chat_id

        async def keep_uploading_capture():
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(3)

        upload_task = asyncio.create_task(keep_uploading_capture())

        image_config = _load_image_config(char_id)
        current_stats = get_character_stats(user_id, char_id)
        force_mood = current_stats["mood"] if current_stats["mood"] not in ("neutral", "") else None

        _cur_location = current_stats.get("location", "")
        loc_hint = f" Current location: {_cur_location}." if _cur_location else ""
        # scene hint — custom_command으로 전달 (auto-image와 동일 패턴)
        scene_desc = f"Capture the current scene.{loc_hint}"
        if force_mood:
            scene_desc += f" [mood:{force_mood}]"

        outfit = get_outfit(user_id, char_id)
        # P10 Phase 2 — location_context 배경 태그 주입 (캐시 히트 시만)
        _cap_loc_bg = ""
        if _cur_location:
            try:
                from src.history import get_location_context as _glc3
                _cap_ctx = _glc3(_normalize_location_key(_cur_location))
                if _cap_ctx:
                    _cap_loc_bg = _cap_ctx.get("danbooru_background", "") or ""
            except Exception:
                _cap_loc_bg = ""
        # 실제 history 리스트를 그대로 Grok에 전달 (auto-image와 동일)
        tags = await generate_danbooru_tags(
            recent_history,
            scene_desc,
            character=character,
            char_id=char_id,
            outfit_override=outfit,
            location_background=_cap_loc_bg,
        )

        if not tags or tags.get("pos_prompt") == "BLOCKED":
            upload_task.cancel()
            return

        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        anchor = character.get("anchor_image", "")

        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            anchor, orientation, skip_face,
        )

        upload_task.cancel()

        if image_path and image_path not in ("QUEUE_FULL", "TIMEOUT"):
            tier = get_user_tier(user_id)
            if tier == "premium" or check_admin(user_id):
                video_ctx_id = _store_video_context(
                    user_id, char_id, image_path, scene_desc,
                    danbooru_tags=tags["pos_prompt"],
                )
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{video_ctx_id}")
                ]])
                with open(image_path, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=keyboard)
            else:
                with open(image_path, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo)
                os.remove(image_path)
            increment_usage(user_id, "images")
            increment_daily_images(user_id)
        elif image_path == "TIMEOUT":
            await notify_image_timeout(context.bot, user_id, char_name)
    except Exception as e:
        upload_task.cancel()
        logger.error("📷촬영 실패: %s", e)


async def video_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎬 영상 생성 버튼 콜백 처리."""
    query = update.callback_query
    await query.answer()

    data = query.data  # "video:{ctx_id}"
    if not data or not data.startswith("video:"):
        return

    ctx_id = data.split(":", 1)[1]
    ctx = _get_video_context(ctx_id)
    if not ctx:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⏰ 영상 생성 시간이 만료되었어요.")
        return

    user_id = ctx["user_id"]
    char_id = ctx["char_id"]
    tier = get_user_tier(user_id)

    # 한도 체크
    limit_msg = check_video_limit(user_id, tier)
    if limit_msg:
        await query.message.reply_text(limit_msg)
        return

    # 버튼 → "생성 중..." 으로 교체
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("⏳ 영상 생성 중...", callback_data="noop")
    ]]))

    # upload_video typing indicator (3초마다 반복)
    chat_id = query.message.chat_id
    async def keep_uploading_video():
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
            except Exception:
                pass
            await asyncio.sleep(3)

    upload_task = asyncio.create_task(keep_uploading_video())

    video_path = None
    prompts_blocked = False
    try:
        # Grok 비디오 프롬프트 생성 (이미지 Vision + 대화 히스토리 + i2v 가이드)
        from src.grok import generate_video_prompts
        recent_history = get_history(user_id, limit=6, character_id=char_id)
        stats = get_character_stats(user_id, char_id)
        try:
            prompts = await generate_video_prompts(
                ctx["description"],
                image_path=ctx["image_path"],
                chat_history=recent_history,
                danbooru_tags=ctx.get("danbooru_tags", ""),
                mood=stats.get("mood", "neutral"),
            )
        except Exception as e:
            logger.error("Grok 비디오 프롬프트 실패: %s", e)
            prompts = {"motion_prompt": ctx["description"], "audio_prompt": "soft moan, heavy breathing, intimate silence"}

        # video-improve2 (P15) — Admin debug dump (VIDEO_DEBUG_DUMP=1)
        if prompts.get("_debug_analyzer_json") and check_admin(user_id):
            import json as _json
            dump = (
                "🔍 VIDEO DEBUG\n\n"
                f"Analyzer:\n```\n{_json.dumps(prompts['_debug_analyzer_json'], ensure_ascii=False, indent=2)}\n```\n\n"
                f"Preset ({prompts.get('_debug_pose_key_resolved')}):\n"
                f"```\n{_json.dumps(prompts.get('_debug_preset'), ensure_ascii=False, indent=2)}\n```\n\n"
                f"Motion:\n{(prompts.get('motion_prompt') or '')[:500]}"
            )
            try:
                await context.bot.send_message(chat_id=user_id, text=dump, parse_mode="Markdown")
            except Exception:
                try:
                    await context.bot.send_message(chat_id=user_id, text=dump[:4000])
                except Exception as _e:
                    logger.warning("VIDEO_DEBUG_DUMP 전송 실패 (char): %s", _e)

        # Phase 2-B — Step 2 태그 추가 fallback 성공 기록 (모니터링용)
        if prompts.get("_csam_fallback_used"):
            logger.info("Grok Step 2 fallback 성공: user=%s char=%s", user_id, char_id)

        # Phase 2-B — 최종 BLOCKED 시 에러 메시지
        if prompts.get("motion_prompt") == "BLOCKED" or prompts.get("_csam_blocked"):
            prompts_blocked = True
            logger.warning("Grok 비디오 최종 차단: user=%s char=%s", user_id, char_id)
        else:
            # Admin 알림 — 영상 생성 시작 (prompts 정보 포함)
            try:
                await notify_admins_video(
                    context,
                    triggering_user_id=user_id,
                    source="char_bot",
                    char_id=char_id,
                    status="started",
                    pose_key=prompts.get("_debug_pose_key_resolved", ""),
                    safety_level=prompts.get("_debug_safety_level", ""),
                    motion_prompt=prompts.get("motion_prompt", ""),
                    audio_prompt=prompts.get("audio_prompt", ""),
                )
            except Exception as _e:
                logger.warning("admin video notify (started) 실패: %s", _e)

            # AtlasCloud 비디오 생성 (오디오 자동 처리)
            from src.video import generate_video
            video_path = await generate_video(
                image_path=ctx["image_path"],
                motion_prompt=prompts["motion_prompt"],
                audio_prompt=prompts.get("audio_prompt", ""),
                lora_config=prompts.get("lora_config"),
            )
    finally:
        upload_task.cancel()

    if prompts_blocked:
        # Grok이 두 번 모두 차단한 경우 — 유저에게는 단일 에러만 전달 (카운트는 성공 시에만 증가하므로 변화 없음)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{ctx_id}")
            ]]))
        except Exception:
            pass
        await query.message.reply_text("😢 영상 생성이 제한됐어요. 다시 시도해 주세요.")
        logger.warning("유저 %s 비디오 Grok 차단 (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="blocked",
                                      extra="Grok motion BLOCKED (CSAM filter)")
        except Exception:
            pass
        return

    if video_path:
        # 성공: 버튼 제거 + 비디오 전송
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        with open(video_path, "rb") as f:
            await query.message.reply_video(video=f)
        increment_usage(user_id, "videos")
        increment_daily_videos(user_id)
        _cleanup_video_context(ctx_id)
        try:
            os.unlink(video_path)
        except OSError:
            pass
        logger.info("유저 %s 비디오 생성 완료 (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="success",
                                      pose_key=prompts.get("_debug_pose_key_resolved", ""))
        except Exception:
            pass
    else:
        # 실패: 버튼 복구 (재시도 가능)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{ctx_id}")
            ]]))
        except Exception:
            pass
        await query.message.reply_text("😢 영상 생성에 실패했어요. 다시 시도해주세요.")
        logger.error("유저 %s 비디오 생성 실패 (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="failed",
                                      extra="AtlasCloud video generation failed — check logs")
        except Exception:
            pass


def register_char_handlers(app):
    """캐릭터 봇 Application에 핸들러를 등록한다."""
    app.add_handler(CommandHandler("start", char_start))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("image", handle_image))
    app.add_handler(CommandHandler("outfit", outfit_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("setstat", setstat_command))
    app.add_handler(CallbackQueryHandler(outfit_callback, pattern=r"^outfit_"))
    app.add_handler(CallbackQueryHandler(capture_scene_callback, pattern=r"^capture_scene$"))
    app.add_handler(CallbackQueryHandler(video_callback_handler, pattern=r"^video:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # 텍스트 외 메시지 (사진, 파일, 스티커 등) — 안내 후 삭제
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, _unsupported_message))
