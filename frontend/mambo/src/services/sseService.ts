// frontend/mambo/src/services/sseService.ts

import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { SubMessage, MessageStatus } from '@/api/types';
import { resolveApiUrl } from './electronUrl';

/**
 * SSE 断线重连的退避序列（毫秒）：用尽后固定使用最后一个间隔。
 *
 * `fetchEventSource` 默认在 `onerror` 未指定间隔时按 1s 无限重连。
 * 移动端锁屏/切后台/弱网时，一次断流会持续数秒到数分钟，
 * 1s 一轮的重连会在网络恢复前反复失败。这里改为逐步退避：
 * 重连本身只是一次 GET，不触发任何业务请求，代价可控且能自愈。
 */
const RETRY_DELAYS = [1000, 2000, 3000, 5000, 8000, 13000, 20000, 30000];

function nextRetryDelay(attempt: number): number {
  return RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
}

/**
 * 定义了从 SSE 流接收到的各类事件数据块的类型结构。
 * 'replace': 用全新的子消息数组和聚合状态完全替换现有内容，通常用于初次连接。
 * 'create': 指示在前端创建一个新的子消息。
 * 'append': 将内容追加到指定的子消息末尾。
 * 'status_update': 更新指定子消息的状态 (例如从 'generating' 到 'completed')。
 * 'content_update': 用新的完整内容替换指定子消息的内容。
 */
export type StreamedChunk =
  | { type: 'replace'; sub_messages: SubMessage[]; status: MessageStatus }
  | { type: 'create'; sub_message: SubMessage }
  | { type: 'append'; sub_message_id: string; content: string }
  | { type: 'status_update'; sub_message_id: string; status: MessageStatus }
  | { type: 'content_update'; sub_message_id: string; content: string }
  | { type: 'batch_status_update'; message_id: string; status: MessageStatus };

/**
 * SSE 订阅服务的参数配置。
 */
export interface SseSubscriptionParams {
  /** 当前会话的 ID。 */
  chatId: string;
  /** 正在生成的 AI 助手消息的 ID。 */
  assistantMessageId: string;
  /** 当接收到新的消息数据块时调用的回调函数。 */
  onMessage: (data: StreamedChunk) => void;
  /** 当 SSE 连接正常关闭时调用的回调函数。 */
  onClose: () => void;
  /**
   * 当收到无法解析的事件、或连接被彻底终止时调用。
   * 可重连的断线不会回调此函数（由内部按退避序列重连），调用方无需在此做数据拉取。
   */
  onError: (error: unknown) => void;
}

/**
 * 订阅指定 AI 助手消息的 Server-Sent Events (SSE) 流。
 * 此函数封装了 `fetchEventSource` 的所有配置和生命周期事件处理。
 *
 * @param params - 包含会话ID、消息ID和事件回调的配置对象。
 * @returns 返回一个 `AbortController` 实例，调用方可以使用它来手动中止 SSE 连接。
 */
export function subscribeToMessageStream(params: SseSubscriptionParams): AbortController {
  const { chatId, assistantMessageId, onMessage, onClose, onError } = params;

  const controller = new AbortController();
  const url = resolveApiUrl(`/api/chats/${chatId}/stream-response/${assistantMessageId}`);
  // 连续失败次数：收到任意事件即视为连接健康并归零
  let attempt = 0;

  const stream = fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    openWhenHidden: true,

    onmessage(event) {
      attempt = 0;
      try {
        const data: StreamedChunk = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse SSE data chunk:', event.data, e);
        onError(e);
      }
    },

    onclose() {
      onClose();
    },

    onerror(err) {
      // 主动 abort 后不再重连（库内部已拦截，此处仅兜底）
      if (controller.signal.aborted) throw err;
      const delay = nextRetryDelay(attempt);
      attempt += 1;
      console.warn(`SSE stream for message ${assistantMessageId} interrupted, retry in ${delay}ms:`, err);
      // 返回间隔交给库自行重连：重连成功后服务端首帧是全量 replace，可自愈
      return delay;
    },
  });

  // 库仅在 onerror 抛出等极端情况下 reject，兜底避免未处理拒绝
  stream.catch((err) => {
    if (!controller.signal.aborted) {
      console.error(`SSE stream for message ${assistantMessageId} terminated:`, err);
      onError(err);
    }
  });

  return controller;
}

/**
 * 待生成文件聚合 SSE 流的事件类型。
 */
export type PendingFileEvent =
  | { type: 'file_ready'; sub_message_id: string; file_id: string; file_info?: Record<string, unknown> }
  | { type: 'file_timeout'; sub_message_id: string; path: string; reason?: string };

/**
 * 订阅待生成文件的聚合 SSE 流。
 * 按会话聚合：进入会话时建立一条连接，等待该会话所有 pending 文件；
 * 全部文件就绪/超时后服务端正常关闭连接。
 */
export function subscribeToPendingFiles(
  chatId: string,
  callbacks: {
    onMessage: (data: PendingFileEvent) => void
    onClose: () => void
    onError: (error: unknown) => void
  },
): AbortController {
  const controller = new AbortController()
  const url = resolveApiUrl(`/api/chats/${chatId}/wait-for-files`)
  let attempt = 0

  const stream = fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    openWhenHidden: true,

    onmessage(event) {
      attempt = 0
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'file_ready' || data.type === 'file_timeout') {
          callbacks.onMessage(data)
        }
      } catch (e) {
        console.error('Failed to parse pending files SSE data:', event.data, e)
        callbacks.onError(e)
      }
    },

    onclose() {
      callbacks.onClose()
    },

    onerror(err) {
      if (controller.signal.aborted) throw err
      const delay = nextRetryDelay(attempt)
      attempt += 1
      console.warn(`Pending files SSE stream for chat ${chatId} interrupted, retry in ${delay}ms:`, err)
      return delay
    },
  })

  stream.catch((err) => {
    if (!controller.signal.aborted) {
      console.error(`Pending files SSE stream for chat ${chatId} terminated:`, err)
      callbacks.onError(err)
    }
  })

  return controller
}
