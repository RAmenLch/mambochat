// frontend/mambo/src/api/backendService.ts
import apiClient from './index';
import type { BackendConfig, BackendCreate, BackendUpdate, SshPublicKeyResponse, SshTestRequest, SshTestResponse } from './types/backendTypes';

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
