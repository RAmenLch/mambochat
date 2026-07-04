// frontend/mambo/src/api/agentService.ts
import apiClient from './index';
import type { Agent, AgentCreate, AgentUpdate, MoveRequest, HitlToolInfo } from './types';
import type { FileResponse } from './types/common'; // [新增] 引入 FileResponse

export const getAgents = (skip = 0, limit = 1000): Promise<Agent[]> => {
  return apiClient.get('/agents/', { params: { skip, limit } });
};

export const getAgentChildren = (parentIds: string[]): Promise<Agent[]> => {
  const params = new URLSearchParams();
  parentIds.forEach(id => params.append('parentIds', id));
  return apiClient.get('/agents/children', { params });
};

export const getAgent = (agentId: string): Promise<Agent> => {
  return apiClient.get(`/agents/${agentId}`);
};

export const createAgent = (data: AgentCreate): Promise<Agent> => {
  return apiClient.post('/agents/', data);
};

export const updateAgent = (agentId: string, data: AgentUpdate): Promise<Agent> => {
  return apiClient.put(`/agents/${agentId}`, data);
};

export const deleteAgent = (agentId: string): Promise<void> => {
  return apiClient.delete(`/agents/${agentId}`);
};

export const moveAgent = (data: MoveRequest): Promise<void> => {
  return apiClient.post('/agents/move', data);
};

// [新增] 上传 Agent 头像
export const uploadAgentAvatar = (agentId: string, file: File): Promise<FileResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  return apiClient.put(`/agents/${agentId}/avatar`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

// [新增] 删除 Agent 头像
export const deleteAgentAvatar = (agentId: string): Promise<void> => {
  return apiClient.delete(`/agents/${agentId}/avatar`);
};

// [新增] 获取 Agent 的可 AI 审核工具列表
export const getAgentHitlTools = (agentId: string): Promise<HitlToolInfo[]> => {
  return apiClient.get(`/agents/${agentId}/hitl-tools`);
};

// [新增] 复制 Agent（副本）
export const duplicateAgent = (agentId: string): Promise<Agent> => {
  return apiClient.post(`/agents/${agentId}/duplicate`);
};
