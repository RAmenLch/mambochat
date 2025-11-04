# backend/routers/notifications.py
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ..services.stream_manager_service import stream_manager

router = APIRouter()

# 定义一个常量作为全局通知流的唯一标识符
GLOBAL_NOTIFICATIONS_STREAM_ID = "global_notifications"


async def _notification_stream_generator():
    """
    一个异步生成器，用于监听并向客户端推送全局通知。
    """
    queue = await stream_manager.subscribe(GLOBAL_NOTIFICATIONS_STREAM_ID)
    try:
        while True:
            # 等待从队列中获取通知数据
            notification_data = await queue.get()
            if notification_data is None:  # 流结束的信号
                break

            # 将数据格式化为SSE事件并发送
            yield f"data: {json.dumps(notification_data)}\n\n"
            queue.task_done()
    except asyncio.CancelledError:
        # 当客户端断开连接时，FastAPI会抛出CancelledError
        print(f"[Notifications] Client disconnected from global stream.")
    finally:
        # 确保在任何情况下都取消订阅，以防止内存泄漏
        await stream_manager.unsubscribe(GLOBAL_NOTIFICATIONS_STREAM_ID, queue)


@router.get(
    "/notifications/subscribe",
    summary="订阅全局实时通知",
    response_description="一个服务器发送事件 (SSE) 流，用于接收应用范围的通知。"
)
async def subscribe_to_notifications():
    """
    客户端通过此端点订阅全局通知流。
    连接将保持活动状态，以便服务器可以随时推送更新。
    """
    return StreamingResponse(_notification_stream_generator(), media_type="text/event-stream")

