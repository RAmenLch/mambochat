// frontend/mambo/src/api/kbService.ts

import { fetchEventSource } from '@microsoft/fetch-event-source';
import apiClient from './index';
import type {
  Resource,
  KnowledgeBaseCreate,
  KBChunkStatus,
  KBSearchRequest,
  KBSearchResponse,
  KBRunTaskRequest,
  KBTaskProgressPayload
} from './types';

/**
 * 创建新的知识库资源
 */
export const createKnowledgeBase = (data: KnowledgeBaseCreate): Promise<Resource> => {
  return apiClient.post('/kb', data);
};

/**
 * 上传文件至指定知识库
 * 注意：上传后需调用 runKBFileTask 启动切分任务
 * @param kbId 知识库ID
 * @param file 要上传的文件对象
 */
export const uploadKBFile = (kbId: string, file: File): Promise<Resource> => {
  const formData = new FormData();
  formData.append('file', file);

  return apiClient.post(`/kb/${kbId}/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

/**
 * 查询特定文件的切片向量化处理状态
 * @param resourceId 文件资源ID
 */
export const getKBFileStatus = (resourceId: string): Promise<KBChunkStatus> => {
  return apiClient.get(`/kb/chunks/${resourceId}/status`);
};

/**
 * 在知识库中进行向量检索
 */
export const searchKnowledgeBase = (data: KBSearchRequest): Promise<KBSearchResponse> => {
  return apiClient.post('/kb/search', data);
};

/**
 * 控制知识库文件的切分与嵌入任务
 * 支持启动(start)、断点续连(resume)和停止(stop)
 * @param resourceId 文件资源ID
 * @param data 任务控制参数
 */
export const runKBFileTask = (resourceId: string, data: KBRunTaskRequest): Promise<void> => {
  return apiClient.post(`/kb/files/${resourceId}/task`, data);
};

/**
 * 知识库文件进度订阅参数
 */
export interface KBProgressSubscriptionParams {
  resourceId: string;
  onMessage: (data: KBTaskProgressPayload) => void;
  onError: (error: unknown) => void;
  onClose?: () => void;
}

/**
 * 订阅知识库文件的处理进度 (SSE)
 * @param params 订阅配置参数
 * @returns AbortController 用于中断连接
 */
export const subscribeToKBFileProgress = (params: KBProgressSubscriptionParams): AbortController => {
  const { resourceId, onMessage, onError, onClose } = params;
  const controller = new AbortController();
  const url = `/api/kb/files/${resourceId}/progress`;

  fetchEventSource(url, {
    method: 'GET',
    signal: controller.signal,
    openWhenHidden: true,

    onmessage(event) {
      try {
        // 处理 SSE 消息
        const data: KBTaskProgressPayload = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse KB progress data:', event.data, e);
        onError(e);
      }
    },

    onclose() {
      if (onClose) {
        onClose();
      }
    },

    onerror(err) {
      // 如果不是手动中止，则报告错误
      if (err.name !== 'AbortError') {
        onError(err);
      }
      // 抛出错误以停止库内部的自动重试机制，通常文件处理进度流中断后应由上层逻辑决定是否重连
      throw err;
    },
  });

  return controller;
};
