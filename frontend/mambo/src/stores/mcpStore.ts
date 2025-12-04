// frontend/mambo/src/stores/mcpStore.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getAvailableMcpServices } from '@/api/chatService';
import type { McpService } from '@/api/types';

/**
 * 管理 MCP (Model Context Protocol) 服务的全局状态。
 * 负责获取并缓存后端可用的所有 MCP 工具/服务。
 */
export const useMcpStore = defineStore('mcp', () => {
  /**
   * 缓存从后端获取的所有可用 MCP 服务列表。
   */
  const availableServices = ref<McpService[]>([]);

  /**
   * 从后端 API 获取并更新可用的 MCP 服务列表。
   * 此操作通常在应用启动时执行一次。
   */
  async function fetchAvailableServices() {
    try {
      const services = await getAvailableMcpServices();
      // 仅存储当前处于激活状态的服务
      availableServices.value = services.filter(s => s.is_active);
    } catch (error) {
      console.error('Failed to fetch available MCP services:', error);
      // 在出错时清空列表，以防显示过时或不正确的数据
      availableServices.value = [];
    }
  }

  return {
    availableServices,
    fetchAvailableServices,
  };
});
