# backend/services/stream_manager_service.py

import asyncio
import contextlib
from collections import defaultdict
from typing import AsyncIterator, TypeVar

T = TypeVar("T")


async def cancellable_aiter(aiter: AsyncIterator[T], cancel_event: asyncio.Event) -> AsyncIterator[T]:
    """
    包装一个异步迭代器，使其在 cancel_event 被触发时立即停止。

    用法::

        cancel_event = await stream_manager.get_cancel_event(message_id)
        async for item in cancellable_aiter(some_async_generator(), cancel_event):
            process(item)

    取消时会关闭底层生成器并抛出 asyncio.CancelledError，
    由调用方的 try/except 处理后续清理逻辑。
    """
    ait = aiter.__aiter__()
    try:
        while True:
            next_coro = asyncio.ensure_future(ait.__anext__())
            cancel_coro = asyncio.ensure_future(cancel_event.wait())

            done, pending = await asyncio.wait(
                {next_coro, cancel_coro},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for p in pending:
                p.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await p

            if cancel_coro in done:
                next_coro.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await next_coro
                raise asyncio.CancelledError("Generation cancelled.")

            exc = next_coro.exception()
            if exc:
                if isinstance(exc, StopAsyncIteration):
                    return
                raise exc
            yield next_coro.result()
    finally:
        await ait.aclose()


class StreamManager:
    """
    一个内存中的发布/订阅管理器，用于处理实时流数据并支持优雅地停止任务。
    """

    def __init__(self):
        self.active_streams: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._cancel_events: dict[str, asyncio.Event] = {}
        self.running_tasks: set[str] = set()
        self.lock = asyncio.Lock()
        self._chat_generation_locks: dict[str, asyncio.Lock] = {}
        self._chat_generation_locks_lock = asyncio.Lock()

    # ── 取消信号管理 ──────────────────────────────────────

    async def get_cancel_event(self, message_id: str) -> asyncio.Event:
        """获取或创建指定消息的取消事件。"""
        async with self.lock:
            event = self._cancel_events.get(message_id)
            if event is None:
                event = asyncio.Event()
                self._cancel_events[message_id] = event
            return event

    async def request_cancellation(self, message_id: str):
        """请求取消指定消息的生成任务。"""
        async with self.lock:
            print(f"[StreamManager] Cancellation requested for message '{message_id}'.")
            event = self._cancel_events.get(message_id)
            if event:
                event.set()
            else:
                event = asyncio.Event()
                event.set()
                self._cancel_events[message_id] = event

    async def is_cancellation_requested(self, message_id: str) -> bool:
        """检查是否已请求取消。"""
        async with self.lock:
            event = self._cancel_events.get(message_id)
            return event is not None and event.is_set()

    def _discard_cancel_event(self, message_id: str):
        """内部方法：清理取消事件（仅在持有 self.lock 时调用）。"""
        self._cancel_events.pop(message_id, None)

    # ── 流订阅管理 ──────────────────────────────────────

    async def subscribe(self, message_id: str) -> asyncio.Queue:
        async with self.lock:
            queue = asyncio.Queue()
            self.active_streams[message_id].append(queue)
            print(f"[StreamManager] New subscriber for message '{message_id}'. Total: {len(self.active_streams[message_id])}.")
            return queue

    async def unsubscribe(self, message_id: str, queue: asyncio.Queue):
        async with self.lock:
            if message_id in self.active_streams:
                try:
                    self.active_streams[message_id].remove(queue)
                    print(f"[StreamManager] Unsubscribed from message '{message_id}'. Remaining: {len(self.active_streams[message_id])}.")
                    if not self.active_streams[message_id]:
                        del self.active_streams[message_id]
                        print(f"[StreamManager] Stream '{message_id}' is now empty and has been removed.")
                except ValueError:
                    pass

    async def publish(self, message_id: str, chunk):
        async with self.lock:
            if message_id in self.active_streams:
                subscribers = self.active_streams[message_id]
                await asyncio.gather(*(queue.put(chunk) for queue in subscribers))

    async def close_stream(self, message_id: str):
        async with self.lock:
            if message_id in self.active_streams:
                subscribers = self.active_streams.pop(message_id, [])
                print(f"[StreamManager] Closing stream '{message_id}' for {len(subscribers)} subscribers.")
                await asyncio.gather(*(queue.put(None) for queue in subscribers))
            self._discard_cancel_event(message_id)

    async def is_stream_active(self, message_id: str) -> bool:
        async with self.lock:
            return message_id in self.active_streams and len(self.active_streams[message_id]) > 0

    # ── 任务状态管理 ──────────────────────────────────────

    async def mark_task_running(self, message_id: str):
        async with self.lock:
            self.running_tasks.add(message_id)
            print(f"[StreamManager] Task marked as RUNNING for message '{message_id}'.")

    async def try_mark_task_running(self, message_id: str) -> bool:
        """原子地尝试将任务标记为运行中。

        若该任务已存在则返回 False（不重复注册），否则注册并返回 True。
        用于需要去重的后台任务（如标题生成），避免重复调度。
        """
        async with self.lock:
            if message_id in self.running_tasks:
                print(f"[StreamManager] Task '{message_id}' already RUNNING, skipped duplicate registration.")
                return False
            self.running_tasks.add(message_id)
            print(f"[StreamManager] Task marked as RUNNING for message '{message_id}'.")
            return True

    async def mark_task_completed(self, message_id: str):
        async with self.lock:
            self.running_tasks.discard(message_id)
            print(f"[StreamManager] Task marked as COMPLETED for message '{message_id}'.")

    async def is_task_running(self, message_id: str) -> bool:
        async with self.lock:
            return message_id in self.running_tasks

    # ── 生成锁管理 ──────────────────────────────────────

    async def try_acquire_generation_lock(self, chat_id: str) -> bool:
        """
        尝试获取指定会话的生成锁。
        返回 True 表示获取成功，False 表示该会话已有生成任务在执行。
        """
        async with self._chat_generation_locks_lock:
            if chat_id in self._chat_generation_locks:
                if self._chat_generation_locks[chat_id].locked():
                    return False
            else:
                self._chat_generation_locks[chat_id] = asyncio.Lock()
            lock = self._chat_generation_locks[chat_id]
            acquired = await lock.acquire()
            if not acquired:
                return False
        print(f"[StreamManager] Generation lock ACQUIRED for chat '{chat_id}'.")
        return True

    async def release_generation_lock(self, chat_id: str):
        async with self._chat_generation_locks_lock:
            lock = self._chat_generation_locks.get(chat_id)
        if lock and lock.locked():
            lock.release()
            print(f"[StreamManager] Generation lock RELEASED for chat '{chat_id}'.")


stream_manager = StreamManager()
