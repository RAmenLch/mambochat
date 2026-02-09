// frontend/mambo/src/services/sseService.ts

import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { SubMessage, MessageStatus } from '@/api/types';

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
  | { type: 'content_update'; sub_message_id: string; content: string };

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
  /** 当发生错误 (非手动中止) 时调用的回调函数。 */
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
  const url = `/api/chats/${chatId}/stream-response/${assistantMessageId}`;

  fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    // 即使浏览器标签页在后台，也保持连接
    openWhenHidden: true,

    onmessage(event) {
      try {
        const data: StreamedChunk = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse SSE data chunk:', event.data, e);
        // 出现解析错误时，也通知调用方，以便其可以尝试同步最终状态
        onError(e);
      }
    },

    onclose() {
      // 正常关闭时通知调用方
      onClose();
    },

    onerror(err) {
      // 如果错误不是由 AbortController.abort() 触发的，则视为真实错误并通知调用方
      if (err.name !== 'AbortError') {
        onError(err);
      }
      // fetchEventSource 在发生错误后会尝试重连，除非我们抛出错误
      // 这里不抛出，让其内部机制处理，但我们已经通知了调用方
    },
  });

  return controller;
}
