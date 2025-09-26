import apiClient from './index';
import type { AIProviderWithModels, AIProviderCreate, AIProvider, AIModelCreate, AIModel } from './types';

/**
 * 获取所有AI服务商及其模型
 */
export const getProviders = (): Promise<AIProviderWithModels[]> => {
  return apiClient.get('/providers/').then(res => res.data);
};

/**
 * 创建一个新的AI服务商
 */
export const createProvider = (providerData: AIProviderCreate): Promise<AIProvider> => {
  return apiClient.post('/providers/', providerData).then(res => res.data);
};

/**
 * 删除一个AI服务商
 */
export const deleteProvider = (providerId: string): Promise<AIProvider> => {
  return apiClient.delete(`/providers/${providerId}`).then(res => res.data);
};

/**
 * 为服务商添加新模型
 */
export const createModel = (modelData: AIModelCreate): Promise<AIModel> => {
  return apiClient.post('/models/', modelData).then(res => res.data);
};

/**
 * 删除一个AI模型
 */
export const deleteModel = (modelId: string): Promise<AIModel> => {
  return apiClient.delete(`/models/${modelId}`).then(res => res.data);
};
