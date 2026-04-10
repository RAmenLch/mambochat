// frontend/mambo/src/stores/mcpStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import {
  getMcpList,
  createMcp as apiCreateMcp,
  updateMcp as apiUpdateMcp,
  deleteMcp as apiDeleteMcp,
  testMcpServer as apiTestMcpServer,
  testMcpConfig as apiTestMcpConfig,
  syncMcpTools as apiSyncMcpTools,
  getMcpTools as apiGetMcpTools,
  updateMcpTool as apiUpdateMcpTool,
  deleteMcpTool as apiDeleteMcpTool
} from '@/api/mcpService';
import type {
  McpServer,
  McpCreateRequest,
  McpUpdateRequest,
  McpTestResponse,
  McpToolResponse,
  McpToolUpdate
} from '@/api/types';

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
   * 缓存当前正在查看的 Server 下的工具列表。
   */
  const currentServerTools = ref<McpToolResponse[]>([]);

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

  /**
   * 测试 MCP 服务连接并更新状态
   * 适配后端接口变更：无论成功失败 HTTP 状态码均为 200，需通过 response.status 判断
   */
  async function testConnection(id: string) {
    const service = availableServices.value.find(s => s.id === id);
    if (!service) return;

    try {
      const response = await apiTestMcpServer(id);

      // 更新测试时间
      service.last_test_at = new Date().toISOString();

      if (response.status === 'healthy') {
        service.last_status = 'healthy';
        service.last_error = null;
        await syncTools(id);
      } else {
        // 业务逻辑返回失败
        service.last_status = 'unhealthy';
        service.last_error = response.error || response.message || 'Connection failed';
        // 主动抛出错误，以便 UI 层捕获并显示错误提示
        throw new Error(service.last_error || 'Connection failed');
      }
    } catch (error: unknown) {
      // 捕获网络错误或上述抛出的业务错误
      service.last_status = 'unhealthy';
      service.last_test_at = new Date().toISOString();

      const errorMessage = error instanceof Error ? error.message : 'Unknown network error';
      // 如果 errorMessage 与 service.last_error 不一致，说明是网络层面的新错误（未被业务逻辑捕获）
      // 或者是首次赋值
      if (service.last_error !== errorMessage) {
         service.last_error = errorMessage || 'Unknown network error';
      }

      throw error;
    }
  }

  /**
   * 同步指定服务的工具列表
   */
  async function syncTools(serverId: string) {
    try {
      const tools = await apiSyncMcpTools(serverId);
      currentServerTools.value = tools;
    } catch (error) {
      console.error(`Failed to sync tools for server ${serverId}:`, error);
      throw error;
    }
  }

  /**
   * 获取指定服务的工具列表
   */
  async function fetchTools(serverId: string) {
    try {
      const tools = await apiGetMcpTools(serverId);
      currentServerTools.value = tools;
    } catch (error) {
      console.error(`Failed to fetch tools for server ${serverId}:`, error);
      throw error;
    }
  }

  /**
   * 更新工具配置
   */
  async function updateToolConfig(toolId: string, data: McpToolUpdate) {
    try {
      const updatedTool = await apiUpdateMcpTool(toolId, data);
      const index = currentServerTools.value.findIndex(t => t.id === toolId);
      if (index !== -1) {
        currentServerTools.value[index] = {
          ...currentServerTools.value[index],
          ...updatedTool
        };
      }
    } catch (error) {
      console.error(`Failed to update tool ${toolId}:`, error);
      throw error;
    }
  }

  /**
   * 删除失效工具
   */
  async function removeTool(toolId: string) {
    try {
      await apiDeleteMcpTool(toolId);
      currentServerTools.value = currentServerTools.value.filter(t => t.id !== toolId);
    } catch (error) {
      console.error(`Failed to remove tool ${toolId}:`, error);
      throw error;
    }
  }

  /**
   * 使用传入的配置直接测试 MCP 连接（无需保存，不写数据库）
   * 适用于新建或编辑时在保存前验证配置是否正确
   */
  async function testConnectionWithConfig(data: McpCreateRequest): Promise<McpTestResponse> {
    return await apiTestMcpConfig(data);
  }

  return {
    availableServices,
    currentServerTools,
    userMcpServices,
    activeUserMcpServices,
    fetchAvailableServices,
    createMcp,
    updateMcp,
    deleteMcp,
    testConnection,
    testConnectionWithConfig,
    syncTools,
    fetchTools,
    updateToolConfig,
    removeTool
  };
});
