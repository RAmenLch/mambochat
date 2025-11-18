// frontend/mambo/src/stores/resourceStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import {
  getResources,
  createResource,
  updateResource,
  deleteResource,
  reorderResources,
  updateResourceVersion,
  createResourceVersion,
  setActiveVersion,
  getResourceDetails,
} from '@/api/resourceService';
import { buildChatTree } from '@/utils/treeHelper';
import type {
  Resource,
  ResourceCreate,
  ResourceUpdate,
  ResourceReorderItem,
  ResourceNode,
  ResourceVersionCreate,
  ResourceWithVersions,
} from '@/api/types';

/**
 * 管理资源中心（提示词、角色卡等）的全局状态。
 */
export const useResourceStore = defineStore('resource', () => {
  // --- State ---
  const resources = ref<ResourceWithVersions[]>([]);
  const isResourcesLoading = ref(false);

  // --- Getters ---
  const resourceTree = computed((): ResourceNode[] => {
    return buildChatTree(resources.value);
  });

  // --- Actions ---

  /**
   * 从服务器获取完整的资源列表。
   */
  async function fetchResources() {
    isResourcesLoading.value = true;
    try {
      const fetchedResources = await getResources();
      resources.value = fetchedResources.map(r => ({ ...r, versions: [] }));
    } catch (error) {
      console.error('Failed to fetch resources:', error);
    } finally {
      isResourcesLoading.value = false;
    }
  }

  /**
   * 创建一个新的资源或文件夹。
   */
  async function addResourceItem(itemData: ResourceCreate): Promise<Resource | null> {
    try {
      const newItem = await createResource(itemData);
      resources.value.push({ ...newItem, versions: [] });
      return newItem;
    } catch (error) {
      console.error('Failed to create new resource item:', error);
      return null;
    }
  }

  /**
   * 更新资源或文件夹的基本设置（例如名称、描述）。
   */
  async function updateResourceItem(resourceId: string, settings: ResourceUpdate) {
    try {
      const updatedItem = await updateResource(resourceId, settings);
      const index = resources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        Object.assign(resources.value[index], updatedItem);
      }
    } catch (error) {
      console.error(`Failed to update settings for resource ${resourceId}:`, error);
    }
  }

  /**
   * 更新指定资源当前活跃版本的内容。
   */
  async function updateVersionContent(resource: Resource, newContent: string) {
    if (!resource.latest_version) {
      console.error(`Resource ${resource.id} has no active version to update.`);
      return;
    }
    const versionId = resource.latest_version.id;
    try {
      const updatedVersion = await updateResourceVersion(versionId, { content: newContent });
      const res = resources.value.find(r => r.id === resource.id);
      if (res && res.latest_version) {
        res.latest_version.content = updatedVersion.content;
      }
    } catch (error) {
      console.error(`Failed to update content for version ${versionId}:`, error);
      await fetchResourceDetails(resource.id);
    }
  }

  /**
   * 删除一个资源或文件夹。
   */
  async function deleteResourceItem(resourceId: string) {
    const index = resources.value.findIndex(r => r.id === resourceId);
    if (index === -1) return;
    const backup = resources.value[index];
    resources.value.splice(index, 1);
    try {
      await deleteResource(resourceId);
    } catch (error) {
      console.error(`Failed to delete resource ${resourceId}:`, error);
      resources.value.splice(index, 0, backup);
    }
  }

  /**
   * 对资源列表项进行重新排序。
   */
  async function reorderResourceItems(updates: ResourceReorderItem[]) {
    updates.forEach(update => {
      const item = resources.value.find(r => r.id === update.id);
      if (item) {
        item.parentId = update.parentId;
        item.sortOrder = update.sortOrder;
      }
    });
    resources.value.sort((a, b) => a.sortOrder - b.sortOrder);
    try {
      await reorderResources(updates);
    } catch (error) {
      console.error('Failed to reorder resources:', error);
      await fetchResources();
    }
  }

  /**
   * 为指定资源创建新版本。
   */
  async function createNewVersion(resourceId: string, versionData: ResourceVersionCreate) {
    try {
      await createResourceVersion(resourceId, versionData);
      await fetchResourceDetails(resourceId);
    } catch (error) {
      console.error(`Failed to create new version for resource ${resourceId}:`, error);
    }
  }

  /**
   * 设置资源的活跃版本。
   */
  async function setActiveResourceVersion(resourceId: string, versionId: string) {
    try {
      const updatedResource = await setActiveVersion(resourceId, versionId);
      const index = resources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        // 这是解决问题的关键：精准更新，而不是全局替换。
        resources.value[index].latest_version = updatedResource.latest_version;
      }
    } catch (error) {
      console.error(`Failed to set active version for resource ${resourceId}:`, error);
      // 发生错误时，刷新一次详情作为回滚/同步策略是合理的。
      await fetchResourceDetails(resourceId);
    }
  }

  /**
   * 获取单个资源的完整信息，包括所有版本。
   */
  async function fetchResourceDetails(resourceId: string) {
    try {
      const detailedResource = await getResourceDetails(resourceId);
      const index = resources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        resources.value[index] = detailedResource;
      }
    } catch (error) {
      console.error(`Failed to fetch details for resource ${resourceId}:`, error);
    }
  }

  return {
    resources,
    isResourcesLoading,
    resourceTree,
    fetchResources,
    addResourceItem,
    updateResourceItem,
    updateVersionContent,
    deleteResourceItem,
    reorderResourceItems,
    createNewVersion,
    setActiveResourceVersion,
    fetchResourceDetails,
  };
});
