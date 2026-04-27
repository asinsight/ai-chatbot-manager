"""유저별 Rate Limiting — 초당/분당 제한 + 스팸 감지.

초당 2회 초과 → 조용히 무시
분당 10회 초과 → 제한 메시지
10초 내 5회 초과 → 5분 임시 차단
"""

import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

RATE_PER_SECOND = 2
RATE_PER_MINUTE = 10
SPAM_THRESHOLD = 5
SPAM_WINDOW = 10
SPAM_COOLDOWN = 300


class RateLimiter:
    def __init__(self):
        self._timestamps: dict[int, list[float]] = defaultdict(list)
        self._blocked: dict[int, float] = {}

    def check(self, user_id: int) -> tuple[bool, str]:
        """요청 허용 여부를 확인한다.

        Returns:
            (allowed, reason)
            - (True, "") — 허용
            - (False, "silent") — 조용히 무시
            - (False, "rate_limit") — 분당 제한
            - (False, "spam_blocked") — 스팸 차단
        """
        now = time.time()

        # 1. 스팸 차단 중인지 확인
        if user_id in self._blocked:
            if now < self._blocked[user_id]:
                return False, "spam_blocked"
            else:
                del self._blocked[user_id]
                logger.info("[rate] 차단 해제: user=%s", user_id)

        # 타임스탬프 정리 (60초 이전 제거)
        self._timestamps[user_id] = [
            t for t in self._timestamps[user_id] if now - t < 60
        ]
        timestamps = self._timestamps[user_id]

        # 2. 초당 제한
        recent_1s = sum(1 for t in timestamps if now - t < 1)
        if recent_1s >= RATE_PER_SECOND:
            return False, "silent"

        # 3. 분당 제한
        if len(timestamps) >= RATE_PER_MINUTE:
            logger.warning("[rate] 분당 제한 초과: user=%s count=%d", user_id, len(timestamps))
            return False, "rate_limit"

        # 4. 스팸 감지
        recent_spam = sum(1 for t in timestamps if now - t < SPAM_WINDOW)
        if recent_spam >= SPAM_THRESHOLD:
            self._blocked[user_id] = now + SPAM_COOLDOWN
            logger.warning("[rate] 스팸 차단: user=%s (%d초)", user_id, SPAM_COOLDOWN)
            return False, "spam_blocked"

        # 허용
        timestamps.append(now)
        return True, ""

    def unblock(self, user_id: int) -> bool:
        """유저 차단을 해제한다. 차단 중이었으면 True, 아니면 False."""
        if user_id in self._blocked:
            del self._blocked[user_id]
            logger.info("[rate] Admin 차단 해제: user=%s", user_id)
            return True
        return False

    def get_blocked_users(self) -> list[dict]:
        """현재 차단 중인 유저 목록을 반환한다.

        Returns:
            [{"user_id": int, "remaining": float}, ...]
        """
        now = time.time()
        result = []
        expired = []
        for user_id, unblock_at in self._blocked.items():
            if now < unblock_at:
                result.append({
                    "user_id": user_id,
                    "remaining": unblock_at - now,
                })
            else:
                expired.append(user_id)
        for uid in expired:
            del self._blocked[uid]
        return result


rate_limiter = RateLimiter()
