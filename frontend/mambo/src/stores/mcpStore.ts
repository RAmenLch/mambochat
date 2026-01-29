// frontend/mambo/src/stores/mcpStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getMcpList, createMcp as apiCreateMcp, updateMcp as apiUpdateMcp, deleteMcp as apiDeleteMcp } from '@/api/mcpService';
import type { McpServer, McpCreateRequest, McpUpdateRequest } from '@/api/types';

/**
 * 管理 MCP (Model Context Protocol) 服务的全局状态。
 * 负责获取、缓存以及增删改查 MCP 工具/服务。
 */
export const useMcpStore = defineStore('mcp', () => {
  /**
   * 缓存从后端获取的所有可用 MCP 服务列表。
   * 包含系统内置(isSystem=true)和用户自定义(isSystem=false)的服务。
   */
  const availableServices = ref<McpServer[]>([]);

  /**
   * 获取用户自定义的 MCP 服务列表（非系统内置）。
   * 用于配置管理页面展示。
   */
  const userMcpServices = computed(() => {
    return availableServices.value.filter(s => !s.isSystem);
  });

  /**
   * 获取当前处于激活状态的用户自定义 MCP 服务列表。
   * 用于聊天工具栏展示供用户选择。
   */
  const activeUserMcpServices = computed(() => {
    return availableServices.value.filter(s => !s.isSystem && s.isEnabled);
  });

  /**
   * 从后端 API 获取并更新可用的 MCP 服务列表。
   */
  async function fetchAvailableServices() {
    try {
      const services = await getMcpList();
      availableServices.value = services;
    } catch (error) {
      console.error('Failed to fetch available MCP services:', error);
      availableServices.value = [];
    }
  }

  /**
   * 创建新的 MCP 服务
   */
  async function createMcp(data: McpCreateRequest) {
    try {
      await apiCreateMcp(data);
      await fetchAvailableServices();
    } catch (error) {
      console.error('Failed to create MCP service:', error);
      throw error;
    }
  }

  /**
   * 更新 MCP 服务
   */
  async function updateMcp(id: string, data: McpUpdateRequest) {
    try {
      await apiUpdateMcp(id, data);
      await fetchAvailableServices();
    } catch (error) {
      console.error(`Failed to update MCP service ${id}:`, error);
      throw error;
    }
  }

  /**
   * 删除 MCP 服务
   */
  async function deleteMcp(id: string) {
    try {
      await apiDeleteMcp(id);
      await fetchAvailableServices();
    } catch (error) {
      console.error(`Failed to delete MCP service ${id}:`, error);
      throw error;
    }
  }

  return {
    availableServices,
    userMcpServices,
    activeUserMcpServices,
    fetchAvailableServices,
    createMcp,
    updateMcp,
    deleteMcp,
  };
});
