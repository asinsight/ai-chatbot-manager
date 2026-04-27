"""이미지 제네레이터 봇 핸들러 — 모든 메시지 = 이미지 생성 요청.

캐릭터 대화 없이 한글/영어 설명 → Grok 태그 → ComfyUI 이미지 생성.
danbooru 태그 직접 입력도 지원.
"""

import asyncio
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.handlers_common import check_admin, check_image_limit, check_video_limit, notify_admins_video
from src.history import (
    is_onboarded, get_user_tier, increment_usage,
    increment_daily_images, increment_daily_videos,
    is_valid_saved_char_name, save_character, list_saved_characters,
    get_saved_character_by_name, get_saved_character_by_slot,
    delete_saved_character, find_available_slot, SAVED_CHAR_MAX_SLOTS,
)
from src.grok import (
    generate_danbooru_tags,
    generate_danbooru_tags_random,
    classify_tags_to_nested_blocks,
    analyze_partial_edit_intent,
)
import src.comfyui
from src.comfyui import generate_image, check_queue, COMFYUI_MAX_QUEUE
from src.input_filter import filter_input
from src.intent_router import analyze_input_intent
from src.rate_limiter import rate_limiter
from src.trait_pools import roll_character, roll_sfw_scene
from src.video_context import (
    store_video_context,
    get_video_context,
    cleanup_video_context,
)

logger = logging.getLogger(__name__)

MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "")

# 사용 가능한 모델 목록
AVAILABLE_MODELS = {
    "1": {"name": "OneObsession v2.0", "path": "illustrious/oneObsession_v20Bold.safetensors"},
    "2": {"name": "JANKU Chenkin Noobai v7.77", "path": "illustrious/JANKUTrainedChenkinNoobai_v777.safetensors"},
}
DEFAULT_MODEL_KEY = "1"

_HELP_TEXT = (
    "🎨 이미지 생성기\n\n"
    "⚠️ 여기서 만들어지는 캐릭터는 모두 20세 이상입니다.\n\n"
    "이미지를 만들고 싶으면 설명을 보내주세요.\n"
    "한글, 영어 모두 가능합니다.\n\n"
    "💡 사용 예시:\n"
    "• 카페에서 커피 마시는 예린이\n"
    "• 수아가 해변에서 비키니 입고 있는 장면\n"
    "• 도서관에서 책 읽는 여자\n"
    "• 이번엔 웃는 표정으로 ← 이전 이미지 수정\n"
    "• 같은 구도에서 옷만 바꿔줘 seed:12345\n\n"
    "📌 기능:\n"
    "• 캐릭터 이름 → 해당 캐릭터 외모 자동 적용\n"
    "• danbooru 태그 직접 입력 가능\n"
    "• 이전 이미지 기반 수정 (자동)\n"
    "• seed 지정으로 동일 구도 유지\n"
    "• 🎲 /random — 완전 랜덤 SFW 이미지\n"
    "• 💾 캐릭터 저장 — 이미지 완성 후 버튼으로 저장 (최대 3개)\n\n"
    "💾 캐릭터 저장/호출:\n"
    "• 이미지 생성 후 💾 캐릭터 저장 버튼 → 이름 입력 (영문/숫자/언더스코어 1~20자)\n"
    "• `@이름`으로 호출 → 해당 외모로 새 이미지 생성\n"
    "  예: `@minkyung 해변에서 비키니`\n"
    "  예: `@yerin_dress 카페에서 커피`\n\n"
    "🔧 커맨드:\n"
    "/help — 도움말\n"
    "/reset — 세션 초기화 (HQ/모델 설정은 유지)\n"
    "/seed — 마지막 사용 시드 확인\n"
    "/model — 모델 변경 (변경 시 로딩 시간 추가)\n"
    "/hq on|off — 고화질 모드 토글 (Premium 전용)\n"
    "/random — 🎲 랜덤 SFW 이미지 생성\n"
    "/chars — 저장된 캐릭터 목록 (🗑️ 삭제 버튼 포함)\n"
    "/cancel — 저장 중인 작업 취소"
)

_VIDEO_CAPTION_PREMIUM = (
    "🎬 버튼을 눌러 자동 모션 영상 생성"
)

# 랜덤 버튼 인라인 키보드 (🎲 SFW 단일 버튼)
_RANDOM_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🎲 Random SFW", callback_data="random:sfw"),
]])

# 한글 이름 → char_id 매핑
CHAR_NAME_MAP = {
    "수아": "char01", "이수아": "char01",
    "민경": "char02", "박민경": "char02",
    "아린": "char03", "최아린": "char03",
    "서연": "char04", "박서연": "char04",
    "유리": "char05", "한유리": "char05",
    "예린": "char06", "강예린": "char06",
    "엘라라": "char07", "엘라라 폰 나흐트": "char07", "나흐트": "char07",
    "리아엘": "char08", "리아엘 폰 아이젠하르트": "char08", "아이젠하르트": "char08",
    "수연": "char09", "박수연": "char09", "수연누나": "char09", "수연 누나": "char09",
    "유진": "char10", "서유진": "char10",
}


def _match_character(text: str, characters: dict) -> tuple[str, dict | None]:
    """텍스트에서 캐릭터 이름을 감지하여 char_id와 캐릭터 딕셔너리를 반환."""
    for name, char_id in CHAR_NAME_MAP.items():
        if name in text and char_id in characters:
            return char_id, characters[char_id]
    return "", None


def _is_danbooru_tags(text: str) -> bool:
    """입력이 danbooru 태그인지 판별 (콤마 구분 + 한글 없음)."""
    if "," not in text:
        return False
    if re.search(r"[가-힣]", text):
        return False
    return True


_HQ_WORKFLOW = "comfyui_workflow/main_character_build_highqual.json"

# 이미지 제네레이터 고정 positive prefix — 모든 생성(custom 텍스트 + /random)에 선두 부착.
# 한국인 + VN 스타일로 일관성 유도.
IMAGEGEN_FIXED_PREFIX = "1girl, solo, beautiful korean woman, visual novel style"


def _extract_seed(text: str) -> tuple[str, int]:
    """텍스트에서 seed:12345 패턴을 추출. 반환: (시드 제거된 텍스트, 시드값). 없으면 시드=0."""
    match = re.search(r"seed[:\s]*(\d+)", text, re.IGNORECASE)
    if match:
        seed = int(match.group(1))
        cleaned = text[:match.start()].strip() + " " + text[match.end():].strip()
        return cleaned.strip(), seed
    return text, 0


# @name 참조 정규식 — 식별자(영문/숫자/언더스코어/.) 직후의 @는 제외 (이메일 false positive 방어)
# 예) email@domain.com 의 domain 은 매칭 X. (@minkyung)/공백 뒤 @minkyung 은 매칭 O.
_AT_NAME_RE = re.compile(r"(?<![a-zA-Z0-9_.])@([a-zA-Z0-9_]{1,20})\b")


def _resolve_saved_char_ref(
    text: str, user_id: int
) -> tuple[dict | None, str, str | None, str | None]:
    """텍스트에서 @이름 참조를 추출하고 저장 캐릭터를 조회.

    Returns:
        (saved_char | None, remaining_text, error_kind | None, attempted_name | None)
        - 매칭 0개: (None, text, None, None) — 일반 처리
        - 매칭 2개+: (None, text, "multiple", None) — 핸들러가 거부 메시지 응답
        - 매칭 1개 + DB hit: (char_dict, stripped_text, None, name) — identity_override 적용
        - 매칭 1개 + DB miss: (None, text, "not_found", name) — 핸들러가 안내 + 목록 응답

    원칙:
        - 첫 번째 매칭만 인식 (정책: 두 캐릭터 동시 호출 거부)
        - DB miss는 명시적 안내 (오타 발견 + 저장 목록 노출)
        - 순수 함수 — DB lookup 외 사이드이펙트 없음
    """
    matches = _AT_NAME_RE.findall(text)
    if not matches:
        return None, text, None, None
    if len(matches) >= 2:
        return None, text, "multiple", None

    name = matches[0]
    char = get_saved_character_by_name(user_id, name)
    if not char:
        # DB miss — 핸들러에서 저장 목록과 함께 안내
        return None, text, "not_found", name

    # @name 토큰 제거 — 첫 번째 매칭만 strip
    full_match = _AT_NAME_RE.search(text)
    if full_match:
        stripped = text[: full_match.start()] + text[full_match.end():]
        # 양옆 공백 정리 + 연속 공백 단일화
        stripped = re.sub(r"\s+", " ", stripped).strip()
    else:
        stripped = text
    return char, stripped, None, name


def _format_saved_chars_list(user_id: int) -> str:
    """저장된 캐릭터 목록을 마크다운 문자열로 포맷.

    Returns:
        포맷 문자열. 저장된 캐릭터가 없으면 "저장된 캐릭터가 없습니다." 안내.
    """
    chars = list_saved_characters(user_id)
    if not chars:
        return "_(저장된 캐릭터가 없습니다. 이미지 생성 후 💾 캐릭터 저장 버튼을 눌러 저장하세요.)_"
    lines = [f"💾 저장된 캐릭터 ({len(chars)}/{SAVED_CHAR_MAX_SLOTS}):"]
    for c in chars:
        appearance = c.get('appearance_tags', '') or ''
        suffix = '...' if len(appearance) > 60 else ''
        lines.append(f"  슬롯 {c['slot']}: `{c['name']}` — {appearance[:60]}{suffix}")
    lines.append("")
    lines.append("호출: 이미지 생성 요청에 `@이름` 포함 (예: `@minkyung 해변 비키니`)")
    return "\n".join(lines)


def _clear_session(user_data: dict) -> None:
    """세션 상태 정리 — hq_mode / selected_model 같은 지속 선호는 유지."""
    # 이전 이미지 ctx 정리 (파일 삭제 + 컨텍스트 제거)
    old_ctx = user_data.get("last_video_ctx_id")
    if old_ctx:
        cleanup_video_context(old_ctx)
    # 세션에서만 관리하던 이미지 파일 (ctx 미등록분)
    old_path = user_data.get("last_image_path")
    if old_path and os.path.exists(old_path):
        try:
            os.unlink(old_path)
        except OSError:
            pass
    for k in (
        "last_tags", "last_char_id", "last_character", "last_seed",
        "last_image_path", "last_korean_description", "last_random_mode",
        "last_video_ctx_id", "last_danbooru_tags",
    ):
        user_data.pop(k, None)


async def imagegen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — 이미지 생성기 안내."""
    # 세션 초기화 (hq_mode / selected_model은 유지)
    _clear_session(context.user_data)
    await update.message.reply_text(_HELP_TEXT, reply_markup=_RANDOM_KEYBOARD)


async def imagegen_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — 도움말."""
    await update.message.reply_text(_HELP_TEXT, reply_markup=_RANDOM_KEYBOARD)


async def imagegen_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset — 세션 초기화 (hq_mode / selected_model 등 지속 선호는 유지)."""
    _clear_session(context.user_data)
    await update.message.reply_text("🔄 세션이 초기화되었습니다. 새로운 이미지를 설명해주세요!")


async def imagegen_hq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hq on|off|status — 고화질 모드 토글 (Premium 전용)."""
    user_id = update.effective_user.id
    args = [a.lower() for a in (context.args or [])]

    if not args or args[0] == "status":
        state = "ON" if context.user_data.get("hq_mode", False) else "OFF"
        await update.message.reply_text(f"현재 HQ: {state}\n\n사용법: /hq on | /hq off")
        return

    if args[0] == "on":
        tier = get_user_tier(user_id)
        if tier != "premium" and not check_admin(user_id):
            await update.message.reply_text(
                "_(고화질(HQ) 모드는 Premium 구독자 전용입니다.)_",
                parse_mode="Markdown",
            )
            return
        context.user_data["hq_mode"] = True
        await update.message.reply_text("✅ HQ 모드 ON — 이후 이미지는 고화질 워크플로우로 생성됩니다.")
        logger.info("이미지봇 HQ ON: user=%s", user_id)
        return

    if args[0] == "off":
        context.user_data["hq_mode"] = False
        await update.message.reply_text("✅ HQ OFF")
        logger.info("이미지봇 HQ OFF: user=%s", user_id)
        return

    await update.message.reply_text("사용법: /hq on | /hq off | /hq status")


async def _send_image_with_video_option(
    *,
    target_message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    image_path: str,
    description: str,
    danbooru_tags: str,
    extra_caption: str = "",
    scene_key: str | None = None,
) -> None:
    """이미지 전송 + Premium/Admin이면 🎬 버튼 부착.

    - Premium/Admin: store_video_context → 🎬 버튼, 파일은 TTL cleanup에 위임
    - 비 Premium: 버튼 없이 전송 후 즉시 os.unlink
    세션에 last_image_path / last_korean_description / last_danbooru_tags / last_video_ctx_id 기록.
    """
    tier = get_user_tier(user_id)
    is_premium = tier == "premium" or check_admin(user_id)

    # 이전 ctx 정리
    old_ctx = context.user_data.get("last_video_ctx_id")
    if old_ctx:
        cleanup_video_context(old_ctx)
    old_path = context.user_data.get("last_image_path")
    if old_path and old_path != image_path and os.path.exists(old_path):
        try:
            os.unlink(old_path)
        except OSError:
            pass

    if is_premium:
        ctx_id = store_video_context(
            user_id=user_id,
            char_id="imagegen",
            image_path=image_path,
            description=description,
            danbooru_tags=danbooru_tags,
            scene_key=scene_key,
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{ctx_id}"),
            InlineKeyboardButton("💾 캐릭터 저장", callback_data="savechar:init"),
        ]])
        caption = _VIDEO_CAPTION_PREMIUM
        if extra_caption:
            caption = f"{extra_caption}\n{caption}"
        with open(image_path, "rb") as f:
            await target_message.reply_photo(photo=f, caption=caption, reply_markup=keyboard)
        context.user_data["last_video_ctx_id"] = ctx_id
    else:
        # Free/Standard: 💾 저장 버튼만 (영상 불가)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💾 캐릭터 저장", callback_data="savechar:init"),
        ]])
        with open(image_path, "rb") as f:
            await target_message.reply_photo(photo=f, caption=extra_caption or None, reply_markup=keyboard)
        try:
            os.unlink(image_path)
        except OSError:
            pass
        context.user_data["last_video_ctx_id"] = None

    # 세션 저장 — 한글 수정 재활용 (이전 이미지 기반 수정)
    context.user_data["last_image_path"] = image_path if is_premium else None
    context.user_data["last_korean_description"] = description
    context.user_data["last_danbooru_tags"] = danbooru_tags


async def imagegen_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/random — 랜덤 SFW 이미지 버튼 노출."""
    await update.message.reply_text(
        "🎲 랜덤 SFW 이미지를 생성합니다.\n버튼을 눌러주세요:",
        reply_markup=_RANDOM_KEYBOARD,
    )


async def imagegen_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/seed — 마지막 사용 시드 확인."""
    last_seed = context.user_data.get("last_seed", 0)
    if last_seed:
        await update.message.reply_text(f"🌱 마지막 시드: {last_seed}\n\n사용법: 설명 뒤에 seed:{last_seed} 추가")
    else:
        await update.message.reply_text("아직 생성된 이미지가 없습니다.")


async def imagegen_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/model [번호] — 모델 변경 또는 현재 모델 확인 (Premium + Admin 전용)."""
    user_id = update.effective_user.id
    tier = get_user_tier(user_id)
    if tier != "premium" and not check_admin(user_id):
        await update.message.reply_text("_(모델 변경은 Premium 구독자 전용입니다.)_", parse_mode="Markdown")
        return

    args = context.args or []
    current_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    current_model = AVAILABLE_MODELS[current_key]

    # 현재 ComfyUI에 로드된 모델
    loaded = src.comfyui.current_loaded_checkpoint

    if not args:
        # 모델 목록 표시
        lines = []
        for key, m in AVAILABLE_MODELS.items():
            marker = " ✅" if key == current_key else ""
            loaded_marker = " (로드됨)" if m["path"] == loaded else ""
            lines.append(f"  {key}. {m['name']}{marker}{loaded_marker}")
        text = (
            "🎛 모델 선택:\n\n"
            + "\n".join(lines)
            + f"\n\n현재 선택: {current_model['name']}"
        )
        if loaded and loaded != current_model["path"]:
            text += "\n⚠️ 다른 모델이 로드되어 있어 첫 생성 시 전환 시간이 추가됩니다."
        text += "\n\n사용법: /model 번호 (예: /model 2)"
        await update.message.reply_text(text)
        return

    choice = args[0]
    if choice not in AVAILABLE_MODELS:
        await update.message.reply_text(f"1~{len(AVAILABLE_MODELS)} 중 선택해주세요.")
        return

    context.user_data["selected_model"] = choice
    selected = AVAILABLE_MODELS[choice]
    msg = f"✅ 모델 변경: {selected['name']}"
    if loaded and selected["path"] != loaded:
        msg += "\n⚠️ 현재 다른 모델이 로드되어 있어 첫 생성 시 10~30초 추가 소요됩니다."
    await update.message.reply_text(msg)
    logger.info("이미지봇 모델 변경: user=%s model=%s", update.effective_user.id, selected["name"])


async def imagegen_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """모든 텍스트 메시지 = 이미지 생성 요청.

    단, pending_save 상태면 텍스트를 캐릭터 저장 이름으로 먼저 처리.
    """
    user_id = update.effective_user.id
    description = update.message.text.strip()

    if not description:
        return

    # 새 턴 시작 — 이전 턴의 identity_override leak 방지
    # (save-name 경로는 identity_override를 쓰지 않으므로 무관)
    context.user_data.pop("identity_override", None)

    # pending_save 상태이면 텍스트를 이름으로 처리
    if await _try_handle_save_name(update, context):
        return

    # 입력 필터링 (프롬프트 인젝션 + 부적절 콘텐츠 방어)
    description, blocked, block_reason = await filter_input(description)
    if blocked:
        logger.warning("[security] 이미지봇 입력 차단: user=%s reason=%s", user_id, block_reason)
        await update.message.reply_text("_(허용되지 않는 내용이 포함되어 있습니다.)_", parse_mode="Markdown")
        return

    # 시드 추출 (seed:12345 패턴)
    description, user_seed = _extract_seed(description)
    if not description:
        return

    # @name 파서 — 저장된 캐릭터 호출 (Phase 1-D)
    # 무거운 작업 전에 처리하되, security/seed 파싱 뒤에 둠 (security 필터는 통과해야 하므로)
    saved_char, description, parse_err, attempted_name = _resolve_saved_char_ref(description, user_id)
    if parse_err == "multiple":
        await update.message.reply_text(
            "_(동일 이미지 내 두 캐릭터 동시 호출은 지원하지 않습니다. 한 캐릭터씩 사용해주세요.)_",
            parse_mode="Markdown",
        )
        return
    if parse_err == "not_found":
        # 저장된 캐릭터 매칭 실패 — 안내 + 목록 표시
        saved_list = _format_saved_chars_list(user_id)
        await update.message.reply_text(
            f"저장된 캐릭터 `{attempted_name}`을(를) 찾을 수 없습니다.\n\n{saved_list}",
            parse_mode="Markdown",
        )
        logger.info("@name DB miss: user=%s attempted_name=%s", user_id, attempted_name)
        return
    # Local LLM 의도 라우터 — RESET / EDIT_SAVED / RECALL / NEW / MODIFY / SCENE 분류
    # @name fast-path 통과 후 자유 텍스트 의도를 분류한다.
    # 기존 4종 휴리스틱(reset 키워드 셋, edit 힌트 정규식, last_tags presence 분기,
    # 리셋 판단 함수)을 단일 분류기로 대체.
    #
    # 라우터 + dispatch + EDIT_SAVED analyzer는 LLM 호출 1~6초 소요 — 사용자 경험을 위해
    # UPLOAD_PHOTO typing indicator를 라우터 시작부터 dispatch 종료까지 유지.
    async def _router_spinner():
        while True:
            try:
                await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            except Exception:
                pass
            await asyncio.sleep(3)

    router_spinner_task = asyncio.create_task(_router_spinner())
    try:
        last_tags_for_router = context.user_data.get("last_tags", "")
        intent_result = await analyze_input_intent(
            text=description,
            has_saved_char_ref=bool(saved_char),
            has_last_tags=bool(last_tags_for_router),
            user_id=user_id,
        )
        intent = intent_result["intent"]
        scene_description = intent_result["scene_description"]
        edit_clause = intent_result["edit_clause"]
        logger.info(
            "intent router: user=%s intent=%s scene=%r edit=%r saved_char=%s last_tags=%s",
            user_id, intent, scene_description[:40], edit_clause[:40],
            bool(saved_char), bool(last_tags_for_router),
        )

        # RESET — 세션 초기화 후 잔여 텍스트로 NEW으로 진행 (잔여 비면 안내 후 종료)
        if intent == "RESET":
            for k in (
                "last_tags", "last_char_id", "last_character", "last_seed",
                "last_random_traits", "last_random_mode",
            ):
                context.user_data.pop(k, None)
            if not scene_description.strip():
                await update.message.reply_text("🔄 세션이 초기화되었습니다. 새로운 이미지를 설명해주세요!")
                return
            intent = "NEW"
            description = scene_description

        # RECALL — saved 캐릭터 identity_override + scene 그대로
        elif intent == "RECALL" and saved_char:
            context.user_data["identity_override"] = saved_char
            description = scene_description or ""
            logger.info(
                "@name RECALL: user=%s name=%s slot=%s",
                user_id, saved_char["name"], saved_char["slot"],
            )

        # EDIT_SAVED — Grok analyzer로 surgical edit 산출 + DB update + identity_override
        elif intent == "EDIT_SAVED" and saved_char:
            current_blocks = {
                "appearance_tags": saved_char.get("appearance_tags", "") or "",
                "clothing":        saved_char.get("clothing", "") or "",
                "underwear":       saved_char.get("underwear", "") or "",
                "body_shape":      saved_char.get("body_shape") or {},
                "breast":          saved_char.get("breast") or {},
            }
            analyzer_input = (edit_clause or description or "").strip()
            try:
                ed_intent = await analyze_partial_edit_intent(analyzer_input, current_blocks)
            except Exception as e:
                logger.error("analyze_partial_edit_intent 실패: user=%s err=%s", user_id, e)
                ed_intent = {"edits": {}, "scene_description": ""}

            edits = ed_intent.get("edits") or {}
            if edits:
                # nested deep-merge: top-level flat keys 교체 + nested dict는 sub-key 단위 overlay
                merged = dict(current_blocks)
                for top_key in ("appearance_tags", "clothing", "underwear"):
                    if top_key in edits and isinstance(edits[top_key], str):
                        merged[top_key] = edits[top_key]
                for nested_key in ("body_shape", "breast"):
                    if nested_key in edits and isinstance(edits[nested_key], dict):
                        merged[nested_key] = {**(merged[nested_key] or {}), **edits[nested_key]}
                try:
                    save_character(
                        user_id=user_id,
                        slot=saved_char["slot"],
                        name=saved_char["name"],
                        appearance_tags=merged["appearance_tags"],
                        clothing=merged["clothing"],
                        underwear=merged["underwear"],
                        body_shape=merged["body_shape"],
                        breast=merged["breast"],
                    )
                    refreshed = get_saved_character_by_slot(user_id, saved_char["slot"])
                    if refreshed:
                        saved_char = refreshed
                    context.user_data["pending_edit_confirm"] = {
                        "name": saved_char["name"],
                        "fields": list(edits.keys()),
                    }
                    logger.info(
                        "@name partial edit: user=%s name=%s slot=%s fields=%s",
                        user_id, saved_char["name"], saved_char["slot"], list(edits.keys()),
                    )
                except Exception as e:
                    logger.error("save_character (partial edit) 실패: user=%s err=%s", user_id, e)

            context.user_data["identity_override"] = saved_char
            # analyzer가 추출한 scene이 더 정확하면 사용, 아니면 라우터의 scene_description 유지
            analyzer_scene = (ed_intent.get("scene_description") or "").strip()
            description = analyzer_scene or scene_description or ""

        # NEW — last_tags clear 후 새 캐릭터 생성
        elif intent == "NEW":
            for k in (
                "last_tags", "last_char_id", "last_character", "last_seed",
                "last_random_traits", "last_random_mode",
            ):
                context.user_data.pop(k, None)
            description = scene_description or description

        # MODIFY — last_tags 유지, scene_description으로 진행 (라우터가 last_tags=true에서만 분류)
        elif intent == "MODIFY":
            description = scene_description or description

        # SCENE — last_tags 없는 단순 씬
        elif intent == "SCENE":
            description = scene_description or description
    finally:
        router_spinner_task.cancel()

    if parse_err is None and not saved_char and "@" in update.message.text:
        # @ 가 있었지만 lookbehind에 막혀 매칭 안 됨 (예: email)
        logger.debug("@name 매칭 없음 (lookbehind reject): user=%s text=%r", user_id, update.message.text[:80])

    # 주의: 여기서 description이 비어 있어도 identity_override가 설정되어 있으면 정상 경로다
    # (예: "@minkyung" 단독 호출 — 저장된 캐릭터로 Grok-free pose/scene 자유 생성).
    # description이 비고 identity_override도 없는 케이스는 위쪽 _extract_seed 가드에서 이미 처리됨.

    # HQ 모드 — 세션 토글에서 읽음 (/hq on|off)
    use_hq = bool(context.user_data.get("hq_mode", False))

    # 온보딩 체크
    if not is_onboarded(user_id):
        main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = "서비스 이용을 위해 먼저 메인봇에서 가입해주세요."
        if main_link:
            text += f"\n👉 {main_link}"
        await update.message.reply_text(text)
        return

    # Rate limiting
    allowed, info = rate_limiter.check(user_id)
    if not allowed:
        await update.message.reply_text("_(요청이 너무 빠릅니다. 잠시 후 다시 시도해주세요.)_", parse_mode="Markdown")
        return

    # 티어별 이미지 한도 체크
    tier = get_user_tier(user_id)
    limit_msg = check_image_limit(user_id, tier)
    if limit_msg:
        await update.message.reply_text(limit_msg, parse_mode="Markdown")
        return

    # HQ 워크플로우 티어 체크 (Premium + Admin만)
    # 실행 시점에 티어가 떨어졌다면 세션 토글도 강제 해제
    if use_hq and tier not in ("premium",) and not check_admin(user_id):
        context.user_data["hq_mode"] = False
        await update.message.reply_text(
            "_(고화질(HQ) 모드는 Premium 구독자 전용입니다. HQ OFF로 전환했습니다.)_",
            parse_mode="Markdown",
        )
        use_hq = False

    # ComfyUI 큐 체크
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        await update.message.reply_text("_(이미지 요청이 많아서 지금은 생성할 수 없습니다. 잠시 후 다시 시도해주세요.)_", parse_mode="Markdown")
        return

    # CHAR_NAME_MAP — 캐릭터봇 한글 이름이 감지되면 세션 초기화 (별도 feature)
    # RESET / NEW intent는 라우터 단계에서 이미 처리됨 — 여기서는 char_id 감지만 담당.
    characters = context.bot_data.get("characters", {})
    char_id, character = _match_character(description, characters)
    if char_id:
        for k in (
            "last_tags", "last_char_id", "last_character", "last_seed",
            "last_random_traits", "last_random_mode",
        ):
            context.user_data.pop(k, None)

    # 이전 세션이 있으면 수정 모드
    last_tags = context.user_data.get("last_tags")

    # 수정 모드에서 유저가 명시적 seed 안 썼으면 last_seed 자동 재사용
    # (같은 캐릭터의 다른 장면 생성 시 얼굴/체형 일관성 유지 목적)
    # char_id가 감지된 경우 위에서 이미 last_tags clear 되었으므로 자동 재사용 안됨.
    if user_seed == 0 and last_tags:
        _auto_seed = context.user_data.get("last_seed", 0) or 0
        if _auto_seed:
            user_seed = _auto_seed
            logger.info("이미지봇 수정 모드 — last_seed 자동 재사용: user=%s seed=%s", user_id, user_seed)
    if not char_id:
        # 캐릭터 미매칭 → 이전 세션의 캐릭터 사용
        char_id = context.user_data.get("last_char_id", "")
        character = context.user_data.get("last_character")

    # 커스텀 danbooru 태그 감지
    if _is_danbooru_tags(description):
        # 직접 태그 입력 → Grok 건너뛰기
        tags = {
            "pos_prompt": description,
            "neg_prompt": "worst quality, low quality, normal quality, lowres, blurry",
            "orientation": "portrait",
            "skip_face": False,
        }
        logger.info("이미지봇 커스텀 태그 (유저 %s): %s", user_id, description[:80])
    else:
        # 한글/영어 설명 → Grok 태그 생성
        if not character:
            character = {
                "image_prompt_prefix": IMAGEGEN_FIXED_PREFIX,
                "image_negative_prefix": "",
            }

        # @name 파서가 설정한 저장 캐릭터 override (Phase 1-D step 4)
        identity_override = context.user_data.get("identity_override")

        # identity_override가 있으면 캐릭터 prefix를 IMAGEGEN_FIXED_PREFIX로 강제 — 이전 세션의
        # 캐릭터 persona prefix(`last_character`)가 saved 캐릭터의 정체성을 오염시키지 않도록.
        if identity_override:
            character = {
                "image_prompt_prefix": IMAGEGEN_FIXED_PREFIX,
                "image_negative_prefix": "",
            }

        # 이전 태그가 있으면 chat_history로 전달 (수정 모드).
        # identity_override가 있으면 다른 캐릭터로 전환되었을 수 있으므로 last_tags 무시.
        chat_history = []
        if last_tags and not identity_override:
            chat_history = [
                {"role": "user", "content": "(previous image request)"},
                {"role": "assistant", "content": f"Generated tags: {last_tags}"},
            ]

        # typing indicator
        async def keep_uploading():
            while True:
                await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(3)

        upload_task = asyncio.create_task(keep_uploading())
        try:
            tags = await generate_danbooru_tags(
                chat_history=chat_history,
                custom_command=description,
                character=character,
                char_id=char_id,
                identity_override=identity_override,
            )
            logger.info(
                "이미지봇 Grok 태그 (유저 %s, 수정=%s, override=%s): pos=%s | neg=%s | orient=%s",
                user_id,
                bool(last_tags) and not identity_override,
                identity_override["name"] if identity_override else "(none)",
                tags["pos_prompt"][:300], tags["neg_prompt"][:100], tags.get("orientation"),
            )
        finally:
            upload_task.cancel()

    # Grok 안전 차단 체크
    if tags.get("pos_prompt") == "BLOCKED":
        logger.warning("[security] Grok 안전 차단: user=%s", user_id)
        await update.message.reply_text("_(허용되지 않는 내용이 포함되어 있습니다.)_", parse_mode="Markdown")
        return

    # ComfyUI 이미지 생성
    async def keep_uploading():
        while True:
            await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    # 선택된 모델
    model_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    selected_checkpoint = AVAILABLE_MODELS[model_key]["path"]

    upload_task = asyncio.create_task(keep_uploading())
    try:
        anchor_image = character.get("anchor_image", "") if character and isinstance(character, dict) and "anchor_image" in character else ""
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            anchor_image, orientation, skip_face,
            seed=user_seed,
            workflow_override=_HQ_WORKFLOW if use_hq else "",
            checkpoint_override=selected_checkpoint,
        )

        if image_path == "TIMEOUT":
            await update.message.reply_text("_(이미지 생성이 너무 오래 걸리고 있어요. 다시 시도해주세요.)_", parse_mode="Markdown")
        elif image_path == "QUEUE_FULL":
            await update.message.reply_text("_(이미지 요청이 많아서 지금은 생성할 수 없습니다.)_", parse_mode="Markdown")
        elif image_path:
            await _send_image_with_video_option(
                target_message=update.message,
                context=context,
                user_id=user_id,
                image_path=image_path,
                description=description,
                danbooru_tags=tags["pos_prompt"],
            )
            increment_usage(user_id, "images")
            increment_daily_images(user_id)
            # 세션 저장 — 다음 요청에서 수정 모드로 참조
            context.user_data["last_tags"] = tags["pos_prompt"]
            context.user_data["last_char_id"] = char_id
            context.user_data["last_character"] = character
            context.user_data["last_seed"] = src.comfyui.last_used_seed
            logger.info("이미지봇 생성 완료: user=%s", user_id)

            # 부분 수정 영구 적용 컨펌 메시지 (이미지 전송 직후)
            edit_confirm = context.user_data.pop("pending_edit_confirm", None)
            if edit_confirm:
                _FIELD_LABELS = {
                    "appearance_tags": "외형",
                    "clothing":        "의상",
                    "underwear":       "속옷",
                    "body_shape":      "체형",
                    "breast":          "가슴",
                }
                labels = ", ".join(_FIELD_LABELS.get(f, f) for f in edit_confirm["fields"])
                await update.message.reply_text(
                    f"✏️ `{edit_confirm['name']}` 영구 수정 완료: {labels}",
                    parse_mode="Markdown",
                )
        else:
            await update.message.reply_text("_(이미지 생성에 실패했습니다. 다시 시도해주세요.)_", parse_mode="Markdown")
    finally:
        upload_task.cancel()


async def random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎲 Random SFW 버튼 콜백 — trait_pools 랜덤 + Grok 태그 → ComfyUI."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = query.from_user.id
    data = query.data or ""
    if data != "random:sfw":
        return
    mode = "sfw"

    # 온보딩 체크
    if not is_onboarded(user_id):
        main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = "서비스 이용을 위해 먼저 메인봇에서 가입해주세요."
        if main_link:
            text += f"\n👉 {main_link}"
        await query.message.reply_text(text)
        return

    # Rate limiting
    allowed, _info = rate_limiter.check(user_id)
    if not allowed:
        await query.message.reply_text(
            "_(요청이 너무 빠릅니다. 잠시 후 다시 시도해주세요.)_",
            parse_mode="Markdown",
        )
        return

    # 이미지 한도 체크
    tier = get_user_tier(user_id)
    limit_msg = check_image_limit(user_id, tier)
    if limit_msg:
        await query.message.reply_text(limit_msg, parse_mode="Markdown")
        return

    # HQ 모드 — 세션 토글에서 읽음 + 실행 시점 재검증
    use_hq = bool(context.user_data.get("hq_mode", False))
    if use_hq and tier not in ("premium",) and not check_admin(user_id):
        context.user_data["hq_mode"] = False
        use_hq = False
        await query.message.reply_text(
            "_(고화질(HQ) 모드는 Premium 구독자 전용입니다. HQ OFF로 전환했습니다.)_",
            parse_mode="Markdown",
        )

    # ComfyUI 큐 체크
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        await query.message.reply_text(
            "_(이미지 요청이 많아서 지금은 생성할 수 없습니다. 잠시 후 다시 시도해주세요.)_",
            parse_mode="Markdown",
        )
        return

    # 1) trait_pools 랜덤 샘플링
    traits = roll_character(location="global")

    # 1-b) SFW 씬 타입 사전 선택 (Python → Grok)
    #     Grok이 포즈 목록에서 자율 선택 시 몇몇 포즈로 편향되는 문제를 제거하기 위해
    #     "씬 타입"을 Python에서 미리 고정한다.
    sfw_scene = roll_sfw_scene()
    logger.info(
        "이미지봇 SFW 씬 선택: user=%s key=%s label=%s",
        user_id, sfw_scene["key"], sfw_scene["label"],
    )

    # 2) Grok 랜덤 태그 생성
    async def keep_uploading():
        while True:
            await query.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    upload_task = asyncio.create_task(keep_uploading())
    try:
        tags = await generate_danbooru_tags_random(
            traits, mode, sfw_scene=sfw_scene
        )
    finally:
        upload_task.cancel()

    if tags.get("pos_prompt") == "BLOCKED":
        logger.warning("[security] Grok 랜덤 안전 차단: user=%s mode=%s", user_id, mode)
        await query.message.reply_text(
            "_(허용되지 않는 내용이 포함되어 있습니다.)_",
            parse_mode="Markdown",
        )
        return

    logger.info(
        "이미지봇 랜덤 Grok 태그 (user=%s mode=%s): pos=%s | neg=%s | orient=%s",
        user_id, mode, tags["pos_prompt"], tags["neg_prompt"], tags.get("orientation"),
    )

    # 3) ComfyUI 이미지 생성
    model_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    selected_checkpoint = AVAILABLE_MODELS[model_key]["path"]

    upload_task = asyncio.create_task(keep_uploading())
    try:
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)

        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            "",  # anchor_image 없음 — 랜덤 캐릭터는 고정 anchor 불필요
            orientation, skip_face,
            seed=0,
            workflow_override=_HQ_WORKFLOW if use_hq else "",
            checkpoint_override=selected_checkpoint,
        )

        if image_path == "TIMEOUT":
            await query.message.reply_text(
                "_(이미지 생성이 너무 오래 걸리고 있어요. 다시 시도해주세요.)_",
                parse_mode="Markdown",
            )
            return
        if image_path == "QUEUE_FULL":
            await query.message.reply_text(
                "_(이미지 요청이 많아서 지금은 생성할 수 없습니다.)_",
                parse_mode="Markdown",
            )
            return
        if not image_path:
            await query.message.reply_text(
                "_(이미지 생성에 실패했습니다. 다시 시도해주세요.)_",
                parse_mode="Markdown",
            )
            return

        # 4) 전송 (+ 🎬 버튼, Premium/Admin)
        scene_desc = tags.get("scene_description", "random_sfw")
        await _send_image_with_video_option(
            target_message=query.message,
            context=context,
            user_id=user_id,
            image_path=image_path,
            description=scene_desc,
            danbooru_tags=tags["pos_prompt"],
            extra_caption="🎲 랜덤 SFW",
            scene_key=sfw_scene.get("key") if sfw_scene else None,
        )

        increment_usage(user_id, "images")
        increment_daily_images(user_id)

        # 5) 세션 저장 — 이후 한글 수정은 기존 imagegen_message 플로우에서 처리
        # 외형 고정: SFW 태그(appearance + body IDENTITY)를 prefix로 저장.
        _dtags = traits.get("danbooru_tags", {}) if isinstance(traits, dict) else {}
        _sfw_appearance = (_dtags.get("appearance") or "").strip()
        _sfw_body = (_dtags.get("body") or "").strip()
        _sfw_clothing = (_dtags.get("clothing") or "").strip()

        # prefix = 고정 prefix + IDENTITY 태그 (appearance + body 실루엣).
        # 고정 prefix는 이미 "1girl"을 포함하므로, appearance에서 "1girl," 중복 제거.
        _sfw_appearance_clean = _sfw_appearance.replace("1girl, ", "").replace("1girl,", "")
        _identity_parts = [IMAGEGEN_FIXED_PREFIX] + [p for p in [_sfw_appearance_clean, _sfw_body] if p]
        _random_prefix = ", ".join(_identity_parts)

        # Grok이 생성한 resolved clothing (색 채움)이 있으면 세션에 덮어씀.
        # 없으면 원본 trait 유지 (fallback). Grok rule: 색 없는 item만 채우고 기존 색 item은 보존.
        _resolved_clothing = (tags.get("clothing_resolved") or "").strip()
        _final_sfw_clothing = _resolved_clothing if _resolved_clothing else _sfw_clothing

        random_character = {
            "name": "random",
            "image_prompt_prefix": _random_prefix,
            "image_negative_prefix": "",
            # 구조화 태그 블록 — generate_danbooru_tags가 씬 맥락에 따라 subset 선택
            "_random_sfw_tags": {
                "appearance": _sfw_appearance,
                "body": _sfw_body,
                "clothing": _final_sfw_clothing,  # ← Grok resolved (색 채움) or original
            },
            "_random_mode": mode,  # 초기 생성 모드 — 참고용
            "_random_clothing_original": _sfw_clothing,  # 디버그/롤백용 원본 보존
        } if _random_prefix else None

        context.user_data["last_tags"] = tags["pos_prompt"]
        context.user_data["last_char_id"] = ""
        context.user_data["last_character"] = random_character
        context.user_data["last_random_traits"] = traits
        context.user_data["last_seed"] = src.comfyui.last_used_seed
        context.user_data["last_random_mode"] = mode

        logger.info(
            "이미지봇 랜덤 생성 완료: user=%s mode=%s identity_prefix=%s "
            "clothing_resolved=%s (original=%s) seed=%s",
            user_id, mode,
            (_random_prefix[:80] if _random_prefix else "(none)"),
            (_final_sfw_clothing[:80] if _final_sfw_clothing else "(none)"),
            (_sfw_clothing[:40] if _sfw_clothing else "(none)"),
            src.comfyui.last_used_seed,
        )
    finally:
        upload_task.cancel()


async def _run_video_generation(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    target_message,
    user_id: int,
    image_path: str,
    description: str,
    danbooru_tags: str,
    motion_override: str | None,
    preferred_pose_key: str | None = None,
) -> bool:
    """영상 생성 공통 코어. 성공 시 비디오 전송 + 사용량 반영. 반환: 성공 여부.

    이미지 파일은 여기서 삭제하지 않는다 — 재시도/다른 모션 재사용을 위해 세션 수명에 맡김.
    """
    chat_id = target_message.chat_id

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
        from src.grok import generate_video_prompts
        try:
            prompts = await generate_video_prompts(
                description,
                image_path=image_path,
                chat_history=None,
                danbooru_tags=danbooru_tags,
                mood="neutral",
                motion_override=motion_override,
                preferred_pose_key=preferred_pose_key,
            )
        except Exception as e:
            logger.error("ImageGen Grok 비디오 프롬프트 실패: %s", e)
            prompts = {
                "motion_prompt": motion_override or description,
                "audio_prompt": "soft breath, intimate silence",
            }

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
                    logger.warning("VIDEO_DEBUG_DUMP 전송 실패 (imagegen): %s", _e)

        # Phase 2-B — Step 2 태그 추가 fallback 성공 기록 (모니터링용)
        if prompts.get("_csam_fallback_used"):
            logger.info("Grok Step 2 fallback 성공: user=%s", user_id)

        # motion_override 경로 명시적 차단 (유저 지정 모션이 CSAM 필터에 걸린 경우)
        # NOTE: 일반 🎬 경로는 grok이 BLOCKED 반환 시 동일하게 prompts_blocked 처리됨
        if prompts.get("motion_prompt") == "BLOCKED" or prompts.get("_csam_blocked"):
            prompts_blocked = True
            logger.warning("Grok 비디오 최종 차단: user=%s", user_id)
        else:
            try:
                await notify_admins_video(
                    context,
                    triggering_user_id=user_id,
                    source="imagegen",
                    char_id="imagegen",
                    status="started",
                    pose_key=prompts.get("_debug_pose_key_resolved", ""),
                    safety_level=prompts.get("_debug_safety_level", ""),
                    motion_prompt=prompts.get("motion_prompt", ""),
                    audio_prompt=prompts.get("audio_prompt", ""),
                )
            except Exception as _e:
                logger.warning("admin video notify (started) 실패: %s", _e)
            from src.video import generate_video
            video_path = await generate_video(
                image_path=image_path,
                motion_prompt=prompts["motion_prompt"],
                audio_prompt=prompts.get("audio_prompt", ""),
            )
    finally:
        upload_task.cancel()

    if prompts_blocked:
        # Grok 두 번 모두 차단 — 유저에게는 단일 에러만 전달 (카운트는 성공 시에만 증가하므로 변화 없음)
        await target_message.reply_text("😢 영상 생성이 제한됐어요. 다시 시도해 주세요.")
        logger.warning("이미지봇 비디오 Grok 차단: user=%s override=%s", user_id, bool(motion_override))
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                      char_id="imagegen", status="blocked",
                                      extra=f"motion_override={bool(motion_override)}")
        except Exception:
            pass
        return False

    if video_path:
        with open(video_path, "rb") as f:
            await target_message.reply_video(video=f)
        increment_usage(user_id, "videos")
        increment_daily_videos(user_id)
        try:
            os.unlink(video_path)
        except OSError:
            pass
        logger.info("이미지봇 비디오 생성 완료: user=%s override=%s", user_id, bool(motion_override))
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                      char_id="imagegen", status="success",
                                      pose_key=prompts.get("_debug_pose_key_resolved", ""))
        except Exception:
            pass
        return True

    await target_message.reply_text("😢 영상 생성에 실패했어요. 다시 시도해주세요.")
    logger.error("이미지봇 비디오 생성 실패: user=%s override=%s", user_id, bool(motion_override))
    try:
        await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                  char_id="imagegen", status="failed",
                                  extra=f"motion_override={bool(motion_override)} — check logs")
    except Exception:
        pass
    return False


async def imagegen_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎬 영상 생성 버튼 — 항상 Grok 자동 모션 (danbooru만)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    if not data.startswith("video:"):
        return

    ctx_id = data.split(":", 1)[1]
    ctx = get_video_context(ctx_id)
    if not ctx:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text("⏰ 영상 생성 시간이 만료되었어요.")
        return

    user_id = ctx["user_id"]
    tier = get_user_tier(user_id)

    if tier != "premium" and not check_admin(user_id):
        await query.message.reply_text("_(영상 생성은 Premium 구독자 전용입니다.)_", parse_mode="Markdown")
        return

    limit_msg = check_video_limit(user_id, tier)
    if limit_msg:
        await query.message.reply_text(limit_msg)
        return

    # 버튼 상태 → 생성 중
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏳ 영상 생성 중...", callback_data="noop")
        ]]))
    except Exception:
        pass

    ok = await _run_video_generation(
        context=context,
        target_message=query.message,
        user_id=user_id,
        image_path=ctx["image_path"],
        description=ctx["description"],
        danbooru_tags=ctx.get("danbooru_tags", ""),
        motion_override=None,  # 버튼은 항상 자동 모션
        preferred_pose_key=ctx.get("scene_key"),
    )

    if ok:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 영상 생성", callback_data=f"video:{ctx_id}"),
            ]]))
        except Exception:
            pass


async def imagegen_scene(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scene [key|off|list|status] — SFW 씬 강제 오버라이드 (Admin 전용 테스트용).

    - /scene list              — SFW 씬 key 나열
    - /scene status            — 현재 SFW 오버라이드 상태
    - /scene <sfw_key>         — 해당 SFW 씬으로 고정
    - /scene off / clear       — SFW 오버라이드 해제
    """
    if not check_admin(update.effective_user.id):
        return

    from src import trait_pools

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "list":
        sfw = trait_pools.list_sfw_scene_keys()
        text = (
            f"🌸 SFW Scene keys ({len(sfw)}):\n" + "\n".join(f"• {k}" for k in sfw)
        )
        await update.message.reply_text(text)
        return

    if subcmd in {"off", "clear", "none"}:
        ok, msg = trait_pools.set_forced_sfw_scene(None)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
        return

    if subcmd == "status":
        s_forced = trait_pools.get_forced_sfw_scene()
        if s_forced:
            line = f"🌸 SFW: `{s_forced}` 고정"
        else:
            line = "🌸 SFW: 랜덤"
        await update.message.reply_text(line + "\n\n(해제하려면 /scene off)")
        return

    # key 입력 — SFW 씬 key 적용
    key = args[0]
    sfw_keys = trait_pools.list_sfw_scene_keys()

    if key in sfw_keys:
        ok, msg = trait_pools.set_forced_sfw_scene(key)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
    else:
        await update.message.reply_text(
            f"❌ 알 수 없는 씬 key '{key}'.\n"
            f"SFW: {', '.join(sfw_keys[:5])}...\n"
            f"전체 목록: /scene list"
        )


# ═══════════════════════════════════════════════════════════════════════
# Saved Characters UI (Feature 1 Phase 1-B / 1-C)
# ═══════════════════════════════════════════════════════════════════════

_SAVE_NAME_PROMPT = (
    "💾 이 캐릭터를 저장합니다.\n\n"
    "이름을 입력해주세요 (영문/숫자/언더스코어, 1~20자).\n"
    "예: `minkyung`, `user_01`, `yerin_dress`\n\n"
    "취소하려면 /cancel 입력."
)


async def savechar_init_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💾 저장 버튼 클릭 — Grok 분류기로 nested 5-block split 후 이름 입력 대기 상태로 전환.

    /random과 custom 텍스트 모든 경로에서 last_tags blob을 그대로 Grok에 보내
    appearance_tags / clothing / underwear / body_shape{} / breast{} nested
    스키마로 통일 저장한다 (images/char*.json와 동일 구조).
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    last_tags = context.user_data.get("last_tags", "")
    if not last_tags:
        await query.message.reply_text("_(저장할 이미지가 없습니다. 먼저 이미지를 생성해주세요.)_", parse_mode="Markdown")
        return

    # 분류 진행 알림 (1~3초 소요)
    progress_msg = await query.message.reply_text("_(캐릭터 분석 중...)_", parse_mode="Markdown")

    try:
        nested = await classify_tags_to_nested_blocks(last_tags)
    except Exception as e:
        logger.error("classify_tags_to_nested_blocks 실패: user=%s err=%s", user_id, e)
        try:
            await progress_msg.edit_text("_(캐릭터 분석 실패. 다시 시도해주세요.)_", parse_mode="Markdown")
        except Exception:
            pass
        return

    # 모든 항목이 비었으면 저장 거부 (분류 실패) — flat str 3개 + nested dict 2개 모두 체크
    has_content = (
        (nested.get("appearance_tags") or "").strip()
        or (nested.get("clothing") or "").strip()
        or (nested.get("underwear") or "").strip()
        or any(nested.get("body_shape", {}).values())
        or any(nested.get("breast", {}).values())
    )
    if not has_content:
        try:
            await progress_msg.edit_text("_(캐릭터 분석 결과가 비어 있습니다. 다시 시도해주세요.)_", parse_mode="Markdown")
        except Exception:
            pass
        return

    base_pending = {
        "appearance_tags": (nested.get("appearance_tags") or "").strip(),
        "clothing":        (nested.get("clothing") or "").strip(),
        "underwear":       (nested.get("underwear") or "").strip(),
        "body_shape":      nested.get("body_shape") or {},
        "breast":          nested.get("breast") or {},
    }

    logger.info(
        "[savechar] Grok classify nested: user=%s "
        "appearance=%d clothing=%d underwear=%d body_shape_keys=%d breast_keys=%d",
        user_id,
        len(base_pending["appearance_tags"]),
        len(base_pending["clothing"]),
        len(base_pending["underwear"]),
        len([k for k, v in base_pending["body_shape"].items() if v]),
        len([k for k, v in base_pending["breast"].items() if v]),
    )

    # 분석 메시지 삭제
    try:
        await progress_msg.delete()
    except Exception:
        pass

    # 빈 슬롯 찾기
    available_slot = find_available_slot(user_id)
    if available_slot is not None:
        # 자동 할당
        context.user_data["pending_save"] = {**base_pending, "slot": available_slot}
        await query.message.reply_text(_SAVE_NAME_PROMPT, parse_mode="Markdown")
    else:
        # 슬롯 full — 덮어쓰기 선택
        chars = list_saved_characters(user_id)
        buttons = []
        for c in chars:
            buttons.append([InlineKeyboardButton(
                f"슬롯 {c['slot']}: {c['name']}", callback_data=f"savechar:slot:{c['slot']}"
            )])
        buttons.append([InlineKeyboardButton("❌ 취소", callback_data="savechar:cancel")])
        context.user_data["pending_save"] = {**base_pending, "slot": None}
        await query.message.reply_text(
            "슬롯이 모두 찼습니다. 어느 슬롯을 덮어쓸까요?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def savechar_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """슬롯 선택 (덮어쓰기) → 이름 입력 대기."""
    query = update.callback_query
    await query.answer()
    data = query.data  # "savechar:slot:1"
    slot = int(data.split(":")[-1])

    pending = context.user_data.get("pending_save")
    # nested 스키마 중 최소 appearance_tags가 있어야 유효
    if not pending or not pending.get("appearance_tags"):
        await query.message.reply_text("_(저장 세션이 만료되었습니다. 다시 시도해주세요.)_", parse_mode="Markdown")
        return
    pending["slot"] = slot  # 나머지 nested 키 보존
    context.user_data["pending_save"] = pending
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(_SAVE_NAME_PROMPT, parse_mode="Markdown")


async def savechar_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """저장 취소."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_save", None)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text("_(저장 취소됨.)_", parse_mode="Markdown")


async def imagegen_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel — pending 저장 상태 해제."""
    if context.user_data.pop("pending_save", None):
        await update.message.reply_text("_(저장 취소됨.)_", parse_mode="Markdown")
    else:
        await update.message.reply_text("_(진행 중인 작업이 없습니다.)_", parse_mode="Markdown")


async def imagegen_chars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chars — 저장된 캐릭터 목록."""
    user_id = update.effective_user.id
    chars = list_saved_characters(user_id)
    if not chars:
        await update.message.reply_text(
            "저장된 캐릭터가 없습니다.\n이미지 생성 후 💾 캐릭터 저장 버튼을 눌러 저장하세요."
        )
        return
    # 각 캐릭터에 삭제 버튼
    buttons = [
        [InlineKeyboardButton(f"🗑️ 슬롯 {c['slot']} ({c['name']}) 삭제",
                              callback_data=f"savechar:delete:{c['slot']}")]
        for c in chars
    ]
    await update.message.reply_text(
        _format_saved_chars_list(user_id),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def savechar_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🗑️ 슬롯 삭제 버튼."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    slot = int(query.data.split(":")[-1])
    ok = delete_saved_character(user_id, slot)
    if ok:
        await query.message.reply_text(f"_(슬롯 {slot} 캐릭터 삭제됨.)_", parse_mode="Markdown")
    else:
        await query.message.reply_text("_(삭제 실패 — 이미 비어있음.)_", parse_mode="Markdown")


async def _try_handle_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """pending_save 상태일 때 텍스트를 이름으로 처리. 처리됐으면 True."""
    pending = context.user_data.get("pending_save")
    # nested 스키마: appearance_tags 가 최소 채워져 있어야 유효
    if not pending or not pending.get("appearance_tags") or pending.get("slot") is None:
        return False

    user_id = update.effective_user.id
    name = (update.message.text or "").strip()

    if not is_valid_saved_char_name(name):
        await update.message.reply_text(
            "_(이름은 영문/숫자/언더스코어 1~20자만 가능합니다. 다시 입력해주세요.)_",
            parse_mode="Markdown",
        )
        return True

    # 이름 중복 체크 (같은 유저, 다른 슬롯)
    existing = get_saved_character_by_name(user_id, name)
    if existing and existing["slot"] != pending["slot"]:
        await update.message.reply_text(
            f"_(이름 `{name}`은 슬롯 {existing['slot']}에서 이미 사용 중입니다. 다른 이름으로 입력해주세요.)_",
            parse_mode="Markdown",
        )
        return True

    try:
        save_character(
            user_id=user_id,
            slot=pending["slot"],
            name=name,
            appearance_tags=pending.get("appearance_tags", ""),
            clothing=pending.get("clothing", ""),
            underwear=pending.get("underwear", ""),
            body_shape=pending.get("body_shape") or {},
            breast=pending.get("breast") or {},
        )
    except Exception as e:
        logger.error("save_character 실패: user=%s slot=%s name=%s err=%s", user_id, pending["slot"], name, e)
        await update.message.reply_text("_(저장 실패. 다시 시도해주세요.)_", parse_mode="Markdown")
        context.user_data.pop("pending_save", None)
        return True

    logger.info(
        "saved_character commit: user=%s slot=%s name=%s "
        "appearance=%d clothing=%d underwear=%d body_shape_keys=%d breast_keys=%d",
        user_id, pending["slot"], name,
        len(pending.get("appearance_tags", "")),
        len(pending.get("clothing", "")),
        len(pending.get("underwear", "")),
        len([k for k, v in (pending.get("body_shape") or {}).items() if v]),
        len([k for k, v in (pending.get("breast") or {}).items() if v]),
    )

    context.user_data.pop("pending_save", None)
    await update.message.reply_text(
        f"✅ 캐릭터 저장 완료!\n"
        f"슬롯 {pending['slot']}: `{name}`\n\n"
        f"다음부터 `@{name}`으로 호출할 수 있어요.\n"
        f"예: `@{name} 해변에서 비키니`",
        parse_mode="Markdown",
    )
    return True


def register_imagegen_handlers(app):
    """이미지 제네레이터 봇에 핸들러를 등록한다."""
    app.add_handler(CommandHandler("start", imagegen_start))
    app.add_handler(CommandHandler("help", imagegen_help))
    app.add_handler(CommandHandler("reset", imagegen_reset))
    app.add_handler(CommandHandler("seed", imagegen_seed))
    app.add_handler(CommandHandler("model", imagegen_model))
    app.add_handler(CommandHandler("hq", imagegen_hq))
    app.add_handler(CommandHandler("random", imagegen_random))
    app.add_handler(CommandHandler("scene", imagegen_scene))
    app.add_handler(CommandHandler("chars", imagegen_chars))
    app.add_handler(CommandHandler("cancel", imagegen_cancel))
    app.add_handler(CallbackQueryHandler(random_callback, pattern=r"^random:sfw$"))
    app.add_handler(CallbackQueryHandler(imagegen_video_callback, pattern=r"^video:"))
    app.add_handler(CallbackQueryHandler(savechar_init_callback, pattern=r"^savechar:init$"))
    app.add_handler(CallbackQueryHandler(savechar_slot_callback, pattern=r"^savechar:slot:[1-3]$"))
    app.add_handler(CallbackQueryHandler(savechar_cancel_callback, pattern=r"^savechar:cancel$"))
    app.add_handler(CallbackQueryHandler(savechar_delete_callback, pattern=r"^savechar:delete:[1-3]$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, imagegen_message))
