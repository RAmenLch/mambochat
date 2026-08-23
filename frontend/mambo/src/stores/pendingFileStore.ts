// frontend/mambo/src/stores/pendingFileStore.ts
import { watch } from 'vue'
import { defineStore } from 'pinia'
import { useChatSessionStore } from './chatSessionStore'
import { subscribeToPendingFiles, type PendingFileEvent } from '@/services/sseService'
import { getChatWithMessages } from '@/api/chatService'
import type { SubMessage } from '@/api/types'

export interface PendingFileCallbacks {
  onReady: (fileId: string, fileInfo: Record<string, unknown>) => void
  onTimeout: (path: string) => void
}

/**
 * 待生成文件聚合订阅中心。
 *
 * 同一会话内所有 pending 文件共享一条 wait-for-files SSE 连接：
 * - 组件挂载时 register（registry 0→1 时建立连接）
 * - 组件卸载时 unregister（registry 1→0 时断开连接）
 * - 后端处理完所有 pending 文件后正常关闭连接 → 本地仍有等待者时刷新
 *   messages 对齐数据，若对齐后仍有 pending 则自动重连（自愈）。
 *
 * 事件分发先更新 store 中的子消息数据（响应式驱动组件重渲染），
 * 再调用组件回调，避免“事件先于组件注册到达”的时序竞态。
 */
export const usePendingFileStore = defineStore('pendingFile', () => {
  const sessionStore = useChatSessionStore()

  const registry = new Map<string, PendingFileCallbacks>()
  let controller: AbortController | null = null

  // 切换会话时清理注册与连接
  watch(
    () => sessionStore.currentChatId,
    () => {
      disconnect()
      registry.clear()
    },
  )

  function register(subMessageId: string, callbacks: PendingFileCallbacks) {
    registry.set(subMessageId, callbacks)
    ensureConnected()
  }

  function unregister(subMessageId: string) {
    registry.delete(subMessageId)
    if (registry.size === 0) disconnect()
  }

  function ensureConnected() {
    const chatId = sessionStore.currentChatId
    if (!chatId || controller || registry.size === 0) return
    controller = subscribeToPendingFiles(chatId, {
      onMessage: handleMessage,
      onClose: handleClose,
      onError: () => {
        // 连接错误：保持 pending 状态，由 fetch-event-source 自动重连
      },
    })
  }

  function disconnect() {
    controller?.abort()
    controller = null
  }

  function handleMessage(data: PendingFileEvent) {
    if (data.type === 'file_ready') {
      updateSubMessage(data.sub_message_id, (sm) => {
        sm.content = data.file_id
        sm.status = 'completed'
        sm.config = {
          ...sm.config,
          pending_file_path: undefined,
          pending_file_timeout: undefined,
        }
        if (data.file_info) {
          sm.file_info = data.file_info as unknown as SubMessage['file_info']
        }
      })
      const cb = registry.get(data.sub_message_id)
      if (cb) {
        registry.delete(data.sub_message_id)
        cb.onReady(data.file_id, data.file_info ?? {})
      }
    } else if (data.type === 'file_timeout') {
      updateSubMessage(data.sub_message_id, (sm) => {
        sm.status = 'failed'
      })
      const cb = registry.get(data.sub_message_id)
      if (cb) {
        registry.delete(data.sub_message_id)
        cb.onTimeout(data.path)
      }
    }
  }

  function updateSubMessage(subMessageId: string, updater: (sm: SubMessage) => void) {
    const sm = findSubMessage(subMessageId)
    if (sm) updater(sm)
  }

  function findSubMessage(subMessageId: string): SubMessage | undefined {
    for (const msg of sessionStore.currentChatMessages) {
      const sm = msg.sub_messages.find((s) => s.id === subMessageId)
      if (sm) return sm
    }
    return undefined
  }

  async function handleClose() {
    controller = null
    if (registry.size === 0) return

    const chatId = sessionStore.currentChatId
    if (!chatId) {
      registry.clear()
      return
    }

    // 后端正常关闭（全部终态 / 无 pending）→ 刷新 messages 对齐本地数据
    try {
      const chatWithMessages = await getChatWithMessages(chatId)
      sessionStore.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder)
    } catch (err) {
      console.error('Failed to refresh messages after pending file stream closed:', err)
      return
    }

    // 对齐后剔除已终态的子消息；若仍有 waiting 文件（前后端数据竞态）则重连
    for (const subMessageId of Array.from(registry.keys())) {
      const sm = findSubMessage(subMessageId)
      const stillPending = sm?.status === 'waiting' && !!sm.config?.pending_file_path
      if (!stillPending) registry.delete(subMessageId)
    }
    if (registry.size > 0) ensureConnected()
  }

  return { register, unregister, reset: disconnect }
})
