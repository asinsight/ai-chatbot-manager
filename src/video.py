"""Video generation module — AtlasCloud i2v wrapper.

wan26 / wan26-flash / seedance: native audio (generate_audio=true)
"""

import logging
import os

logger = logging.getLogger(__name__)

# Read video config from .env
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "alibaba/wan-2.6/image-to-video-flash")
VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "480p")
VIDEO_DURATION = int(os.getenv("VIDEO_DURATION", "5"))

# Models with native audio support — only these models forward audio_prompt
_NATIVE_AUDIO_MODELS = {
    "alibaba/wan-2.6/image-to-video",
    "alibaba/wan-2.6/image-to-video-flash",
    "alibaba/wan-2.7/image-to-video",
    "bytedance/seedance-v1.5-pro/image-to-video-spicy",
}

# AtlasCloudClient — requires ATLASCLOUD_API_KEY env var
_client = None


def _get_client():
    """Lazily initialize the client (returns None if ATLASCLOUD_API_KEY is missing)."""
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
    """Generate a video from an image (with optional audio).

    - wan26 / wan26-flash / seedance: native audio
    - Video duration is fixed by VIDEO_DURATION in .env

    Args:
        image_path: input image path.
        motion_prompt: motion prompt produced by the composer.
        audio_prompt: audio prompt produced by the composer (only used for native-audio models).

    Returns the local file path on success, None on failure.
    """
    client = _get_client()
    if not client:
        logger.error("AtlasCloud client not available")
        return None

    effective_model = VIDEO_MODEL
    # Detect native-audio model
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
