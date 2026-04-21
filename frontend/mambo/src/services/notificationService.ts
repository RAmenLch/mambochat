// frontend/mambo/src/services/notificationService.ts

import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { GlobalNotification } from '@/api/types';
import { resolveApiUrl } from './electronUrl';

/**
 * 全局通知订阅服务的参数配置。
 */
export interface GlobalSseSubscriptionParams {
  /** 当接收到新的通知时调用的回调函数。 */
  onNotification: (data: GlobalNotification) => void;
  /** 当发生错误时调用的回调函数。 */
  onError: (error: unknown) => void;
}

/**
 * 订阅全局 Server-Sent Events (SSE) 通知流。
 * 此函数建立一个持久连接，用于接收来自后端的应用级实时通知。
 *
 * @param params - 包含事件回调的配置对象。
 * @returns 返回一个 `AbortController` 实例，调用方可以使用它来手动中止 SSE 连接。
 */
export function subscribeToGlobalNotifications(params: GlobalSseSubscriptionParams): AbortController {
  const { onNotification, onError } = params;

  const controller = new AbortController();
  const url = resolveApiUrl('/api/notifications/subscribe');

  fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    openWhenHidden: true,

    onmessage(event) {
      try {
        const data: GlobalNotification = JSON.parse(event.data);
        onNotification(data);
      } catch (e) {
        console.error('Failed to parse global notification data:', event.data, e);
        onError(e);
      }
    },

    onclose() {
      // The library will automatically try to reconnect on close.
      // We only need to intervene if the error is fatal.
    },

    onerror(err) {
      // If the error is not a manual abort, report it.
      if (err.name !== 'AbortError') {
        onError(err);
      }
      // The library's default behavior is to retry.
      // To stop retrying, we would need to throw the error.
      // For a persistent global listener, retrying is desirable.
    },
  });

  return controller;
}
