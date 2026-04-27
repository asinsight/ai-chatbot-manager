"""메인 봇 핸들러 — 온보딩, 프로필 관리, 관리자 커맨드.

대화/채팅 처리는 하지 않는다. 캐릭터 봇(handlers_char.py)에서 처리.
"""

import asyncio
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram import LabeledPrice
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

from src.history import get_full_profile, set_profile, set_user_tier, get_user_tier, get_usage, get_stats, _get_connection, is_onboarded, set_onboarded, save_payment, create_coupon, list_coupons, delete_coupon, redeem_coupon, delete_all_user_data
from src.handlers_common import check_admin
from src.rate_limiter import rate_limiter
from src.input_filter import check_regex, strip_signals
import src.comfyui as comfyui
import src.grok_search as grok_search

logger = logging.getLogger(__name__)
TOS_URL = "https://telegra.ph/Ella-AI-%EC%9D%B4%EC%9A%A9%EC%95%BD%EA%B4%80--Terms-of-Service-04-07"
PRIVACY_URL = "https://telegra.ph/Ella-AI-개인정보-처리방침--Privacy-Policy-04-09"

# 구독 상품 설정 (env로 조정 가능)
STANDARD_STARS = int(os.getenv("STANDARD_STARS", "250"))
STANDARD_DAYS = int(os.getenv("STANDARD_DAYS", "30"))
PREMIUM_STARS = int(os.getenv("PREMIUM_STARS", "700"))
PREMIUM_DAYS = int(os.getenv("PREMIUM_DAYS", "30"))


FREE_CHAR_IDS = [c.strip() for c in os.getenv("FREE_CHAR_IDS", "char06").split(",")]
FREE_MAX_TURNS = int(os.getenv("FREE_MAX_TURNS", "30"))


# 캐릭터 표시 순서 (persona에 profile_summary_ko가 없어도 이 순서로 나열)
# 일반(1~6) → char09 (박수연) → char10 (서유진) → 판타지/premium(7, 8) → 이미지 생성기
_CHAR_ORDER = ["char01", "char02", "char03", "char04", "char05", "char06", "char09", "char10", "char07", "char08", "imagegen"]

# imagegen은 persona 파일이 없으므로 메인 봇에서 직접 캡션 정의
_IMAGEGEN_SUMMARY = "🎨 이미지 생성기\n한글로 설명하면 AI가 이미지를 만들어줍니다. 캐릭터 이름을 넣으면 해당 캐릭터로 생성!"


def _get_char_summary(char_id: str, characters: dict) -> str | None:
    """캐릭터 한국어 프로필 소개를 가져온다. persona의 profile_summary_ko 우선, imagegen은 특수 처리."""
    if char_id == "imagegen":
        return _IMAGEGEN_SUMMARY
    cd = characters.get(char_id, {})
    summary = cd.get("profile_summary_ko")
    if summary:
        return summary
    # fallback: name + description 첫 줄
    name = cd.get("name", char_id)
    desc = (cd.get("description") or "").strip().split("\n")[0][:200]
    return f"{name}\n{desc}" if desc else name


def _build_character_descriptions(characters: dict) -> str:
    """등록된 캐릭터들의 한국어 소개 텍스트를 생성한다. (레거시)"""
    lines = []
    for char_id in characters:
        summary = _get_char_summary(char_id, characters)
        if not summary:
            continue
        lines.append(summary)
    return "\n\n".join(lines)


def _build_character_keyboard(characters: dict, tier: str = "free") -> InlineKeyboardMarkup | None:
    """캐릭터 봇 링크 인라인 키보드를 생성한다. Free 유저는 잠금 표시."""
    keyboard = []
    for char_id, char_data in characters.items():
        bot_username = os.getenv(f"CHAR_USERNAME_{char_id}", "")
        if not bot_username:
            continue
        name = char_data.get("name", char_id)

        if tier == "free":
            if char_id in FREE_CHAR_IDS:
                label = f"{name} (Free 하루 {FREE_MAX_TURNS}턴)"
                keyboard.append([InlineKeyboardButton(label, url=f"https://t.me/{bot_username}")])
            else:
                label = f"🔒 {name} (구독 필요)"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"locked_{char_id}")])
        else:
            keyboard.append([InlineKeyboardButton(name, url=f"https://t.me/{bot_username}")])

    # 이미지 생성기 버튼
    imagegen_username = os.getenv("CHAR_USERNAME_imagegen", "")
    if imagegen_username:
        keyboard.append([InlineKeyboardButton(
            "🎨 이미지 생성기", url=f"https://t.me/{imagegen_username}"
        )])

    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def _send_character_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, characters: dict, tier: str):
    """등록된 캐릭터별로 프로필 이미지 + 캡션 + 인라인 버튼을 개별 메시지로 전송한다."""
    project_root = Path(__file__).resolve().parents[1]

    # 노출 대상 캐릭터 목록 조립:
    # 1) _CHAR_ORDER 순서 유지 (char01~08, imagegen) — 등록된 것만
    # 2) 그 외 characters dict에 있고 CHAR_USERNAME이 설정된 캐릭터 (test 환경의 char_test 등)
    char_ids: list[str] = []
    seen: set[str] = set()
    for cid in _CHAR_ORDER:
        char_ids.append(cid)
        seen.add(cid)
    for cid in characters.keys():
        if cid in seen:
            continue
        if os.getenv(f"CHAR_USERNAME_{cid}", ""):
            char_ids.append(cid)
            seen.add(cid)

    for char_id in char_ids:
        # imagegen은 characters dict에 없어도 허용 (별도 봇이므로 username만 확인)
        if char_id != "imagegen" and char_id not in characters:
            continue

        bot_username = os.getenv(f"CHAR_USERNAME_{char_id}", "")

        # 캡션: persona의 profile_summary_ko (imagegen은 _IMAGEGEN_SUMMARY)
        summary = _get_char_summary(char_id, characters)

        # 캐릭터 메타 (이름 추출용)
        char_data = characters.get(char_id, {})
        name = char_data.get("name", char_id)

        # 인라인 버튼 조립
        button = None
        if tier == "free" and char_id not in FREE_CHAR_IDS and char_id != "imagegen":
            # Free 유저 잠금 상태 — 클릭 시 안내 콜백
            button = InlineKeyboardButton(
                f"🔒 {name} (구독 필요)",
                callback_data=f"locked_{char_id}",
            )
        else:
            if not bot_username:
                # username이 없으면 해당 캐릭터는 스킵
                continue
            if char_id == "imagegen":
                label = "🎨 이미지 생성 시작"
            elif tier == "free" and char_id in FREE_CHAR_IDS:
                label = f"💬 대화 시작 (Free 하루 {FREE_MAX_TURNS}턴)"
            else:
                label = "💬 대화 시작"
            button = InlineKeyboardButton(label, url=f"https://t.me/{bot_username}")

        reply_markup = InlineKeyboardMarkup([[button]])

        # 프로필 이미지 경로
        image_path = project_root / "images" / "profile" / f"{char_id}.png"

        try:
            if image_path.exists():
                with open(image_path, "rb") as f:
                    await update.effective_chat.send_photo(
                        photo=f,
                        caption=summary,
                        reply_markup=reply_markup,
                    )
            else:
                # 이미지가 없으면 텍스트로 fallback
                await update.effective_chat.send_message(summary, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("캐릭터 카드 전송 실패 (%s): %s", char_id, e)
            # 실패 시에도 텍스트로 최소 노출
            try:
                await update.effective_chat.send_message(summary, reply_markup=reply_markup)
            except Exception:
                pass

        # rate limit 회피
        await asyncio.sleep(0.3)


async def locked_char_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """잠긴 캐릭터 클릭 시 안내."""
    query = update.callback_query
    await query.answer("이 캐릭터는 프리미엄 구독이 필요합니다. / Premium subscription required.", show_alert=True)


async def main_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 커맨드 — 온보딩 게이트 + 환영 메시지 + 캐릭터 봇 링크."""
    user_id = update.effective_user.id

    # 온보딩 완료 → 환영 메시지
    if is_onboarded(user_id):
        await _send_welcome(update, context)
        return

    # 온보딩 게이트
    text = (
        "⚠️ 이 서비스는 19세 이상 이용 가능합니다.\n"
        "서비스를 이용하려면 아래에 동의해 주세요.\n\n"
        "⚠️ This service is for users aged 19 and above.\n"
        "Please agree to the terms below to continue.\n\n"
        "• 본 서비스는 AI 캐릭터 챗봇이며 성인 콘텐츠를 포함할 수 있습니다.\n"
        "• This service is an AI character chatbot that may contain adult content.\n\n"
        f"📋 이용약관 / Terms of Service:\n{TOS_URL}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 동의합니다 / I Agree", callback_data="onboard_agree"),
            InlineKeyboardButton("❌ 거부 / Decline", callback_data="onboard_decline"),
        ]
    ])
    await update.message.reply_text(text, reply_markup=keyboard)


async def _send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """온보딩 완료 유저에게 환영 메시지를 전송한다."""
    user_id = update.effective_user.id if update.effective_user else 0
    tier = get_user_tier(user_id)
    characters = context.bot_data.get("characters", {})
    text = (
        "안녕하세요! Ella AI 캐릭터 챗봇입니다.\n\n"
        "📋 사용 가능한 기능:\n"
        "/char — 캐릭터 선택\n"
        "/profile — 내 프로필 설정/조회\n"
        "/subscribe — 구독 (Standard / Premium)\n"
        "/redeem — 쿠폰 코드 사용\n"
        "/tier — 내 구독 상태\n"
        "/privacy — 개인정보 처리방침\n"
        "/deletedata — 내 데이터 삭제\n"
    )
    if check_admin(user_id):
        text += (
            "\n🔧 Admin:\n"
            "/admin — 관리 메뉴\n"
        )
    text += (
        "\n📩 캐릭터 제작 문의: ella.ai.project@gmail.com\n"
        "\n아래에서 캐릭터를 선택하세요 ⬇️\n"
    )
    await update.effective_chat.send_message(text)
    await _send_character_cards(update, context, characters, tier)


async def onboard_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """메인 봇 온보딩 동의/거부 콜백."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "onboard_agree":
        set_onboarded(user_id)
        logger.info("유저 %s 온보딩 동의 완료", user_id)
        await query.edit_message_text("✅ 동의 완료! / Agreed!")
        await _send_welcome(update, context)

    elif query.data == "onboard_decline":
        await query.edit_message_text(
            "동의하지 않으면 서비스를 이용할 수 없습니다.\n"
            "You cannot use this service without agreement.\n\n"
            "다시 시작하려면 /start를 입력하세요."
        )


async def char_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/char — 캐릭터 선택 메뉴. 티어에 따라 잠금/해금 표시."""
    user_id = update.effective_user.id
    characters = context.bot_data.get("characters", {})
    tier = get_user_tier(user_id)
    # Admin은 항상 전체 접근
    if check_admin(user_id):
        tier = "premium"
    if not characters:
        await update.message.reply_text("등록된 캐릭터 봇이 없습니다.")
        return
    await update.message.reply_text("캐릭터를 선택하세요:")
    await _send_character_cards(update, context, characters, tier)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/profile 커맨드 — 글로벌 유저 프로필 조회/설정. 자유 키 지원.

    메인 봇에서는 항상 글로벌 스코프로 동작한다.
    캐릭터별 프로필(nickname 등)은 캐릭터 봇에서 설정.
    """
    user_id = update.effective_user.id
    args = context.args if context.args else []

    # 인자 없으면 -> 프로필 조회
    if not args:
        profile = get_full_profile(user_id, "global")
        if not profile:
            await update.message.reply_text(
                "설정된 프로필이 없습니다.\n\n"
                "사용법: /profile 키 값\n"
                "예시: /profile name 준희\n"
                "/profile location 서울\n"
                "/profile favorite_team 토트넘"
            )
            return
        lines = []
        for key, data in profile.items():
            source_tag = " (auto)" if data["source"] == "auto" else ""
            lines.append(f"• {key}: {data['value']}{source_tag}")
        await update.message.reply_text("📋 프로필:\n" + "\n".join(lines))
        return

    # delete all -> 프로필 전체 삭제
    key = args[0].lower()
    if key == "delete" and len(args) > 1 and args[1].lower() == "all":
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM user_profile WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text("✅ 프로필이 전부 삭제되었습니다.")
        logger.info("유저 %s 프로필 전체 삭제", user_id)
        return

    # 프로필 설정 (자유 키)
    value = " ".join(args[1:]) if len(args) > 1 else ""

    if not value:
        await update.message.reply_text(f"사용법: /profile {key} 값\n전체 삭제: /profile delete all")
        return

    # 프로필 값 인젝션 방어
    value = strip_signals(value)
    blocked, pattern = check_regex(value)
    if blocked:
        logger.warning("[security] 프로필 인젝션 차단: user=%s key=%s value=%s", user_id, key, value[:100])
        await update.message.reply_text("프로필에 허용되지 않는 내용이 포함되어 있습니다.")
        return

    set_profile(user_id, "global", key, value, source="manual")
    await update.message.reply_text(f"✅ 글로벌 프로필 설정: {key} = {value}")
    logger.info("유저 %s 프로필 설정: %s=%s (scope=global)", user_id, key, value)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin — Admin 메뉴."""
    if not check_admin(update.effective_user.id):
        return
    text = (
        "🔧 Admin 메뉴:\n\n"
        "/premium <user_id> <days> — 유저 프리미엄 부여\n"
        "/tier <user_id> — 유저 티어 확인\n"
        "/stats — 전체 통계\n"
        "/blocked — 차단 유저 목록\n"
        "/unblock <user_id> — 차단 해제\n"
        "/coupon create|list|delete — 쿠폰 관리\n"
        "/refund <user_id> <charge_id> — 환불\n"
        "/balance — 봇 Stars 잔액 조회\n"
        "/withdraw — Stars 인출 (Fragment.com)\n"
        "/runpod on|off|status — RunPod 관리\n"
        "/runpod_video on|off|status — RunPod 비디오 관리"
    )
    await update.message.reply_text(text)


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/premium <user_id> <days> — 유저에게 프리미엄 부여."""
    if not check_admin(update.effective_user.id):
        return
    args = context.args or []
    if len(args) < 1:
        await update.message.reply_text("사용법: /premium <user_id> [days]\n기본 30일")
        return
    target_id = int(args[0])
    days = int(args[1]) if len(args) > 1 else 30
    set_user_tier(target_id, "premium", days)
    await update.message.reply_text(f"✅ 유저 {target_id} → premium ({days}일)")
    logger.info("Admin이 유저 %s에게 premium %d일 부여", target_id, days)


async def tier_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/tier [user_id] — 티어 확인."""
    args = context.args or []
    if args and check_admin(update.effective_user.id):
        target_id = int(args[0])
    else:
        target_id = update.effective_user.id
    tier = get_user_tier(target_id)
    usage = get_usage(target_id)
    text = (
        f"👤 유저: {target_id}\n"
        f"📊 티어: {tier}\n"
        f"💬 이번 달 대화: {usage['turns']}턴\n"
        f"🖼 이번 달 이미지: {usage['images']}장\n"
        f"🎬 이번 달 동영상: {usage['videos']}개"
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — 전체 통계 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    stats = get_stats()
    tier_lines = [f"  {t}: {c}명" for t, c in stats["tier_counts"].items()]
    text = (
        f"📊 전체 통계:\n\n"
        f"👥 총 유저: {stats['total_users']}명\n"
        f"📋 티어별:\n" + "\n".join(tier_lines) + "\n"
        f"💳 총 결제: {stats['total_payments']}건"
    )
    await update.message.reply_text(text)


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unblock <user_id> — 유저 차단 해제 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("사용법: /unblock <user_id>")
        return
    target_id = int(args[0])
    if rate_limiter.unblock(target_id):
        await update.message.reply_text(f"✅ 유저 {target_id} 차단 해제 완료")
    else:
        await update.message.reply_text(f"유저 {target_id}는 차단 중이 아닙니다.")


async def blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/blocked — 현재 차단 중인 유저 목록 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    blocked = rate_limiter.get_blocked_users()
    if not blocked:
        await update.message.reply_text("현재 차단 중인 유저가 없습니다.")
        return
    lines = []
    for entry in blocked:
        mins = int(entry["remaining"] // 60)
        secs = int(entry["remaining"] % 60)
        lines.append(f"• user {entry['user_id']} — {mins}분 {secs}초 남음")
    text = f"🚫 차단 유저: {len(blocked)}명\n\n" + "\n".join(lines)
    await update.message.reply_text(text)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/subscribe — 구독 상품 선택."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"Standard — {STANDARD_STARS} Stars / {STANDARD_DAYS}일",
            callback_data="buy_standard",
        )],
        [InlineKeyboardButton(
            f"Premium — {PREMIUM_STARS} Stars / {PREMIUM_DAYS}일",
            callback_data="buy_premium",
        )],
    ])
    text = (
        "📋 구독 상품을 선택하세요:\n\n"
        f"⭐ Standard ({STANDARD_STARS} Stars)\n"
        "  • 전체 캐릭터 오픈\n"
        "  • 무제한 대화\n"
        f"  • 이미지 {os.getenv('STANDARD_MAX_IMAGES', '30')}장/월, {os.getenv('STANDARD_DAILY_IMAGES', '5')}장/일\n\n"
        f"💎 Premium ({PREMIUM_STARS} Stars)\n"
        "  • 전체 캐릭터 오픈\n"
        "  • 무제한 대화\n"
        f"  • 이미지 {os.getenv('PREMIUM_MAX_IMAGES', '60')}장/월, {os.getenv('PREMIUM_DAILY_IMAGES', '10')}장/일\n"
        "  • 우선 응답"
    )
    await update.message.reply_text(text, reply_markup=keyboard)


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """구독 구매 콜백 — send_invoice 호출."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_standard":
        title = f"Standard Subscription ({STANDARD_DAYS} days)"
        description = "All characters, unlimited chat, monthly image quota"
        amount = STANDARD_STARS
        payload = f"sub_standard_{user_id}"
    elif query.data == "buy_premium":
        title = f"Premium Subscription ({PREMIUM_DAYS} days)"
        description = "All characters, unlimited chat, unlimited images, priority response"
        amount = PREMIUM_STARS
        payload = f"sub_premium_{user_id}"
    else:
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(title, amount)],
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PreCheckoutQuery — 10초 내 응답 필수."""
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("sub_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Invalid payment. Please try again.")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """결제 성공 — 티어 변경 + DB 저장."""
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    charge_id = payment.telegram_payment_charge_id
    amount = payment.total_amount

    # payload에서 plan 파싱
    parts = payment.invoice_payload.split("_")
    plan = parts[1] if len(parts) >= 2 else "unknown"

    if plan == "standard":
        days = STANDARD_DAYS
    elif plan == "premium":
        days = PREMIUM_DAYS
    else:
        days = 30

    # DB 저장 + 티어 변경
    save_payment(user_id, amount, plan, days, charge_id)
    set_user_tier(user_id, plan, days)

    logger.info("결제 성공: user=%s plan=%s stars=%d days=%d charge=%s",
                user_id, plan, amount, days, charge_id)

    await update.message.reply_text(
        f"✅ 결제 완료! {amount} Stars\n"
        f"📋 플랜: {plan.capitalize()} ({days}일)\n\n"
        "감사합니다! 모든 기능이 활성화되었습니다."
    )


async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/refund <user_id> <charge_id> — 환불 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("사용법: /refund <user_id> <telegram_charge_id>")
        return
    target_id = int(args[0])
    charge_id = args[1]
    try:
        await context.bot.refund_star_payment(
            user_id=target_id,
            telegram_payment_charge_id=charge_id,
        )
        await update.message.reply_text(f"✅ 환불 완료: user={target_id}")
        logger.info("환불 완료: user=%s charge=%s", target_id, charge_id)
    except Exception as e:
        await update.message.reply_text(f"환불 실패: {e}")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/balance — 봇 Stars 잔액 조회 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    try:
        result = await context.bot.get_star_transactions(limit=100)
        total = 0
        for t in result.transactions:
            if hasattr(t, "source") and t.source:
                total += t.amount  # 수입
            elif hasattr(t, "receiver") and t.receiver:
                total -= t.amount  # 환불/출금
        await update.message.reply_text(
            f"⭐ 봇 Stars 잔액: {total} Stars\n"
            f"📋 총 거래 수: {len(result.transactions)}건"
        )
    except Exception as e:
        await update.message.reply_text(f"잔액 조회 실패: {e}")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/withdraw — Stars 인출 URL 생성 (Admin 전용).

    주의: 최소 1,000 Stars + 수령 후 21일 경과 필요.
    """
    if not check_admin(update.effective_user.id):
        return
    try:
        # getStarRevenueWithdrawalUrl은 아직 python-telegram-bot에 없을 수 있음
        # 직접 API 호출
        import httpx
        bot_token = context.bot.token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/getStarRevenueWithdrawalUrl",
                json={"user_id": update.effective_user.id},
            )
            data = resp.json()
            if data.get("ok"):
                url = data["result"]["url"]
                await update.message.reply_text(f"⭐ Stars 인출 페이지:\n{url}")
            else:
                error = data.get("description", "Unknown error")
                await update.message.reply_text(f"인출 불가: {error}")
    except Exception as e:
        await update.message.reply_text(f"인출 요청 실패: {e}")
        logger.error("Stars 인출 요청 실패: %s", e)


async def coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/coupon create|list|delete — 쿠폰 관리 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "사용법:\n"
            "/coupon create <code> <tier> <days> [max_uses]\n"
            "/coupon list\n"
            "/coupon delete <code>"
        )
        return

    sub = args[0].lower()

    if sub == "create":
        if len(args) < 4:
            await update.message.reply_text("사용법: /coupon create <code> <tier> <days> [max_uses]")
            return
        code = args[1].upper()
        tier = args[2].lower()
        if tier not in ("standard", "premium"):
            await update.message.reply_text("tier는 standard 또는 premium만 가능합니다.")
            return
        days = int(args[3])
        max_uses = int(args[4]) if len(args) > 4 else 0
        try:
            create_coupon(code, tier, days, max_uses)
            max_text = f"최대 {max_uses}회" if max_uses > 0 else "무제한"
            await update.message.reply_text(
                f"✅ 쿠폰 생성 완료\n"
                f"코드: {code}\n"
                f"티어: {tier} / {days}일\n"
                f"사용: {max_text}"
            )
            logger.info("쿠폰 생성: code=%s tier=%s days=%d max=%d", code, tier, days, max_uses)
        except Exception as e:
            await update.message.reply_text(f"쿠폰 생성 실패: {e}")

    elif sub == "list":
        coupons = list_coupons()
        if not coupons:
            await update.message.reply_text("등록된 쿠폰이 없습니다.")
            return
        lines = []
        for c in coupons:
            max_text = f"{c['used_count']}/{c['max_uses']}" if c["max_uses"] > 0 else f"{c['used_count']}/∞"
            exp = c["expires_at"] or "없음"
            lines.append(f"• {c['code']} — {c['tier']} {c['days']}일 ({max_text}) 만료: {exp}")
        await update.message.reply_text("📋 쿠폰 목록:\n\n" + "\n".join(lines))

    elif sub == "delete":
        if len(args) < 2:
            await update.message.reply_text("사용법: /coupon delete <code>")
            return
        code = args[1].upper()
        if delete_coupon(code):
            await update.message.reply_text(f"✅ 쿠폰 {code} 삭제 완료")
            logger.info("쿠폰 삭제: code=%s", code)
        else:
            await update.message.reply_text(f"쿠폰 {code}를 찾을 수 없습니다.")

    else:
        await update.message.reply_text("사용법: /coupon create|list|delete")


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/redeem <code> — 쿠폰 코드 사용."""
    user_id = update.effective_user.id

    # 온보딩 체크
    if not is_onboarded(user_id):
        await update.message.reply_text("먼저 /start로 서비스에 가입해주세요.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("사용법: /redeem <쿠폰코드>")
        return

    code = args[0].upper()
    success, message = redeem_coupon(code, user_id)

    if success:
        await update.message.reply_text(f"✅ 쿠폰 적용! {message}")
        logger.info("쿠폰 사용: user=%s code=%s result=%s", user_id, code, message)
    else:
        await update.message.reply_text(f"❌ {message}")
        logger.info("쿠폰 사용 실패: user=%s code=%s reason=%s", user_id, code, message)


async def deletedata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deletedata — 개인정보 삭제 요청."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 삭제합니다", callback_data="deletedata_confirm"),
            InlineKeyboardButton("❌ 취소", callback_data="deletedata_cancel"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ 정말 모든 데이터를 삭제하시겠습니까?\n\n"
        "삭제되는 항목:\n"
        "• 모든 대화 히스토리\n"
        "• 대화 요약\n"
        "• 유저 프로필\n"
        "• 장기 기억 (관계, 이벤트)\n"
        "• 의상 설정\n"
        "• 사용량 기록\n"
        "• 계정 설정 (온보딩 초기화)\n\n"
        "⚠️ 이 작업은 되돌릴 수 없습니다.\n"
        "결제 기록은 법적 보관 의무에 따라 보존됩니다.",
        reply_markup=keyboard,
    )


async def deletedata_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """개인정보 삭제 확인/취소 콜백."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "deletedata_confirm":
        deleted = delete_all_user_data(user_id)
        total = sum(deleted.values())
        logger.info("유저 %s 데이터 삭제 완료: %s (총 %d행)", user_id, deleted, total)
        await query.edit_message_text(
            "✅ 모든 데이터가 삭제되었습니다.\n\n"
            "서비스를 다시 이용하시려면 /start로 재가입해주세요."
        )
    elif query.data == "deletedata_cancel":
        await query.edit_message_text("취소되었습니다. 데이터는 그대로 유지됩니다.")


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/privacy — 개인정보 처리방침."""
    await update.message.reply_text(
        f"📋 개인정보 처리방침 / Privacy Policy:\n{PRIVACY_URL}\n\n"
        "데이터 삭제를 원하시면 /deletedata를 입력해주세요."
    )


async def runpod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runpod on|off|status — RunPod Serverless 관리 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        # 1. workersMin=1 설정
        await update.message.reply_text("RunPod 워커 시작 중...")
        result = await comfyui.set_runpod_workers(1)
        if "error" in result:
            await update.message.reply_text(f"RunPod workersMin 설정 실패: {result['error']}")
            return

        # 2. 워커 준비 대기 (최대 30초, 5초 간격 폴링)
        comfyui.runpod_enabled = True
        ready = False
        for _ in range(6):
            await asyncio.sleep(5)
            health = await comfyui.check_runpod_health()
            workers = health.get("workers", {})
            workers_ready = workers.get("ready", 0) + workers.get("idle", 0) + workers.get("running", 0)
            if workers_ready > 0:
                ready = True
                break

        if ready:
            await update.message.reply_text(
                f"✅ RunPod ON — 워커 준비 완료\n"
                f"Workers: ready={workers.get('ready', 0)}, idle={workers.get('idle', 0)}, running={workers.get('running', 0)}"
            )
        else:
            health = await comfyui.check_runpod_health()
            await update.message.reply_text(
                f"⚠️ RunPod ON — 활성화했으나 워커 아직 준비 안 됨 (cold start 중)\n"
                f"Health: {health}\n"
                f"잠시 후 /runpod status로 확인하세요."
            )

    elif subcmd == "off":
        comfyui.runpod_enabled = False
        result = await comfyui.set_runpod_workers(0)
        if "error" in result:
            await update.message.reply_text(
                f"RunPod 비활성화 완료 (라우팅 OFF)\n"
                f"⚠️ workersMin=0 설정 실패: {result['error']}"
            )
        else:
            await update.message.reply_text("✅ RunPod OFF — 라우팅 비활성화 + workersMin=0")

    else:
        # status (기본)
        enabled_str = "ON ✅" if comfyui.runpod_enabled else "OFF ❌"
        health = await comfyui.check_runpod_health()
        local_queue = await comfyui.check_queue()

        if "error" in health:
            runpod_status = f"Error: {health['error']}"
        else:
            workers = health.get("workers", {})
            jobs = health.get("jobs", {})
            runpod_status = (
                f"Workers — ready: {workers.get('ready', 0)}, idle: {workers.get('idle', 0)}, "
                f"running: {workers.get('running', 0)}, throttled: {workers.get('throttled', 0)}\n"
                f"Jobs — inQueue: {jobs.get('inQueue', 0)}, inProgress: {jobs.get('inProgress', 0)}, "
                f"completed: {jobs.get('completed', 0)}, failed: {jobs.get('failed', 0)}"
            )

        text = (
            f"🖥 RunPod 상태\n"
            f"라우팅: {enabled_str}\n"
            f"Endpoint: {comfyui.RUNPOD_ENDPOINT_ID or '(미설정)'}\n"
            f"Max Queue: {comfyui.RUNPOD_MAX_QUEUE}\n\n"
            f"📡 RunPod Health:\n{runpod_status}\n\n"
            f"🏠 GB10 로컬 ComfyUI:\n"
            f"Running: {local_queue.get('running', '?')}, Pending: {local_queue.get('pending', '?')}"
        )
        await update.message.reply_text(text)


async def runpod_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runpod_video on|off|status — RunPod 비디오 Serverless 관리 (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        await update.message.reply_text("RunPod Video 워커 시작 중... (cold start S3 다운로드 ~3-5분)")
        # workersMin=1로 active worker 강제 (running 상태 진입 + S3 모델 다운로드 트리거)
        result = await comfyui.set_runpod_video_workers(1, comfyui.RUNPOD_VIDEO_MAX_WORKERS)
        if "error" in result:
            await update.message.reply_text(f"RunPod Video 설정 실패: {result['error']}")
            return

        comfyui.runpod_video_enabled = True
        # 워커 running 상태 대기 (최대 5분, 10초 간격 폴링)
        running = False
        for _ in range(30):
            await asyncio.sleep(10)
            health = await comfyui.check_runpod_video_health()
            workers = health.get("workers", {})
            if workers.get("running", 0) > 0 or workers.get("ready", 0) > 0:
                running = True
                break

        if running:
            await update.message.reply_text(
                f"✅ RunPod Video ON — 워커 active\n"
                f"Workers: running={workers.get('running', 0)}, ready={workers.get('ready', 0)}, "
                f"idle={workers.get('idle', 0)}, initializing={workers.get('initializing', 0)}"
            )
        else:
            health = await comfyui.check_runpod_video_health()
            await update.message.reply_text(
                f"⚠️ RunPod Video ON — 활성화했으나 5분 내 워커 ready 안 됨 (S3 다운로드 지연 가능)\n"
                f"Health: {health}\n"
                f"잠시 후 /runpod_video status로 확인하세요."
            )

    elif subcmd == "off":
        comfyui.runpod_video_enabled = False
        result = await comfyui.set_runpod_video_workers(0, 0)
        if "error" in result:
            await update.message.reply_text(
                f"RunPod Video 비활성화 완료 (라우팅 OFF)\n"
                f"⚠️ workers 설정 실패: {result['error']}"
            )
        else:
            await update.message.reply_text("✅ RunPod Video OFF — 라우팅 비활성화 + workers=0")

    else:
        # status (기본)
        enabled_str = "ON ✅" if comfyui.runpod_video_enabled else "OFF ❌"
        health = await comfyui.check_runpod_video_health()

        if "error" in health:
            runpod_status = f"Error: {health['error']}"
        else:
            workers = health.get("workers", {})
            jobs = health.get("jobs", {})
            runpod_status = (
                f"Workers — ready: {workers.get('ready', 0)}, idle: {workers.get('idle', 0)}, "
                f"running: {workers.get('running', 0)}, throttled: {workers.get('throttled', 0)}\n"
                f"Jobs — inQueue: {jobs.get('inQueue', 0)}, inProgress: {jobs.get('inProgress', 0)}, "
                f"completed: {jobs.get('completed', 0)}, failed: {jobs.get('failed', 0)}"
            )

        text = (
            f"🎬 RunPod Video 상태\n"
            f"라우팅: {enabled_str}\n"
            f"Endpoint: {comfyui.RUNPOD_VIDEO_ENDPOINT_ID or '(미설정)'}\n"
            f"Max Workers: {comfyui.RUNPOD_VIDEO_MAX_WORKERS}\n\n"
            f"📡 Health:\n{runpod_status}"
        )
        await update.message.reply_text(text)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/search on|off|status — Grok 인터넷 검색 on/off (Admin 전용)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        grok_search.GROK_SEARCH_ENABLED = True
        await update.message.reply_text("✅ Grok Search ON — 캐릭터 인터넷 검색 활성화")

    elif subcmd == "off":
        grok_search.GROK_SEARCH_ENABLED = False
        await update.message.reply_text("✅ Grok Search OFF — 캐릭터 인터넷 검색 비활성화")

    else:
        enabled_str = "ON ✅" if grok_search.GROK_SEARCH_ENABLED else "OFF ❌"
        month = grok_search._now_month()
        monthly_used = grok_search._monthly_count.get(month, 0)
        monthly_limit = grok_search.GROK_SEARCH_MONTHLY_LIMIT
        cache_size = len(grok_search._search_cache)

        text = (
            f"🔍 Grok Search 상태\n"
            f"검색: {enabled_str}\n"
            f"월간 사용: {monthly_used}/{monthly_limit} ({month})\n"
            f"캐시: {cache_size}개\n"
            f"제외 캐릭터: {os.getenv('SEARCH_EXCLUDED_CHARS', 'char07,char08')}"
        )
        await update.message.reply_text(text)


async def scene_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scene [key|off|list|status] — SFW 씬 강제 오버라이드 (Admin 전용 테스트용).

    씬 key가 SFW_SCENES에 있으면 SFW override로 고정한다.

    - /scene list              — SFW 씬 key 나열
    - /scene status            — 현재 오버라이드 상태
    - /scene <sfw_key>         — 해당 SFW 씬으로 고정
    - /scene off / clear       — 오버라이드 해제
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
        lines = []
        lines.append(f"🌸 SFW: `{s_forced}` 고정" if s_forced else "🌸 SFW: 랜덤")
        lines.append("\n(해제하려면 /scene off)")
        await update.message.reply_text("\n".join(lines))
        return

    key = args[0]
    sfw_keys = trait_pools.list_sfw_scene_keys()

    if key in sfw_keys:
        ok, msg = trait_pools.set_forced_sfw_scene(key)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
    else:
        await update.message.reply_text(
            f"❌ 알 수 없는 씬 key '{key}'. /scene list 로 확인."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — 커맨드 목록."""
    user_id = update.effective_user.id if update.effective_user else 0
    text = (
        "📋 커맨드 목록:\n\n"
        "/start — 서비스 시작\n"
        "/char — 캐릭터 선택\n"
        "/profile — 내 프로필 설정/조회\n"
        "/subscribe — 구독 (Standard / Premium)\n"
        "/redeem — 쿠폰 코드 사용\n"
        "/tier — 내 구독 상태\n"
        "/privacy — 개인정보 처리방침\n"
        "/deletedata — 내 데이터 삭제\n"
        "/help — 도움말\n"
    )
    if check_admin(user_id):
        text += (
            "\n🔧 Admin:\n"
            "/admin — 관리 메뉴\n"
        )
    text += "\n📩 문의: ella.ai.project@gmail.com"
    await update.message.reply_text(text)


def register_main_handlers(app):
    """메인 봇에 핸들러를 등록한다."""
    app.add_handler(CommandHandler("start", main_start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(onboard_main_callback, pattern="^onboard_"))
    app.add_handler(CommandHandler("char", char_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("tier", tier_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("blocked", blocked_command))
    app.add_handler(CommandHandler("unblock", unblock_command))
    app.add_handler(CallbackQueryHandler(locked_char_callback, pattern="^locked_"))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CommandHandler("refund", refund_command))
    app.add_handler(CommandHandler("coupon", coupon_command))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("deletedata", deletedata_command))
    app.add_handler(CallbackQueryHandler(deletedata_callback, pattern="^deletedata_"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("runpod", runpod_command))
    app.add_handler(CommandHandler("runpod_video", runpod_video_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("scene", scene_command))
