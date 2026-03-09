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
  ResourceVersionUpdate,
  MoveRequest,
  ResourceSearchRequest,
  ResourceSearchResponse,
  SkillCreate,
  SkillValidationResult,
  SkillImportResponse
} from './types';

/**
 * [新增] 懒加载获取资源/文件夹子节点
 * @param parentIds 父节点ID列表，传 "root" 获取根目录
 */
export const getResourceChildren = (parentIds: string[]): Promise<Resource[]> => {
  const params = new URLSearchParams();
  parentIds.forEach(id => params.append('parentIds', id));
  return apiClient.get('/resources/children', { params });
};

/**
 * [新增] 移动资源/文件夹节点
 */
export const moveResource = (data: MoveRequest): Promise<void> => {
  return apiClient.post('/resources/move', data);
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

/**
 * 全局搜索资源
 * @param data 搜索请求参数
 * @returns 返回搜索结果
 */
export const searchResources = (data: ResourceSearchRequest): Promise<ResourceSearchResponse> => {
  return apiClient.post('/resources/search', data);
};

/**
 * 创建新的 SKILL 资源
 * 后端会自动创建对应的文件夹和 SKILL.md 文件
 */
export const createSkill = (data: SkillCreate): Promise<Resource> => {
  return apiClient.post('/resources/skills', data);
};

/**
 * 验证 SKILL 是否符合规范
 */
export const validateSkill = (resourceId: string): Promise<SkillValidationResult> => {
  return apiClient.get(`/resources/skills/${resourceId}/validate`);
};


/**
 * 通过文件/压缩包导入 Skill
 * @param file 文件对象 (SKILL.md 或 .zip)
 * @param parentId 目标父文件夹 ID
 */
export const importSkillFromFile = (
  file: File,
  parentId: string | null = null
): Promise<SkillImportResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  if (parentId) {
    formData.append('parent_id', parentId)
  }
  return apiClient.post('/resources/skills/import/file', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 通过 GitHub 仓库导入 Skill
 * @param repoUrl 仓库地址
 * @param parentId 目标父文件夹 ID
 */
export const importSkillFromGithub = (
  repoUrl: string,
  parentId: string | null = null
): Promise<SkillImportResponse> => {
  return apiClient.post('/resources/skills/import/github', {
    repo_url: repoUrl,
    parent_id: parentId
  })
}
