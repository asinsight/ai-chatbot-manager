"""
멀티봇 엔트리포인트.

하나의 프로세스에서 메인 봇(관리) + 캐릭터 봇(대화) N개를 동시 실행한다.
각 봇은 독립적인 Application 인스턴스를 갖고, bot_data로 설정을 구분한다.

환경변수:
  MAIN_BOT_TOKEN    — 메인 봇 토큰 (온보딩, 프로필, 관리)
  CHAR_BOT_{char_id} — 캐릭터 봇 토큰 (대화, 이미지)
"""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv
load_dotenv()  # 모듈 import 전에 .env 로드 (모듈 레벨 os.getenv 지원)

# ENV 기반 봇 토큰 해석: TEST_X 또는 PROD_X → X로 매핑
_ENV_PREFIX = os.getenv("ENV", "test").upper() + "_"
for _key in list(os.environ):
    if _key.startswith(_ENV_PREFIX):
        os.environ[_key[len(_ENV_PREFIX):]] = os.environ[_key]

from telegram.ext import ApplicationBuilder

from src.handlers_main import register_main_handlers
from src.handlers_char import register_char_handlers
from src.handlers_imagegen import register_imagegen_handlers
from src.history import init_db, set_admin
from src.prompt import load_all_characters, load_system_config
from src.logging_config import setup_logging
from src.llm_queue import llm_queue
from src.watchdog import notify_admins, comfyui_watchdog

setup_logging()
logger = logging.getLogger(__name__)


def _uncaught_exception_handler(exc_type, exc_value, exc_tb):
    """sys.excepthook — 프로세스 종료 전 미처리 예외 로깅."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


def _asyncio_exception_handler(loop, context):
    """asyncio 이벤트 루프 미처리 예외 핸들러."""
    msg = context.get("exception", context.get("message", "Unknown asyncio error"))
    logger.error("Asyncio exception: %s", msg)


async def main():
    # ── 예외 핸들러 설정 ──
    sys.excepthook = _uncaught_exception_handler
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)

    # ── DB 초기화 ──
    init_db()

    # ── LLM 큐 워커 시작 ──
    await llm_queue.start()

    # ── Admin 계정 등록 ──
    admin_ids = os.getenv("ADMIN_USER_IDS", "")
    for uid in admin_ids.split(","):
        uid = uid.strip()
        if uid:
            set_admin(int(uid), True)
            logger.info("Admin 등록: %s", uid)

    # ── 캐릭터 + 시스템 설정 로드 ──
    characters = load_all_characters()
    if not characters:
        raise SystemExit("persona/ 디렉토리에 캐릭터 JSON 파일이 없습니다.")
    logger.info("캐릭터 %d개 로드: %s", len(characters), ", ".join(characters.keys()))

    system_config = load_system_config()
    logger.info("마스터 시스템 프롬프트 로드 완료")

    # ── 봇 등록 ──
    apps: list[tuple[str, any]] = []  # (이름, Application) 쌍

    # 메인 봇
    main_token = os.getenv("MAIN_BOT_TOKEN")
    if main_token:
        main_app = ApplicationBuilder().token(main_token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
        main_app.bot_data["characters"] = characters
        main_app.bot_data["system_config"] = system_config
        register_main_handlers(main_app)
        apps.append(("main", main_app))
        logger.info("메인 봇 등록 완료")
    else:
        logger.warning("MAIN_BOT_TOKEN이 설정되지 않았습니다")

    # 캐릭터 봇 — char_id별로 CHAR_BOT_{char_id} 토큰 매핑
    for char_id, char_data in characters.items():
        token = os.getenv(f"CHAR_BOT_{char_id}")
        if not token:
            continue
        char_app = ApplicationBuilder().token(token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
        char_app.bot_data["char_id"] = char_id
        char_app.bot_data["character"] = char_data
        char_app.bot_data["characters"] = characters  # 전체 캐릭터 참조용
        char_app.bot_data["system_config"] = system_config
        register_char_handlers(char_app)
        apps.append((char_id, char_app))
        logger.info("캐릭터 봇 등록: %s (%s)", char_id, char_data.get("name", char_id))

    # 이미지 제네레이터 봇 — 캐릭터와 별도 등록
    imagegen_token = os.getenv("CHAR_BOT_imagegen")
    if imagegen_token:
        imagegen_app = ApplicationBuilder().token(imagegen_token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
        imagegen_app.bot_data["characters"] = characters
        imagegen_app.bot_data["system_config"] = system_config
        register_imagegen_handlers(imagegen_app)
        apps.append(("imagegen", imagegen_app))
        logger.info("이미지 제네레이터 봇 등록 완료")

    if not apps:
        raise SystemExit(
            "등록된 봇이 없습니다. "
            ".env에 MAIN_BOT_TOKEN 또는 CHAR_BOT_* 토큰을 설정하세요."
        )

    logger.info("총 %d개 봇 시작...", len(apps))

    # ── 모든 봇 초기화 + polling 시작 (non-blocking) ──
    for name, app in apps:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("봇 polling 시작: %s", name)

    logger.info("모든 봇 실행 중. Ctrl+C로 종료.")

    # ── Admin 시작 알림 + ComfyUI watchdog ──
    # 메인 봇의 bot 인스턴스를 알림용으로 사용
    main_bot = None
    for name, app in apps:
        if name == "main":
            main_bot = app.bot
            break
    if main_bot is None and apps:
        # 메인 봇이 없으면 첫 번째 봇 사용
        main_bot = apps[0][1].bot

    watchdog_task = None
    admin_notify = os.getenv("ADMIN_NOTIFY", "1") == "1"
    if main_bot:
        if admin_notify:
            try:
                await notify_admins(main_bot, "✅ 봇이 시작되었습니다.")
            except Exception as e:
                logger.error("Admin 시작 알림 실패: %s", e)
        watchdog_task = asyncio.create_task(comfyui_watchdog(main_bot))

    # ── 종료 시그널 대기 ──
    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # ── Graceful shutdown ──
    logger.info("봇 종료 중...")

    # watchdog 취소
    if watchdog_task is not None:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

    # Admin 종료 알림
    if main_bot and admin_notify:
        try:
            await notify_admins(main_bot, "⚠️ 봇이 종료됩니다.")
        except Exception as e:
            logger.error("Admin 종료 알림 실패: %s", e)

    await llm_queue.stop()
    for name, app in apps:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("봇 종료 완료: %s", name)

    logger.info("모든 봇 종료 완료.")


if __name__ == "__main__":
    asyncio.run(main())
