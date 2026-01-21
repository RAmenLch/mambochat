// frontend/mambo/src/api/kbService.ts

import apiClient from './index';
import type {
  Resource,
  KnowledgeBaseCreate,
  KBChunkStatus,
  KBSearchRequest,
  KBSearchResponse
} from './types';

/**
 * 创建新的知识库资源
 */
export const createKnowledgeBase = (data: KnowledgeBaseCreate): Promise<Resource> => {
  return apiClient.post('/kb', data);
};

/**
 * 上传文件至指定知识库
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
 * 手动重试指定文件的向量化任务
 * @param resourceId 文件资源ID
 */
export const retryKBFile = (resourceId: string): Promise<void> => {
  return apiClient.post(`/kb/${resourceId}/retry`);
};
