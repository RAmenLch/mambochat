// frontend/mambo/src/api/imageGenService.ts

import apiClient from './index';
import type {
  ImageGenConfig,
  ImageGenConfigCreate,
  ImageGenConfigUpdate,
  ImageGenToolCheckResult,
} from './types';

/** 获取所有生图配置 */
export const getImageGenConfigs = (): Promise<ImageGenConfig[]> => {
  return apiClient.get('/image-gen/');
};

/** 获取单个生图配置 */
export const getImageGenConfig = (id: string): Promise<ImageGenConfig> => {
  return apiClient.get(`/image-gen/${id}`);
};

/** 创建生图配置 */
export const createImageGenConfig = (data: ImageGenConfigCreate): Promise<ImageGenConfig> => {
  return apiClient.post('/image-gen/', data);
};

/** 更新生图配置 */
export const updateImageGenConfig = (
  id: string,
  data: ImageGenConfigUpdate,
): Promise<ImageGenConfig> => {
  return apiClient.put(`/image-gen/${id}`, data);
};

/** 删除生图配置 */
export const deleteImageGenConfig = (id: string): Promise<void> => {
  return apiClient.delete(`/image-gen/${id}`);
};

/** 检测绑定的 MCP 服务是否符合生图标准（三个固定工具是否齐全） */
export const testImageGenConfig = (id: string): Promise<ImageGenToolCheckResult> => {
  return apiClient.post(`/image-gen/${id}/test`);
};
