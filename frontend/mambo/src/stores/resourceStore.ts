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
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';
import type {
  Resource,
  ResourceCreate,
  ResourceUpdate,
  ResourceReorderItem,
  ResourceNode,
  ResourceVersionCreate,
  ResourceWithVersions,
  ResourceVersionUpdate,
} from '@/api/types';

/**
 * 管理资源中心（提示词、角色卡等）的全局状态。
 */
export const useResourceStore = defineStore('resource', () => {
  // --- State ---
  const resources = ref<ResourceWithVersions[]>([]);

  // --- Getters ---
  const resourceTree = computed((): ResourceNode[] => {
    // NOTE: The type assertion is safe because ResourceWithVersions includes all properties of Resource.
    return buildChatTree(resources.value as Resource[]);
  });

  // --- Actions ---

  // 使用通用 Composable 封装树形数据操作
  const {
    isLoading: isResourcesLoading,
    fetchItems: fetchResources,
    createItem: addResourceItem,
    updateItem: updateResourceItem,
    deleteItem: deleteResourceItem,
    reorderItems: reorderResourceItems,
  } = useTreeStoreActions<Resource, ResourceCreate, ResourceUpdate>({
    items: resources,
    api: {
      fetchAll: getResources,
      create: createResource,
      update: updateResource,
      // 适配 remove 函数。调用原始 API，但忽略其 Resource 返回值，以匹配 Promise<void>
      remove: async (id: string): Promise<void> => {
        await deleteResource(id);
      },
      // 适配 reorder 函数。调用原始 API，但忽略其 { message: string } 返回值，以匹配 Promise<void>
      reorder: async (updates: ResourceReorderItem[]): Promise<void> => {
        await reorderResources(updates);
      },
    },
    // onDeleteItem is not needed here as there are no store-level side effects.
    // UI-related side effects (like clearing the selected ID) will be handled in the component.
  });

  // --- Resource-Specific Actions (Versioning, etc.) ---

  /**
   * 更新指定资源当前活跃版本的内容。
   */
  async function updateVersionContent(resource: Resource, newContent: string) {
    if (!resource.latest_version) {
      console.error(`Resource ${resource.id} has no active version to update.`);
      return;
    }
    // 复用通用的更新逻辑，确保 versions 列表和 latest_version 都被更新
    await updateResourceVersionItem(resource.id, resource.latest_version.id, { content: newContent });
  }

  /**
   * 更新指定资源的特定版本（内容、属性等）。
   *
   * 此方法替代了原有的 updateActiveVersionDetails，支持指定 versionId，
   * 并确保同时更新 versions 列表中的对应项和 latest_version（如果匹配）。
   */
  async function updateResourceVersionItem(resourceId: string, versionId: string, data: ResourceVersionUpdate) {
    const resource = resources.value.find(r => r.id === resourceId);
    if (!resource) {
      console.error(`Resource ${resourceId} not found.`);
      return;
    }

    try {
      const updatedVersion = await updateResourceVersion(versionId, data);

      // 1. 同步更新 versions 列表中的对应项
      if (resource.versions) {
        const vIndex = resource.versions.findIndex(v => v.id === versionId);
        if (vIndex !== -1) {
          Object.assign(resource.versions[vIndex], updatedVersion);
        }
      }

      // 2. 如果更新的是当前活跃版本，同步更新 latest_version
      if (resource.latest_version && resource.latest_version.id === versionId) {
        Object.assign(resource.latest_version, updatedVersion);
      }
    } catch (error) {
      console.error(`Failed to update version ${versionId}:`, error);
      // 发生错误时，从服务器获取最新状态以保证一致性
      await fetchResourceDetails(resourceId);
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
        resources.value[index].latest_version = updatedResource.latest_version;
      }
    } catch (error) {
      console.error(`Failed to set active version for resource ${resourceId}:`, error);
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
    // State
    resources,
    isResourcesLoading,
    // Getters
    resourceTree,
    // Actions from Composable
    fetchResources,
    addResourceItem,
    updateResourceItem,
    deleteResourceItem,
    reorderResourceItems,
    // Resource-specific Actions
    updateVersionContent,
    updateResourceVersionItem,
    createNewVersion,
    setActiveResourceVersion,
    fetchResourceDetails,
  };
});
