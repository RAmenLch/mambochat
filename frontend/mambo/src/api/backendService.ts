import apiClient from './index';
import type { BackendConfig, BackendCreate, BackendUpdate, SshPublicKeyResponse, SshTestRequest, SshTestResponse, UnifiedLsRequest, LocalLsResponse } from './types/backendTypes';

export const getBackends = (skip = 0, limit = 100): Promise<BackendConfig[]> => {
  return apiClient.get('/backends/', { params: { skip, limit } });
};

export const getBackend = (backendId: string): Promise<BackendConfig> => {
  return apiClient.get(`/backends/${backendId}`);
};

export const createBackend = (data: BackendCreate): Promise<BackendConfig> => {
  return apiClient.post('/backends/', data);
};

export const updateBackend = (backendId: string, data: BackendUpdate): Promise<BackendConfig> => {
  return apiClient.put(`/backends/${backendId}`, data);
};

export const deleteBackend = (backendId: string): Promise<void> => {
  return apiClient.delete(`/backends/${backendId}`);
};

export const getSshPublicKey = (): Promise<SshPublicKeyResponse> => {
  return apiClient.get('/backends/ssh/public-key');
};

export const testSshConnection = (data: SshTestRequest): Promise<SshTestResponse> => {
  return apiClient.post('/backends/ssh/test', data);
};

/** 目录列表 API — 根据 backend_type 自动分发（ssh / local） */
export const listDirectory = (data: UnifiedLsRequest): Promise<LocalLsResponse> => {
  return apiClient.post('/backends/ls', data);
};

export interface ClientStatusResponse {
  connected: boolean;
  client_info?: Record<string, any>;
}

export const getClientStatus = (backendId: string): Promise<ClientStatusResponse> => {
  return apiClient.get(`/api-client/status/${backendId}`);
};

// [新增] 复制 Backend（副本）
export const duplicateBackend = (backendId: string): Promise<BackendConfig> => {
  return apiClient.post(`/backends/${backendId}/duplicate`);
};
