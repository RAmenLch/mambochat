// frontend/mambo/src/api/mcpService.ts

import apiClient from './index';
import type {
  McpServer,
  McpCreateRequest,
  McpUpdateRequest,
  McpTestResponse,
  McpToolResponse,
  McpToolUpdate
} from './types';

/**
 * 获取所有可用 MCP 服务列表
 * 列表包含系统内置(isSystem=true)和用户自定义(isSystem=false)的服务
 */
export const getMcpList = (): Promise<McpServer[]> => {
  return apiClient.get('/mcp/');
};

/**
 * 获取指定 MCP 服务的详细配置
 * @param id MCP 服务 ID
 */
export const getMcpDetail = (id: string): Promise<McpServer> => {
  return apiClient.get(`/mcp/${id}`);
};

/**
 * 创建新的 MCP 服务配置
 * @param data 创建请求数据
 */
export const createMcp = (data: McpCreateRequest): Promise<McpServer> => {
  return apiClient.post('/mcp/', data);
};

/**
 * 更新现有的 MCP 服务配置
 * 注意: 系统内置服务(isSystem=true)不可更新
 * @param id MCP 服务 ID
 * @param data 更新请求数据
 */
export const updateMcp = (id: string, data: McpUpdateRequest): Promise<McpServer> => {
  return apiClient.put(`/mcp/${id}`, data);
};

/**
 * 删除指定的 MCP 服务配置
 * 注意: 系统内置服务(isSystem=true)不可删除
 * @param id MCP 服务 ID
 */
export const deleteMcp = (id: string): Promise<void> => {
  return apiClient.delete(`/mcp/${id}`);
};

/**
 * 测试指定 MCP 服务的连接状态
 * @param id MCP 服务 ID
 */
export const testMcpServer = (id: string): Promise<McpTestResponse> => {
  return apiClient.post(`/mcp/${id}/test`);
};

/**
 * 同步服务器工具列表
 * @param serverId MCP 服务 ID
 */
export const syncMcpTools = (serverId: string): Promise<McpToolResponse[]> => {
  return apiClient.post(`/mcp/${serverId}/sync`);
};

/**
 * 获取服务器工具列表
 * @param serverId MCP 服务 ID
 */
export const getMcpTools = (serverId: string): Promise<McpToolResponse[]> => {
  return apiClient.get(`/mcp/${serverId}/tools`);
};

/**
 * 更新工具配置
 * @param toolId 工具 ID
 * @param data 更新数据
 */
export const updateMcpTool = (toolId: string, data: McpToolUpdate): Promise<McpToolResponse> => {
  return apiClient.patch(`/mcp/tools/${toolId}`, data);
};

/**
 * 删除失效工具
 * @param toolId 工具 ID
 */
export const deleteMcpTool = (toolId: string): Promise<void> => {
  return apiClient.delete(`/mcp/tools/${toolId}`);
};
