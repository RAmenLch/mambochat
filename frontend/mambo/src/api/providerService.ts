// frontend/mambochat/src/api/providerService.ts

import apiClient from './index';
import type {
  AIProviderWithModels,
  ProviderWithModelsCreate,
  AIProviderUpdate,
  AIModel,
  AIModelCreate,
  AIModelUpdate,
  ConnectionRequest,
  ConnectionTestResponse,
  AIModelBase
} from './types';

/**
 * 获取所有服务商及其模型
 */
export const getProviders = (): Promise<AIProviderWithModels[]> => {
  return apiClient.get('/providers/').then(res => res.data);
};

/**
 * 创建一个包含模型的新服务商
 */
export const createProviderWithModels = (providerData: ProviderWithModelsCreate): Promise<AIProviderWithModels> => {
  return apiClient.post('/providers/', providerData).then(res => res.data);
};

/**
 * 更新服务商信息
 */
export const updateProvider = (providerId: string, providerData: AIProviderUpdate): Promise<AIProviderWithModels> => {
  return apiClient.put(`/providers/${providerId}`, providerData).then(res => res.data);
};

/**
 * 删除一个服务商
 */
export const deleteProvider = (providerId: string): Promise<void> => {
  return apiClient.delete(`/providers/${providerId}`).then(res => res.data);
};

/**
 * 创建一个新模型
 */
export const createModel = (modelData: AIModelCreate): Promise<AIModel> => {
  return apiClient.post('/models/', modelData).then(res => res.data);
};

/**
 * 更新模型信息
 */
export const updateModel = (modelId: string, modelData: AIModelUpdate): Promise<AIModel> => {
  return apiClient.put(`/models/${modelId}`, modelData).then(res => res.data);
};

/**
 * 删除一个模型
 */
export const deleteModel = (modelId: string): Promise<void> => {
  return apiClient.delete(`/models/${modelId}`).then(res => res.data);
};

/**
 * 测试与外部服务的连接 (需要提供 apiHost 和 apiKey)
 */
export const testConnection = (connectionData: ConnectionRequest): Promise<ConnectionTestResponse> => {
  return apiClient.post('/providers/test-connection', connectionData).then(res => res.data);
};

/**
 * 为已存在的服务商测试连接 (使用已存储的凭证)
 * @param providerId 服务商ID
 * @param apiHost 要测试的 API Host (用户可能在表单中修改)
 */
export const testConnectionForProvider = (providerId: string, apiHost: string): Promise<ConnectionTestResponse> => {
  // 后端会根据 providerId 从数据库中获取 key
  return apiClient.post(`/providers/${providerId}/test-connection`, { apiHost }).then(res => res.data);
};

/**
 * 从外部服务获取模型列表 (需要提供 apiHost 和 apiKey)
 */
export const fetchExternalModels = (connectionData: ConnectionRequest): Promise<AIModelBase[]> => {
  return apiClient.post('/providers/fetch-models', connectionData).then(res => res.data);
};

/**
 * 为已存在的服务商获取模型列表 (使用已存凭证)
 * @param providerId 服务商ID
 */
export const fetchModelsForProvider = (providerId: string): Promise<AIModelBase[]> => {
  return apiClient.get(`/providers/${providerId}/fetch-models`).then(res => res.data);
};

