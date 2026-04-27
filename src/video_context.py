"""비디오 생성 컨텍스트 캐시 — handlers_char, handlers_imagegen 공유.

🎬 버튼 클릭 시 필요한 이미지/설명/태그/모션 override 등을 ctx_id에 묶어 보관.
TTL 10분 후 자동 만료 + 임시 이미지 파일 정리.
"""

from __future__ import annotations

import os
import time
import uuid

_video_contexts: dict[str, dict] = {}
_VIDEO_CTX_TTL = 600  # 10분


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
    """비디오 생성에 필요한 컨텍스트를 임시 저장. ctx_id 반환.

    char_id: 캐릭터 봇이면 "char01" 등, imagegen 봇이면 "imagegen" 또는 "".
    motion_override: 유저 지정 한글 모션. 있으면 Grok Vision 생략.
    scene_key: 캐릭터 봇의 SFW pose/scene 분류 결과. 🎬 영상 콜백에서 일관성 보장에 사용.
    pose: scene_key의 `pose_pool`에서 선택한 pose.
    """
    now = time.time()
    # 만료된 항목 정리 (파일도 삭제)
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
    """컨텍스트 조회. 만료/미존재 시 None."""
    ctx = _video_contexts.get(ctx_id)
    if not ctx:
        return None
    if time.time() - ctx["created_at"] > _VIDEO_CTX_TTL:
        cleanup_video_context(ctx_id)
        return None
    return ctx


def cleanup_video_context(ctx_id: str) -> None:
    """컨텍스트 삭제 + 임시 이미지 파일 정리."""
    ctx = _video_contexts.pop(ctx_id, None)
    if ctx and ctx.get("image_path") and os.path.exists(ctx["image_path"]):
        try:
            os.unlink(ctx["image_path"])
        except OSError:
            pass
