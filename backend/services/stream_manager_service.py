# backend/services/stream_manager_service.py

import asyncio
from collections import defaultdict
from typing import Dict, List, Set

class StreamManager:
    """
    一个内存中的发布/订阅管理器，用于处理实时流数据并支持优雅地停止任务。

    该管理器允许一个后台任务（发布者）生成数据块，并将其广播给多个
    并发的客户端连接（订阅者）。它还提供了一个机制，允许外部请求
    （例如通过一个API端点）来请求停止一个正在运行的生成任务。

    这是一个单例模式的实现，通过在模块级别创建实例来保证全局唯一。
    """

    def __init__(self):
        """
        初始化管理器。
        - active_streams: 存储每个流的订阅者队列。
        - cancellation_requests: 存储被请求停止的流的ID。
        - lock: 使用一个锁来保证对上述数据结构的并发访问安全。
        """
        self.active_streams: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self.cancellation_requests: Set[str] = set()
        self.lock = asyncio.Lock()

    async def subscribe(self, message_id: str) -> asyncio.Queue:
        """
        为一个指定的 message_id 订阅一个新的队列。

        Args:
            message_id: 要订阅的流的唯一标识符。

        Returns:
            一个新的 asyncio.Queue 实例，订阅者可以从中获取数据块。
        """
        async with self.lock:
            queue = asyncio.Queue()
            self.active_streams[message_id].append(queue)
            print(f"[StreamManager] New subscriber for message '{message_id}'. Total: {len(self.active_streams[message_id])}.")
            return queue

    async def unsubscribe(self, message_id: str, queue: asyncio.Queue):
        """
        取消订阅一个队列。

        Args:
            message_id: 正在订阅的流的ID。
            queue: 要移除的队列实例。
        """
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
        """
        向指定流的所有订阅者发布一个数据块。

        Args:
            message_id: 目标流的ID。
            chunk: 要发送的数据块。
        """
        async with self.lock:
            if message_id in self.active_streams:
                subscribers = self.active_streams[message_id]
                await asyncio.gather(*(queue.put(chunk) for queue in subscribers))

    async def close_stream(self, message_id: str):
        """
        关闭一个流，通知所有订阅者流已结束，并清理资源。
        """
        async with self.lock:
            if message_id in self.active_streams:
                subscribers = self.active_streams.pop(message_id, [])
                print(f"[StreamManager] Closing stream '{message_id}' for {len(subscribers)} subscribers.")
                await asyncio.gather(*(queue.put(None) for queue in subscribers))
            self.cancellation_requests.discard(message_id)

    async def request_cancellation(self, message_id: str):
        """
        请求停止一个正在运行的生成任务。
        """
        async with self.lock:
            print(f"[StreamManager] Cancellation requested for message '{message_id}'.")
            self.cancellation_requests.add(message_id)

    async def is_cancellation_requested(self, message_id: str) -> bool:
        """
        检查一个任务是否已被请求停止。
        """
        async with self.lock:
            return message_id in self.cancellation_requests


# 创建一个全局唯一的 StreamManager 实例，供整个应用使用
stream_manager = StreamManager()

