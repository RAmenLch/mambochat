// frontend/mambo/src/api/resourceService.ts

import apiClient from './index';
import type {
  Resource,
  ResourceCreate,
  ResourceWithVersions,
  ResourceUpdate,
  ResourceReorderItem,
  ResourceVersion,
  ResourceVersionCreate,
  ResourceVersionUpdate
} from './types';

/**
 * 获取所有资源和文件夹的列表。
 */
export const getResources = (): Promise<Resource[]> => {
  return apiClient.get('/resources');
};

/**
 * 创建一个新的资源或文件夹。
 */
export const createResource = (data: ResourceCreate): Promise<Resource> => {
  return apiClient.post('/resources', data);
};

/**
 * 获取单个资源的详细信息，包含其所有版本的列表。
 */
export const getResourceDetails = (resourceId: string): Promise<ResourceWithVersions> => {
  return apiClient.get(`/resources/${resourceId}`);
};

/**
 * 更新资源的基本信息（如名称、父文件夹ID）。
 */
export const updateResource = (resourceId: string, data: ResourceUpdate): Promise<Resource> => {
  return apiClient.put(`/resources/${resourceId}`, data);
};

/**
 * 删除一个资源或文件夹。
 */
export const deleteResource = (resourceId: string): Promise<Resource> => {
  return apiClient.delete(`/resources/${resourceId}`);
};

/**
 * 批量更新资源和文件夹的顺序与层级。
 */
export const reorderResources = (updates: ResourceReorderItem[]): Promise<{ message: string }> => {
  return apiClient.post('/resources/reorder', updates);
};

/**
 * 为指定的资源创建一个新的版本快照。
 */
export const createResourceVersion = (resourceId: string, data: ResourceVersionCreate): Promise<ResourceVersion> => {
  return apiClient.post(`/resources/${resourceId}/versions`, data);
};

/**
 * 更新一个已存在的版本快照的内容或元数据。
 */
export const updateResourceVersion = (versionId: string, data: ResourceVersionUpdate): Promise<ResourceVersion> => {
  return apiClient.put(`/resources/versions/${versionId}`, data);
};

/**
 * 将指定资源的一个版本设置为其“当前活跃版本”。
 */
export const setActiveVersion = (resourceId: string, versionId: string): Promise<Resource> => {
  return apiClient.put(`/resources/${resourceId}/set-active/${versionId}`);
};
