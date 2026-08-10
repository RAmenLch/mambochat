import apiClient from './index';
import type {
  ResourceCompletePathRequest,
  ResourceCompletePathResponse,
  ResourceContentCompleteRequest,
  ResourceContentCompleteResponse,
} from './types/resourceCompletionTypes';

/**
 * 资源路径补全：按 Agent 挂载的 ResourceBackend 子树检索路径候选。
 */
export const completeResourcePath = (
  data: ResourceCompletePathRequest,
): Promise<ResourceCompletePathResponse> => {
  return apiClient.post('/resources/completion/path', data);
};

/**
 * 资源内容续写：在挂载子树内检索前缀之后的续写片段。
 */
export const completeResourceContent = (
  data: ResourceContentCompleteRequest,
): Promise<ResourceContentCompleteResponse> => {
  return apiClient.post('/resources/completion/content', data);
};
