// frontend/mambo/src/api/settingsService.ts

import apiClient from './index';
import type { GlobalSettingsUpdate } from './types';

/**
 * 获取全局配置
 */
export const getGlobalSettings = (): Promise<GlobalSettingsUpdate> => {
  return apiClient.get('/settings/global').then(res => res.data);
};

/**
 * 更新全局配置
 * @param settings - 包含要更新的配置的对象
 */
export const updateGlobalSettings = (settings: GlobalSettingsUpdate): Promise<GlobalSettingsUpdate> => {
  return apiClient.put('/settings/global', settings).then(res => res.data);
};
