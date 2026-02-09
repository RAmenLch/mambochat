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
import {
  uploadResourceFile,
  updateKBFileConfig as apiUpdateKBFileConfig,
  runKBFileTask as apiRunKBFileTask,
} from '@/api/kbService';
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
  KBSplitterConfig,
  KBRunTaskRequest,
} from '@/api/types';

/**
 * 管理资源中心（提示词、角色卡等）的全局状态。
 * 采用增量懒加载模式管理资源数据。
 */
export const useResourceStore = defineStore('resource', () => {
  // --- State ---
  const resources = ref<ResourceWithVersions[]>([]);

  // --- Actions (Composable) ---

  // 使用通用 Composable 封装树形数据操作 (适配懒加载与移动接口)
  const {
    isLoading: isResourcesLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList: _initializeList,
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

  // --- Getters ---
  const resourceTree = computed((): ResourceNode[] => {
    // NOTE: The type assertion is safe because ResourceWithVersions includes all properties of Resource.
    // buildChatTree 能够处理增量列表，并根据 loadedFolderIds 判断是否需要注入占位节点
    return buildChatTree(resources.value as Resource[], loadedFolderIds.value);
  });

  // --- Resource-Specific Actions (Versioning, etc.) ---

  /**
   * 预测加载子文件夹内容。
   * 在父文件夹加载完成后触发，静默加载其包含的子文件夹的下一级内容。
   */
  async function prefetchSubFolders(parentId: string) {
    const subFolders = resources.value.filter(item => {
      if (item.itemType !== 'folder') {
        return false;
      }
      // 如果是根目录加载，需要同时匹配 parentId 为 'root' 和 null 的情况
      if (parentId === 'root') {
        return item.parentId === 'root' || item.parentId === null;
      }
      return item.parentId === parentId;
    });

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
   * 初始化列表，并触发根目录下的子文件夹预加载。
   */
  async function initializeList() {
    await _initializeList();
    prefetchSubFolders('root');
  }

  /**
   * 包装 fetchChildren 以集成预测加载逻辑。
   */
  async function fetchResourceChildren(parentId: string) {
    await fetchChildren(parentId);
    prefetchSubFolders(parentId);
  }

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
   * 直接更新资源属性（用于同步后端返回的最新属性，如配置变更）
   */
  function updateResourceAttributes(resourceId: string, newAttributes: Record<string, any>) {
    const resource = resources.value.find(r => r.id === resourceId);
    if (resource && resource.latest_version) {
      // 合并更新，确保不丢失其他属性
      resource.latest_version.attributes = {
        ...resource.latest_version.attributes,
        ...newAttributes
      };
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

  // --- Knowledge Base Specific Actions ---

  /**
   * 上传文件到指定的知识库目录。
   * @param parentId 父文件夹ID (知识库ID或其子文件夹ID)
   * @param file 文件对象
   * @returns 新创建的资源对象
   */
  async function uploadKBFile(parentId: string, file: File) {
    try {
      const newResource = await uploadResourceFile(file, parentId);

      // 构造符合 Store 要求的 ResourceWithVersions 类型
      const resourceWithVersions: ResourceWithVersions = {
        ...newResource,
        versions: [], // 上传接口通常不返回完整版本历史，初始化为空
      };

      resources.value.push(resourceWithVersions);

      return newResource;
    } catch (error) {
      console.error('Store: Upload KB file failed', error);
      throw error;
    }
  }

  /**
   * 更新知识库文件的切分配置。
   * @param resourceId 资源ID
   * @param config 切分配置对象
   */
  async function updateKBFileConfig(resourceId: string, config: KBSplitterConfig) {
    const updatedResource = await apiUpdateKBFileConfig(resourceId, { splitter_config: config });

    // 同步更新本地状态
    const resource = resources.value.find(r => r.id === resourceId);
    if (resource) {
      // 同步更新根级别的 kb_config，确保 KnowledgeBaseFileDetail 能读取到最新值
      if (updatedResource.kb_config) {
        resource.kb_config = updatedResource.kb_config;
      }
    }
    return updatedResource;
  }

  /**
   * 控制知识库文件的任务（启动、继续、停止）。
   * @param resourceId 资源ID
   * @param data 任务控制参数
   */
  async function runKBFileTask(resourceId: string, data: KBRunTaskRequest) {
    await apiRunKBFileTask(resourceId, data);
    // 注意：任务启动后的状态更新通常由 SSE 订阅或轮询处理，此处不直接修改本地状态
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
    updateResourceAttributes,
    createNewVersion,
    setActiveResourceVersion,
    fetchResourceDetails,
    // KB Specific Actions
    uploadKBFile,
    updateKBFileConfig,
    runKBFileTask,
  };
});
