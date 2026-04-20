// frontend/mambo/src/api/fileService.ts

import apiClient from './index';
import type { FileResponse } from './types';

/**
 * 上传单个文件到服务器。
 * @param file 用户选择的 File 对象。
 * @returns 返回已上传文件的元数据。
 */
export const uploadFile = (file: File): Promise<FileResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  return apiClient.post('/files/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

/**
 * 获取文件文本内容
 * @param fileId 文件ID
 */
export const getFileContent = (fileId: string): Promise<{ content: string }> => {
  return apiClient.get(`/files/${fileId}/content`);
};

/**
 * 更新文件文本内容
 * @param fileId 文件ID
 * @param content 文本内容
 */
export const updateFileContent = (fileId: string, content: string): Promise<FileResponse> => {
  return apiClient.put(`/files/${fileId}`, { content });
};
