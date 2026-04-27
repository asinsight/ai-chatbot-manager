"""비디오 생성 모듈 — AtlasCloud i2v 래퍼.

wan26/wan26-flash/seedance: 네이티브 오디오 (generate_audio=true)
"""

import logging
import os

logger = logging.getLogger(__name__)

# .env에서 비디오 설정 읽기
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "alibaba/wan-2.6/image-to-video-flash")
VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "480p")
VIDEO_DURATION = int(os.getenv("VIDEO_DURATION", "5"))

# 네이티브 오디오 지원 모델 — 이 모델들만 audio_prompt를 전달
_NATIVE_AUDIO_MODELS = {
    "alibaba/wan-2.6/image-to-video",
    "alibaba/wan-2.6/image-to-video-flash",
    "alibaba/wan-2.7/image-to-video",
    "bytedance/seedance-v1.5-pro/image-to-video-spicy",
}

# AtlasCloudClient — ATLASCLOUD_API_KEY 환경변수 필요
_client = None


def _get_client():
    """클라이언트를 lazy init한다 (ATLASCLOUD_API_KEY 없으면 None)."""
    global _client
    if _client is not None:
        return _client
    try:
        from atlascloud import AtlasCloudClient
        _client = AtlasCloudClient()
        logger.info("AtlasCloud client initialized (model=%s, res=%s, dur=%ds)",
                     VIDEO_MODEL, VIDEO_RESOLUTION, VIDEO_DURATION)
        return _client
    except Exception as e:
        logger.warning("AtlasCloud client init failed: %s", e)
        return None


async def generate_video(
    image_path: str,
    motion_prompt: str,
    audio_prompt: str = "",
) -> str | None:
    """이미지 → 비디오 생성 (오디오 포함).

    - wan26/wan26-flash/seedance: 네이티브 오디오
    - 비디오 길이는 .env VIDEO_DURATION으로 고정 제어

    Args:
        image_path: 입력 이미지 경로.
        motion_prompt: Composer가 만든 motion 프롬프트.
        audio_prompt: Composer가 만든 audio 프롬프트 (native audio 모델만 사용).

    성공 시 로컬 파일 경로 반환, 실패 시 None.
    """
    client = _get_client()
    if not client:
        logger.error("AtlasCloud client not available")
        return None

    effective_model = VIDEO_MODEL
    # 네이티브 오디오 모델 감지
    effective_audio = audio_prompt if effective_model in _NATIVE_AUDIO_MODELS else ""
    if not effective_audio and audio_prompt:
        logger.info("Model %s lacks native audio — skipping audio", effective_model)

    logger.info("AtlasCloud motion_prompt: %s", motion_prompt)
    if effective_audio:
        logger.info("AtlasCloud audio_prompt: %s", effective_audio)
    try:
        video_path = await client.generate(
            image_path=image_path,
            prompt=motion_prompt,
            audio_prompt=effective_audio,
            model=effective_model,
            resolution=VIDEO_RESOLUTION,
            duration=VIDEO_DURATION,
        )
        logger.info(
            "Video generated: %s (model=%s, duration=%ds, audio=%s)",
            video_path, effective_model, VIDEO_DURATION, bool(effective_audio),
        )
        return video_path
    except Exception as e:
        logger.error("Video generation failed: %s", e)
        return None
