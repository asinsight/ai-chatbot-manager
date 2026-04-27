"""ComfyUI stuck 감지 + VRAM 모니터링 + Admin 알림 유틸리티."""
import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

# stuck 판정 시간 (초)
STUCK_TIMEOUT = int(os.getenv("COMFYUI_STUCK_TIMEOUT", "360"))
_CHECK_INTERVAL = 60  # 체크 간격

# VRAM 최소 여유량 (MB) — 이 아래로 떨어지면 경고
COMFYUI_VRAM_MIN_MB = int(os.getenv("COMFYUI_VRAM_MIN_MB", "20"))

# 큐 스냅샷 추적
_last_queue_change_time: float = 0.0
_last_running_count: int = 0
_last_pending_count: int = 0

# VRAM 경고 플래그 (스팸 방지)
_vram_alert_sent: bool = False


async def notify_admins(bot, message: str):
    """Admin 유저들에게 Telegram 메시지 전송."""
    admin_ids = os.getenv("ADMIN_USER_IDS", "")
    for uid in admin_ids.split(","):
        uid = uid.strip()
        if uid:
            try:
                await bot.send_message(chat_id=int(uid), text=message)
            except Exception as e:
                logger.error("Admin 알림 실패 (uid=%s): %s", uid, e)


async def notify_image_timeout(bot, user_id: int, username: str, char_id: str, char_name: str):
    """이미지 생성 6분 타임아웃 시 Admin에게 상세 알림."""
    from src.comfyui import check_queue
    queue = await check_queue()
    message = (
        f"⚠️ 이미지 생성 지연\n"
        f"유저: @{username} (ID: {user_id})\n"
        f"캐릭터: {char_id} ({char_name})\n"
        f"대기 시간: 6분+\n"
        f"ComfyUI 상태: Running: {queue['running']}, Pending: {queue['pending']}"
    )
    await notify_admins(bot, message)


async def check_vram() -> dict | None:
    """ComfyUI /system_stats에서 VRAM 정보 조회.

    Returns:
        VRAM 정보 dict 또는 실패 시 None.
        {
            "name": str,
            "vram_total": int,
            "vram_free": int,
            "torch_vram_total": int,
            "torch_vram_free": int,
        }
    """
    comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{comfyui_url}/system_stats")
            resp.raise_for_status()
            data = resp.json()
            devices = data.get("devices", [])
            if not devices:
                logger.warning("ComfyUI /system_stats: devices 목록이 비어있음")
                return None
            # 첫 번째 GPU 디바이스 사용
            device = devices[0]
            return {
                "name": device.get("name", "unknown"),
                "vram_total": device.get("vram_total", 0),
                "vram_free": device.get("vram_free", 0),
                "torch_vram_total": device.get("torch_vram_total", 0),
                "torch_vram_free": device.get("torch_vram_free", 0),
            }
    except Exception as e:
        logger.error("ComfyUI VRAM 조회 실패: %s", e)
        return None


async def comfyui_watchdog(bot):
    """ComfyUI stuck 감지 + VRAM 모니터링 워치독. 6분간 큐가 줄지 않으면 stuck 판정 + Admin 알림."""
    global _last_queue_change_time, _last_running_count, _last_pending_count, _vram_alert_sent

    from src.comfyui import check_queue
    _last_queue_change_time = time.time()

    while True:
        try:
            await asyncio.sleep(_CHECK_INTERVAL)
            queue = await check_queue()

            if queue.get("error"):
                # ComfyUI 자체가 다운 — 별도 처리 (systemd가 재시작)
                await notify_admins(bot, f"🔴 ComfyUI 연결 실패: {queue['error']}")
                _last_queue_change_time = time.time()
                continue

            running = queue["running"]
            pending = queue["pending"]

            # 큐 상태가 변했으면 타이머 리셋
            if running != _last_running_count or pending != _last_pending_count:
                _last_queue_change_time = time.time()
                _last_running_count = running
                _last_pending_count = pending

            # running > 0인데 6분간 큐 변화 없으면 stuck
            if running > 0 and (time.time() - _last_queue_change_time) >= STUCK_TIMEOUT:
                logger.error("ComfyUI stuck 감지: running=%d, pending=%d, 변화 없음 %d초",
                             running, pending, int(time.time() - _last_queue_change_time))
                await notify_admins(bot,
                    f"🔴 ComfyUI stuck 감지\n"
                    f"Running: {running}, Pending: {pending}\n"
                    f"큐 변화 없음: {int(time.time() - _last_queue_change_time)}초\n"
                    f"자동 재시작은 미구현 — 수동 확인 필요"
                )
                # 알림 후 타이머 리셋 (반복 알림 방지)
                _last_queue_change_time = time.time()

            # --- VRAM 모니터링 ---
            # 시스템 전체 free(vram_free) 기준으로 판단 — torch_vram_free는 PyTorch pool 내부
            # 여유이고 필요 시 pool이 dynamic 확장되므로 99% 차있어도 OOM 아님.
            # 특히 GB10 통합 메모리(128GB)에서는 torch pool 크기가 misleading.
            # COMFYUI_VRAM_MIN_MB=0이면 알림 비활성화.
            vram = await check_vram()
            if vram and COMFYUI_VRAM_MIN_MB > 0:
                sys_free = vram.get("vram_free", 0)
                sys_total = vram.get("vram_total", 0)
                torch_free = vram.get("torch_vram_free", 0)
                torch_total = vram.get("torch_vram_total", 0)
                threshold_bytes = COMFYUI_VRAM_MIN_MB * 1_000_000

                # 시스템 전체 free가 임계값 아래일 때만 경고 (torch pool fill-up은 정상)
                if sys_total > 0 and sys_free < threshold_bytes:
                    if not _vram_alert_sent:
                        sys_free_mb = sys_free / 1_000_000
                        sys_total_mb = sys_total / 1_000_000
                        torch_free_mb = torch_free / 1_000_000
                        torch_total_mb = torch_total / 1_000_000

                        logger.warning(
                            "ComfyUI VRAM 부족 (시스템): sys_free=%.0fMB (임계값=%dMB), "
                            "sys_total=%.0fMB, torch_pool=%.0f/%.0fMB",
                            sys_free_mb, COMFYUI_VRAM_MIN_MB, sys_total_mb,
                            torch_free_mb, torch_total_mb,
                        )
                        await notify_admins(bot,
                            f"⚠️ ComfyUI VRAM 부족 (시스템 레벨)\n"
                            f"시스템 free: {sys_free_mb:.0f}MB / {sys_total_mb:.0f}MB\n"
                            f"Torch pool: {torch_free_mb:.0f}MB / {torch_total_mb:.0f}MB (내부)\n"
                            f"임계값: {COMFYUI_VRAM_MIN_MB}MB\n"
                            f"디바이스: {vram['name']}"
                        )
                        _vram_alert_sent = True
                else:
                    # VRAM 회복 시 플래그 리셋
                    if _vram_alert_sent:
                        logger.info("ComfyUI VRAM 회복: sys_free=%.0fMB",
                                    sys_free / 1_000_000)
                        _vram_alert_sent = False

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("ComfyUI watchdog 에러: %s", e)
