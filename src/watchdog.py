"""ComfyUI stuck detection + VRAM monitoring + admin notification utilities."""
import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

# Stuck detection timeout (seconds)
STUCK_TIMEOUT = int(os.getenv("COMFYUI_STUCK_TIMEOUT", "360"))
_CHECK_INTERVAL = 60  # check interval

# Minimum free VRAM (MB); below this we warn
COMFYUI_VRAM_MIN_MB = int(os.getenv("COMFYUI_VRAM_MIN_MB", "20"))

# Queue snapshot tracking
_last_queue_change_time: float = 0.0
_last_running_count: int = 0
_last_pending_count: int = 0

# VRAM warning flag (suppress repeat alerts)
_vram_alert_sent: bool = False


async def notify_admins(bot, message: str):
    """Send a Telegram message to all admin users."""
    admin_ids = os.getenv("ADMIN_USER_IDS", "")
    for uid in admin_ids.split(","):
        uid = uid.strip()
        if uid:
            try:
                await bot.send_message(chat_id=int(uid), text=message)
            except Exception as e:
                logger.error("admin notify failed (uid=%s): %s", uid, e)


async def notify_image_timeout(bot, user_id: int, username: str, char_id: str, char_name: str):
    """Notify admins with details when image generation hits the 6-minute timeout."""
    from src.comfyui import check_queue
    queue = await check_queue()
    message = (
        f"⚠️ Image generation delay\n"
        f"User: @{username} (ID: {user_id})\n"
        f"Character: {char_id} ({char_name})\n"
        f"Wait: 6min+\n"
        f"ComfyUI status: Running: {queue['running']}, Pending: {queue['pending']}"
    )
    await notify_admins(bot, message)


async def check_vram() -> dict | None:
    """Query VRAM info from ComfyUI /system_stats.

    Returns:
        VRAM info dict, or None on failure.
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
                logger.warning("ComfyUI /system_stats: devices list is empty")
                return None
            # Use the first GPU device
            device = devices[0]
            return {
                "name": device.get("name", "unknown"),
                "vram_total": device.get("vram_total", 0),
                "vram_free": device.get("vram_free", 0),
                "torch_vram_total": device.get("torch_vram_total", 0),
                "torch_vram_free": device.get("torch_vram_free", 0),
            }
    except Exception as e:
        logger.error("ComfyUI VRAM query failed: %s", e)
        return None


async def comfyui_watchdog(bot):
    """ComfyUI stuck-detection + VRAM-monitoring watchdog. If the queue does not move for 6 minutes, it is declared stuck and admins are notified."""
    global _last_queue_change_time, _last_running_count, _last_pending_count, _vram_alert_sent

    from src.comfyui import check_queue
    _last_queue_change_time = time.time()

    while True:
        try:
            await asyncio.sleep(_CHECK_INTERVAL)
            queue = await check_queue()

            if queue.get("error"):
                # ComfyUI itself is down — handled separately (systemd restarts it)
                await notify_admins(bot, f"🔴 ComfyUI connection failed: {queue['error']}")
                _last_queue_change_time = time.time()
                continue

            running = queue["running"]
            pending = queue["pending"]

            # Queue state changed → reset the timer
            if running != _last_running_count or pending != _last_pending_count:
                _last_queue_change_time = time.time()
                _last_running_count = running
                _last_pending_count = pending

            # running > 0 with no queue change for 6 minutes → stuck
            if running > 0 and (time.time() - _last_queue_change_time) >= STUCK_TIMEOUT:
                logger.error("ComfyUI stuck detected: running=%d, pending=%d, no change for %ds",
                             running, pending, int(time.time() - _last_queue_change_time))
                await notify_admins(bot,
                    f"🔴 ComfyUI stuck detected\n"
                    f"Running: {running}, Pending: {pending}\n"
                    f"No queue change: {int(time.time() - _last_queue_change_time)}s\n"
                    f"Auto-restart not implemented — manual check needed"
                )
                # Reset timer after the alert (avoid repeat alerts)
                _last_queue_change_time = time.time()

            # --- VRAM monitoring ---
            # Decide based on the system-wide free VRAM (vram_free); torch_vram_free is
            # internal to the PyTorch pool and the pool grows dynamically on demand,
            # so 99% full there does not imply OOM. In particular, the GB10 unified-memory
            # setup (128GB) makes torch pool size misleading.
            # Setting COMFYUI_VRAM_MIN_MB=0 disables this alert.
            vram = await check_vram()
            if vram and COMFYUI_VRAM_MIN_MB > 0:
                sys_free = vram.get("vram_free", 0)
                sys_total = vram.get("vram_total", 0)
                torch_free = vram.get("torch_vram_free", 0)
                torch_total = vram.get("torch_vram_total", 0)
                threshold_bytes = COMFYUI_VRAM_MIN_MB * 1_000_000

                # Warn only when system-wide free is below the threshold (torch pool fill is normal)
                if sys_total > 0 and sys_free < threshold_bytes:
                    if not _vram_alert_sent:
                        sys_free_mb = sys_free / 1_000_000
                        sys_total_mb = sys_total / 1_000_000
                        torch_free_mb = torch_free / 1_000_000
                        torch_total_mb = torch_total / 1_000_000

                        logger.warning(
                            "ComfyUI VRAM low (system): sys_free=%.0fMB (threshold=%dMB), "
                            "sys_total=%.0fMB, torch_pool=%.0f/%.0fMB",
                            sys_free_mb, COMFYUI_VRAM_MIN_MB, sys_total_mb,
                            torch_free_mb, torch_total_mb,
                        )
                        await notify_admins(bot,
                            f"⚠️ ComfyUI VRAM low (system level)\n"
                            f"System free: {sys_free_mb:.0f}MB / {sys_total_mb:.0f}MB\n"
                            f"Torch pool: {torch_free_mb:.0f}MB / {torch_total_mb:.0f}MB (internal)\n"
                            f"Threshold: {COMFYUI_VRAM_MIN_MB}MB\n"
                            f"Device: {vram['name']}"
                        )
                        _vram_alert_sent = True
                else:
                    # VRAM recovered → reset the flag
                    if _vram_alert_sent:
                        logger.info("ComfyUI VRAM recovered: sys_free=%.0fMB",
                                    sys_free / 1_000_000)
                        _vram_alert_sent = False

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("ComfyUI watchdog error: %s", e)
