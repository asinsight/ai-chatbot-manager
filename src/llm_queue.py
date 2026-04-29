"""LLM request queue — Priority queue + semaphore for concurrency control.

Priorities:
  1 (NORMAL): user-facing chat
  2 (LOW):    summarization / extraction (background)
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Priority constants
PRIORITY_HIGH = 0
PRIORITY_NORMAL = 1
PRIORITY_LOW = 2

_counter = 0


@dataclass(order=True)
class QueueItem:
    priority: int
    seq: int = field(compare=True)
    future: asyncio.Future = field(compare=False)
    messages: list = field(compare=False)
    user_id: int = field(compare=False, default=0)
    task_type: str = field(compare=False, default="chat")
    max_tokens: int = field(compare=False, default=250)
    enqueued_at: float = field(compare=False, default_factory=time.time)


class QueueFullError(Exception):
    pass


class QueueTimeoutError(Exception):
    pass


class LLMQueue:
    def __init__(self):
        max_size = int(os.getenv("LLM_MAX_QUEUE_SIZE", "20"))
        self._max_concurrent = int(os.getenv("LLM_MAX_CONCURRENT", "2"))
        self._timeout = int(os.getenv("LLM_QUEUE_TIMEOUT", "120"))
        self._queue = asyncio.PriorityQueue(maxsize=max_size)
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._worker_task = None

    async def start(self):
        """Start the worker loop — called from bot.py."""
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(
            "[queue] worker started (max_concurrent=%d, max_queue=%d, timeout=%ds)",
            self._max_concurrent, self._queue.maxsize, self._timeout,
        )

    async def stop(self):
        """Stop the worker loop."""
        if self._worker_task:
            self._worker_task.cancel()
            logger.info("[queue] worker stopped")

    async def enqueue(self, messages, user_id=0, task_type="chat", max_tokens=250):
        """Enqueue a request and await its result.

        Args:
            messages: list of messages to send to the LLM
            user_id: user id (used to decide priority)
            task_type: "chat" | "summary" | "extract"

        Returns:
            LLM response string

        Raises:
            QueueFullError: when the queue is full
            QueueTimeoutError: when the wait time exceeds the timeout
        """
        global _counter
        _counter += 1

        # Decide priority
        if task_type in ("summary", "extract"):
            priority = PRIORITY_LOW
        else:
            priority = PRIORITY_NORMAL

        future = asyncio.get_event_loop().create_future()
        item = QueueItem(
            priority=priority,
            seq=_counter,
            future=future,
            messages=messages,
            user_id=user_id,
            task_type=task_type,
            max_tokens=max_tokens,
        )

        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning(
                "[queue] queue full, rejected: user=%s type=%s queue_size=%d",
                user_id, task_type, self._queue.qsize(),
            )
            raise QueueFullError()

        logger.info(
            "[queue] enqueued: user=%s type=%s priority=%d pending=%d",
            user_id, task_type, priority, self._queue.qsize(),
        )

        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "[queue] timeout: user=%s type=%s waited=%.1fs",
                user_id, task_type, time.time() - item.enqueued_at,
            )
            raise QueueTimeoutError()

    async def _worker(self):
        """Pull items off the queue and schedule LLM calls."""
        while True:
            item = await self._queue.get()
            asyncio.create_task(self._process(item))

    async def _process(self, item):
        """Call the LLM with the semaphore bounding concurrency."""
        from src.llm import chat_completion

        wait_time = time.time() - item.enqueued_at
        logger.debug(
            "[queue] processing: user=%s type=%s waited=%.1fs",
            item.user_id, item.task_type, wait_time,
        )

        async with self._semaphore:
            start = time.time()
            try:
                result = await chat_completion(item.messages, max_tokens=item.max_tokens)
                if not item.future.done():
                    item.future.set_result(result)
                elapsed = time.time() - start
                logger.info(
                    "[queue] done: user=%s type=%s priority=%d resp=%.1fs waited=%.1fs",
                    item.user_id, item.task_type, item.priority, elapsed, wait_time,
                )
            except Exception as e:
                if not item.future.done():
                    item.future.set_exception(e)
                logger.error(
                    "[queue] failed: user=%s type=%s error=%s",
                    item.user_id, item.task_type, e,
                )

    @property
    def pending(self):
        """Current number of items pending in the queue."""
        return self._queue.qsize()


# Singleton instance
llm_queue = LLMQueue()
