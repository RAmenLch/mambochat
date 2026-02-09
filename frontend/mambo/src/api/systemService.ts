// frontend/mambo/src/api/systemService.ts

import apiClient from './index';
import type { SystemConfigResponse } from './types';

/**
 * 获取系统级配置信息。
 *
 * @returns 返回一个包含所有支持的LLM参数定义和预设服务商列表的Promise。
 */
export const getSystemConfig = (): Promise<SystemConfigResponse> => {
  return apiClient.get('/system-config');
};

