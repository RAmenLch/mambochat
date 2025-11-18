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
} from '@/api/resourceService';
import { buildChatTree } from '@/utils/treeHelper';
import type { Resource, ResourceCreate, ResourceUpdate, ResourceReorderItem, ResourceNode } from '@/api/types';

/**
 * 管理资源中心（提示词、角色卡等）的全局状态。
 */
export const useResourceStore = defineStore('resource', () => {
  // --- State ---
  const resources = ref<Resource[]>([]);
  const isResourcesLoading = ref(false);

  // --- Getters ---
  const resourceTree = computed((): ResourceNode[] => {
    // 使用通用的 buildChatTree 函数将扁平的资源列表转换为树状结构
    return buildChatTree(resources.value);
  });

  // --- Actions ---

  /**
   * 从服务器获取完整的资源列表。
   */
  async function fetchResources() {
    isResourcesLoading.value = true;
    try {
      resources.value = await getResources();
    } catch (error) {
      console.error('Failed to fetch resources:', error);
      // 用户侧的错误提示由全局 API 客户端拦截器处理
    } finally {
      isResourcesLoading.value = false;
    }
  }

  /**
   * 创建一个新的资源或文件夹。
   * @param itemData - 创建项所需的数据。
   * @returns 创建成功后的新项，或在失败时返回null。
   */
  async function addResourceItem(itemData: ResourceCreate): Promise<Resource | null> {
    try {
      const newItem = await createResource(itemData);
      resources.value.push(newItem);
      return newItem;
    } catch (error) {
      console.error('Failed to create new resource item:', error);
      return null;
    }
  }

  /**
   * 更新资源或文件夹的基本设置（例如名称、描述）。
   * @param resourceId - 要更新的项的ID。
   * @param settings - 要更新的设置。
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
   * @param resource - 目标资源对象。
   * @param newContent - 新的文本内容。
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
      await fetchResources(); // 失败时回退到重新获取以保证一致性
    }
  }

  /**
   * 删除一个资源或文件夹。
   * @param resourceId - 要删除的项的ID。
   */
  async function deleteResourceItem(resourceId: string) {
    const index = resources.value.findIndex(r => r.id === resourceId);
    if (index === -1) return;

    const backup = resources.value[index];
    resources.value.splice(index, 1); // 乐观更新UI

    try {
      await deleteResource(resourceId);
    } catch (error) {
      console.error(`Failed to delete resource ${resourceId}:`, error);
      resources.value.splice(index, 0, backup); // 失败时回滚UI
    }
  }

  /**
   * 对资源列表项进行重新排序。
   * @param updates - 包含排序更新信息的数组。
   */
  async function reorderResourceItems(updates: ResourceReorderItem[]) {
    // 乐观更新UI
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
      await fetchResources(); // 失败时从服务器重新获取以回滚
    }
  }

  return {
    // State
    resources,
    isResourcesLoading,
    // Getters
    resourceTree,
    // Actions
    fetchResources,
    addResourceItem,
    updateResourceItem,
    updateVersionContent,
    deleteResourceItem,
    reorderResourceItems,
  };
});
