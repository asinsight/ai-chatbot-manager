"""Per-user rate limiting — per-second / per-minute caps + spam detection.

> 2 calls/sec  → silently dropped
> 10 calls/min → rate-limited message
> 5 calls within 10s → 5-minute temporary block
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
        """Decide whether the request is allowed.

        Returns:
            (allowed, reason)
            - (True, "") — allowed
            - (False, "silent") — silently dropped
            - (False, "rate_limit") — over the per-minute cap
            - (False, "spam_blocked") — spam-blocked
        """
        now = time.time()

        # 1. Check whether the user is currently spam-blocked
        if user_id in self._blocked:
            if now < self._blocked[user_id]:
                return False, "spam_blocked"
            else:
                del self._blocked[user_id]
                logger.info("[rate] block lifted: user=%s", user_id)

        # Prune old timestamps (older than 60s)
        self._timestamps[user_id] = [
            t for t in self._timestamps[user_id] if now - t < 60
        ]
        timestamps = self._timestamps[user_id]

        # 2. Per-second cap
        recent_1s = sum(1 for t in timestamps if now - t < 1)
        if recent_1s >= RATE_PER_SECOND:
            return False, "silent"

        # 3. Per-minute cap
        if len(timestamps) >= RATE_PER_MINUTE:
            logger.warning("[rate] per-minute cap exceeded: user=%s count=%d", user_id, len(timestamps))
            return False, "rate_limit"

        # 4. Spam detection
        recent_spam = sum(1 for t in timestamps if now - t < SPAM_WINDOW)
        if recent_spam >= SPAM_THRESHOLD:
            self._blocked[user_id] = now + SPAM_COOLDOWN
            logger.warning("[rate] spam block: user=%s (%ds)", user_id, SPAM_COOLDOWN)
            return False, "spam_blocked"

        # Allowed
        timestamps.append(now)
        return True, ""

    def unblock(self, user_id: int) -> bool:
        """Unblock a user. Returns True if they were blocked, False otherwise."""
        if user_id in self._blocked:
            del self._blocked[user_id]
            logger.info("[rate] admin unblock: user=%s", user_id)
            return True
        return False

    def get_blocked_users(self) -> list[dict]:
        """Return the list of currently blocked users.

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
