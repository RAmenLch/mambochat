# backend/services/stream_manager_service.py

import asyncio
from collections import defaultdict
from typing import Dict, List, Set

class StreamManager:
    """
    一个内存中的发布/订阅管理器，用于处理实时流数据并支持优雅地停止任务。
    """

    def __init__(self):
        self.active_streams: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self.cancellation_requests: Set[str] = set()
        self.running_tasks: Set[str] = set()
        self.lock = asyncio.Lock()

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

    async def publish(self, message_id: str, chunk: any):
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
            self.cancellation_requests.discard(message_id)

    async def is_stream_active(self, message_id: str) -> bool:
        async with self.lock:
            return message_id in self.active_streams and len(self.active_streams[message_id]) > 0

    async def request_cancellation(self, message_id: str):
        async with self.lock:
            print(f"[StreamManager] Cancellation requested for message '{message_id}'.")
            self.cancellation_requests.add(message_id)

    async def is_cancellation_requested(self, message_id: str) -> bool:
        async with self.lock:
            return message_id in self.cancellation_requests

    async def mark_task_running(self, message_id: str):
        """标记一个生成任务已启动"""
        async with self.lock:
            self.running_tasks.add(message_id)
            print(f"[StreamManager] Task marked as RUNNING for message '{message_id}'.")

    async def mark_task_completed(self, message_id: str):
        """标记一个生成任务已结束"""
        async with self.lock:
            self.running_tasks.discard(message_id)
            print(f"[StreamManager] Task marked as COMPLETED for message '{message_id}'.")

    async def is_task_running(self, message_id: str) -> bool:
        """检查一个生成任务是否正在内存中运行"""
        async with self.lock:
            return message_id in self.running_tasks


stream_manager = StreamManager()
