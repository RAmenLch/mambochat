// frontend/mambo/src/api/providerService.ts

import apiClient from './index';
import type {
  AIProviderWithModels,
  AIProvider,
  AIModelCreate,
  AIModel,
  ProviderWithModelsCreate,
  ConnectionRequest,
  ConnectionTestResponse,
  AIModelBase,
  AIProviderUpdate,
  AIModelUpdate
} from './types';

/**
 * 获取所有AI服务商及其模型
 */
export const getProviders = (): Promise<AIProviderWithModels[]> => {
  return apiClient.get('/providers/').then(res => res.data);
};

/**
 * 创建一个新的AI服务商，并可同时创建其下的模型
 * @param providerData - 包含服务商信息和可选模型列表的数据
 */
export const createProviderWithModels = (providerData: ProviderWithModelsCreate): Promise<AIProviderWithModels> => {
  return apiClient.post('/providers/', providerData).then(res => res.data);
};

/**
 * 更新一个已存在的AI服务商
 * @param providerId - 要更新的服务商ID
 * @param providerData - 要更新的服务商信息
 */
export const updateProvider = (providerId: string, providerData: AIProviderUpdate): Promise<AIProvider> => {
  return apiClient.put(`/providers/${providerId}`, providerData).then(res => res.data);
};

/**
 * 删除一个AI服务商及其所有关联模型
 * @param providerId - 要删除的服务商ID
 */
export const deleteProvider = (providerId: string): Promise<AIProvider> => {
  return apiClient.delete(`/providers/${providerId}`).then(res => res.data);
};

/**
 * 测试与服务商API的连接性
 * @param connectionData - 包含 apiHost 和 apiKey 的连接信息
 */
export const testConnection = (connectionData: ConnectionRequest): Promise<ConnectionTestResponse> => {
  return apiClient.post('/providers/test-connection', connectionData).then(res => res.data);
};

/**
 * 从服务商的API获取其可用的模型列表
 * @param connectionData - 包含 apiHost 和 apiKey 的连接信息
 */
export const fetchExternalModels = (connectionData: ConnectionRequest): Promise<AIModelBase[]> => {
  return apiClient.post('/providers/fetch-models', connectionData).then(res => res.data);
};

/**
 * 为一个已存在的服务商获取模型列表 (使用已存凭证)
 * @param providerId - 服务商ID
 */
export const fetchModelsForProvider = (providerId: string): Promise<AIModelBase[]> => {
  return apiClient.post(`/providers/${providerId}/fetch-models`).then(res => res.data);
};

/**
 * 为已存在的服务商添加一个新模型
 * @param modelData - 新模型的数据
 */
export const createModel = (modelData: AIModelCreate): Promise<AIModel> => {
  return apiClient.post('/models/', modelData).then(res => res.data);
};

/**
 * 更新一个已存在的AI模型
 * @param modelId - 要更新的模型的ID
 * @param modelData - 要更新的模型信息
 */
export const updateModel = (modelId: string, modelData: AIModelUpdate): Promise<AIModel> => {
  return apiClient.put(`/models/${modelId}`, modelData).then(res => res.data);
};

/**
 * 删除一个AI模型
 * @param modelId - 要删除的模型的ID
 */
export const deleteModel = (modelId: string): Promise<AIModel> => {
  return apiClient.delete(`/models/${modelId}`).then(res => res.data);
};
