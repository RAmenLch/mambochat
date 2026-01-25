// frontend/mambo/src/api/kbService.ts

import { fetchEventSource } from '@microsoft/fetch-event-source'
import apiClient from './index'
import type {
  Resource,
  KnowledgeBaseCreate,
  KBSearchRequest,
  KBSearchResponse,
  KBRunTaskRequest,
  KBTaskProgressPayload,
  KBUpdateConfigRequest,
} from './types'

/**
 * 创建新的知识库资源
 */
export const createKnowledgeBase = (data: KnowledgeBaseCreate): Promise<Resource> => {
  return apiClient.post('/kb', data)
}

/**
 * 上传通用资源文件
 * 支持新建文件资源 (传入 parentId) 或更新现有资源版本 (传入 resourceId)
 * @param file 要上传的文件对象
 * @param parentId 上传到的父文件夹ID (新建模式)
 * @param resourceId 要更新的资源ID (更新模式)
 */
export const uploadResourceFile = (
  file: File,
  parentId?: string,
  resourceId?: string,
): Promise<Resource> => {
  const formData = new FormData()
  formData.append('file', file)

  if (parentId) {
    formData.append('parent_id', parentId)
  }
  if (resourceId) {
    formData.append('resource_id', resourceId)
  }

  return apiClient.post('/resources/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

/**
 * 更新知识库文件的切分配置
 * @param resourceId 文件资源ID
 * @param data 配置数据
 */
export const updateKBFileConfig = (
  resourceId: string,
  data: KBUpdateConfigRequest,
): Promise<Resource> => {
  return apiClient.put(`/resources/kb/${resourceId}/config`, data)
}

/**
 * 在知识库中进行向量检索
 */
export const searchKnowledgeBase = (data: KBSearchRequest): Promise<KBSearchResponse> => {
  return apiClient.post('/resources/kb/search', data)
}

/**
 * 控制知识库文件的切分与嵌入任务
 * 支持启动(start)、断点续连(resume)和停止(stop)
 * @param resourceId 文件资源ID
 * @param data 任务控制参数
 */
export const runKBFileTask = (resourceId: string, data: KBRunTaskRequest): Promise<void> => {
  return apiClient.post(`/resources/kb/${resourceId}/task`, data)
}

/**
 * 知识库文件进度订阅参数
 */
export interface KBProgressSubscriptionParams {
  resourceId: string
  onMessage: (data: KBTaskProgressPayload) => void
  onError: (error: unknown) => void
  onClose?: () => void
}

/**
 * 订阅知识库文件的处理进度 (SSE)
 * @param params 订阅配置参数
 * @returns AbortController 用于中断连接
 */
export const subscribeToKBFileProgress = (
  params: KBProgressSubscriptionParams,
): AbortController => {
  const { resourceId, onMessage, onError, onClose } = params
  const controller = new AbortController()
  // 路径更新为 /api/resources/kb/{id}/progress
  const url = `/api/resources/kb/${resourceId}/progress`

  fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    openWhenHidden: true,

    onmessage(event) {
      // 处理服务端主动发送的结束事件
      if (event.event === 'end') {
        controller.abort()
        if (onClose) {
          onClose()
        }
        return
      }

      try {
        // 处理 SSE 消息
        const data: KBTaskProgressPayload = JSON.parse(event.data)
        onMessage(data)
      } catch (e) {
        console.error('Failed to parse KB progress data:', event.data, e)
        onError(e)
      }
    },

    onclose() {
      if (onClose) {
        onClose()
      }
    },

    onerror(err) {
      // 如果不是手动中止，则报告错误
      if (err.name !== 'AbortError') {
        onError(err)
      }
      // 抛出错误以停止库内部的自动重试机制
      throw err
    },
  })

  return controller
}
