"""Video-generation context cache — shared between handlers_char and handlers_imagegen.

When the 🎬 button is clicked we need the source image, description, tags, and any
motion override; this module bundles them under a ctx_id. Entries auto-expire
after 10 minutes and the temporary image files are cleaned up on expiry.
"""

from __future__ import annotations

import os
import time
import uuid

_video_contexts: dict[str, dict] = {}
_VIDEO_CTX_TTL = 600  # 10 minutes


def store_video_context(
    user_id: int,
    char_id: str,
    image_path: str,
    description: str,
    danbooru_tags: str = "",
    motion_override: str | None = None,
    scene_key: str | None = None,
    pose: str | None = None,
) -> str:
    """Store the context needed for video generation. Returns a ctx_id.

    char_id: "char01" etc. for character bots, "imagegen" or "" for the imagegen bot.
    motion_override: user-supplied Korean motion text. If set, skip Grok Vision.
    scene_key: SFW pose/scene classification from the character bot. Used by the
        🎬 video callback to keep the result consistent.
    pose: pose chosen from scene_key's `pose_pool`.
    """
    now = time.time()
    # Clean up expired entries (and their files)
    expired = [k for k, v in _video_contexts.items() if now - v["created_at"] > _VIDEO_CTX_TTL]
    for k in expired:
        cleanup_video_context(k)

    ctx_id = uuid.uuid4().hex[:8]
    _video_contexts[ctx_id] = {
        "user_id": user_id,
        "char_id": char_id,
        "image_path": image_path,
        "description": description,
        "danbooru_tags": danbooru_tags,
        "motion_override": motion_override,
        "scene_key": scene_key,
        "pose": pose,
        "created_at": now,
    }
    return ctx_id


def get_video_context(ctx_id: str) -> dict | None:
    """Look up a context by id. Returns None if expired or not found."""
    ctx = _video_contexts.get(ctx_id)
    if not ctx:
        return None
    if time.time() - ctx["created_at"] > _VIDEO_CTX_TTL:
        cleanup_video_context(ctx_id)
        return None
    return ctx


def cleanup_video_context(ctx_id: str) -> None:
    """Delete a context and clean up its temporary image file."""
    ctx = _video_contexts.pop(ctx_id, None)
    if ctx and ctx.get("image_path") and os.path.exists(ctx["image_path"]):
        try:
            os.unlink(ctx["image_path"])
        except OSError:
            pass
