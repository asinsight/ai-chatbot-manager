"""LLM 요청 큐 — Priority Queue + Semaphore로 동시 실행 제한.

우선순위:
  1 (NORMAL): 유저 대화
  2 (LOW):    요약/추출 (백그라운드)
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 우선순위 상수
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
        """워커 루프 시작 — bot.py에서 호출."""
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(
            "[queue] 워커 시작 (max_concurrent=%d, max_queue=%d, timeout=%ds)",
            self._max_concurrent, self._queue.maxsize, self._timeout,
        )

    async def stop(self):
        """워커 루프 종료."""
        if self._worker_task:
            self._worker_task.cancel()
            logger.info("[queue] 워커 종료")

    async def enqueue(self, messages, user_id=0, task_type="chat", max_tokens=250):
        """요청을 큐에 추가하고 결과를 기다린다.

        Args:
            messages: LLM에 보낼 메시지 리스트
            user_id: 유저 ID (우선순위 판단용)
            task_type: "chat" | "summary" | "extract"

        Returns:
            LLM 응답 문자열

        Raises:
            QueueFullError: 큐가 가득 찼을 때
            QueueTimeoutError: 대기 시간 초과 시
        """
        global _counter
        _counter += 1

        # 우선순위 결정
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
                "[queue] 큐 풀 거부: user=%s type=%s queue_size=%d",
                user_id, task_type, self._queue.qsize(),
            )
            raise QueueFullError()

        logger.info(
            "[queue] 추가: user=%s type=%s priority=%d 대기=%d",
            user_id, task_type, priority, self._queue.qsize(),
        )

        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "[queue] 타임아웃: user=%s type=%s 대기=%.1fs",
                user_id, task_type, time.time() - item.enqueued_at,
            )
            raise QueueTimeoutError()

    async def _worker(self):
        """큐에서 아이템을 꺼내 LLM 호출을 스케줄링한다."""
        while True:
            item = await self._queue.get()
            asyncio.create_task(self._process(item))

    async def _process(self, item):
        """세마포어로 동시 실행 수를 제한하여 LLM 호출."""
        from src.llm import chat_completion

        wait_time = time.time() - item.enqueued_at
        logger.debug(
            "[queue] 처리 시작: user=%s type=%s 대기=%.1fs",
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
                    "[queue] 완료: user=%s type=%s priority=%d 응답=%.1fs 대기=%.1fs",
                    item.user_id, item.task_type, item.priority, elapsed, wait_time,
                )
            except Exception as e:
                if not item.future.done():
                    item.future.set_exception(e)
                logger.error(
                    "[queue] 실패: user=%s type=%s error=%s",
                    item.user_id, item.task_type, e,
                )

    @property
    def pending(self):
        """현재 큐 대기 수."""
        return self._queue.qsize()


# 싱글턴 인스턴스
llm_queue = LLMQueue()
