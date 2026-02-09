// frontend/mambochat/src/api/settingsService.ts

import apiClient from './index';
import type { GlobalSettingsUpdate, ProxyTestRequest, ConnectionTestResponse, FileResponse } from './types';

/**
 * 获取全局配置
 */
export const getGlobalSettings = (): Promise<GlobalSettingsUpdate> => {
  return apiClient.get('/settings/global')
};

/**
 * 更新全局配置
 * @param settings - 包含要更新的配置的对象
 */
export const updateGlobalSettings = (settings: GlobalSettingsUpdate): Promise<GlobalSettingsUpdate> => {
  return apiClient.put('/settings/global', settings)
};

/**
 * 上传头像文件
 * @param type - 头像类型, 'user' 或 'ai'
 * @param file - 用户选择的文件对象
 */
export const uploadAvatar = (type: 'user' | 'ai', file: File): Promise<FileResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  const url = `/settings/avatar/${type}`;

  return apiClient.put(url, formData, {
    headers: {
      // 当使用 FormData 时, 浏览器会自动设置正确的 Content-Type 和 boundary
      // 通常不需要手动设置, 但为明确起见保留
      'Content-Type': 'multipart/form-data',
    }
  })
};

/**
 * 删除指定类型的头像
 * @param type - 头像类型, 'user' 或 'ai'
 */
export const deleteAvatar = (type: 'user' | 'ai'): Promise<void> => {
  const url = `/settings/avatar/${type}`;
  // 204 No Content 响应体为空, .then() 会接收到 undefined
  return apiClient.delete(url)
};

/**
 * 测试代理服务器的连通性
 * @param data - 包含代理URL和测试目标URL的对象
 */
export const testProxyConnection = (data: ProxyTestRequest): Promise<ConnectionTestResponse> => {
  return apiClient.post('/settings/test-proxy', data)
};
