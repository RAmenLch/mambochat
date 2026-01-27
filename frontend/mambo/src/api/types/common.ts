// frontend/mambo/src/api/types/common.ts

import type {
  ChatUpdateNotificationPayload, TitleGenerationErrorContext,
  ZipHistoryUpdateNotificationPayload
} from "@/api/types/chatTypes.ts";

export type MoveAction = 'before' | 'after' | 'inside'

export interface MoveRequest {
  item_ids: string[]
  reference_id: string
  action: MoveAction
}

/**
 * 定义树形结构数据的基本接口。
 * 任何需要使用通用树组件 (ExplorerTree) 的数据模型都应满足此结构。
 */
export interface BaseTreeItem {
  id: string
  name: string
  parentId: string | null
  sortOrder: number
  itemType: string
}

/**
 * 定义树节点拖拽排序事件的数据载荷。
 */
export interface TreeReorderEvent {
  id: string
  parentId: string | null
  sortOrder: number
}

export interface FileResponse {
  id: string
  filename: string
  mime_type: string
  size: number
  created_at: string // ISO 8601 date string
  url: string
}

export type GlobalNotification =
  | {
      type: 'chat_update'
      payload: ChatUpdateNotificationPayload
    }
  | {
      type: 'zip_history_update'
      payload: ZipHistoryUpdateNotificationPayload
    }
  | {
      type: 'notification'
      category: 'title_generation_error'
      context: TitleGenerationErrorContext
      level: string
      message: string
    }
