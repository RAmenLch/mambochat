// frontend/mambo/src/stores/resourceStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import {
  getResourceChildren,
  createResource,
  updateResource,
  deleteResource,
  moveResource,
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
  MoveRequest,
  ResourceNode,
  ResourceVersionCreate,
  ResourceWithVersions,
  ResourceVersionUpdate,
} from '@/api/types';

/**
 * 管理资源中心（提示词、角色卡等）的全局状态。
 * 采用增量懒加载模式管理资源数据。
 */
export const useResourceStore = defineStore('resource', () => {
  // --- State ---
  const resources = ref<ResourceWithVersions[]>([]);

  // --- Getters ---
  const resourceTree = computed((): ResourceNode[] => {
    // NOTE: The type assertion is safe because ResourceWithVersions includes all properties of Resource.
    // buildChatTree 能够处理增量列表，未加载子节点的文件夹将作为叶子节点显示（直到被展开）
    return buildChatTree(resources.value as Resource[]);
  });

  // --- Actions ---

  // 使用通用 Composable 封装树形数据操作 (适配懒加载与移动接口)
  const {
    isLoading: isResourcesLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList,
    fetchChildren,
    createItem: addResourceItem,
    updateItem: updateResourceItem,
    deleteItem: deleteResourceItem,
    moveItem: moveResourceItem,
  } = useTreeStoreActions<Resource, ResourceCreate, ResourceUpdate>({
    items: resources,
    api: {
      fetchChildren: getResourceChildren,
      create: createResource,
      update: updateResource,
      // 适配 remove 函数。调用原始 API，但忽略其 Resource 返回值，以匹配 Promise<void>
      remove: async (id: string): Promise<void> => {
        await deleteResource(id);
      },
      move: async (req: MoveRequest): Promise<void> => {
        await moveResource(req);
      },
    },
    // onDeleteItem is not needed here as there are no store-level side effects.
  });

  /**
   * 预测加载子文件夹内容。
   * 在父文件夹加载完成后触发，静默加载其包含的子文件夹的下一级内容。
   */
  async function prefetchSubFolders(parentId: string) {
    const subFolders = resources.value.filter(
      item => item.parentId === parentId && item.itemType === 'folder'
    );

    if (subFolders.length === 0) return;

    setTimeout(() => {
      subFolders.forEach(folder => {
        if (!loadedFolderIds.value.has(folder.id) && !loadingFolders.value.has(folder.id)) {
          fetchChildren(folder.id).catch(err => {
            console.warn(`[Prefetch] Failed to prefetch resource folder ${folder.id}:`, err);
          });
        }
      });
    }, 200);
  }

  /**
   * 包装 fetchChildren 以集成预测加载逻辑。
   */
  async function fetchResourceChildren(parentId: string) {
    await fetchChildren(parentId);
    prefetchSubFolders(parentId);
  }

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
   * 在懒加载模式下，列表项不包含详细内容，点击资源时需调用此方法。
   */
  async function fetchResourceDetails(resourceId: string) {
    try {
      const detailedResource = await getResourceDetails(resourceId);
      const index = resources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        // 替换列表中的简略对象为详细对象
        resources.value[index] = detailedResource;
      } else {
        // 如果资源不在当前列表中（理论上不应发生，除非直接通过URL访问），则添加到列表
        resources.value.push(detailedResource);
      }
    } catch (error) {
      console.error(`Failed to fetch details for resource ${resourceId}:`, error);
    }
  }

  return {
    // State
    resources,
    isResourcesLoading,
    loadedFolderIds,
    loadingFolders,
    // Getters
    resourceTree,
    // Actions from Composable
    initializeList,
    fetchResourceChildren, // Exposed wrapper with prefetch
    addResourceItem,
    updateResourceItem,
    deleteResourceItem,
    moveResourceItem,
    // Resource-specific Actions
    updateVersionContent,
    updateResourceVersionItem,
    createNewVersion,
    setActiveResourceVersion,
    fetchResourceDetails,
  };
});
