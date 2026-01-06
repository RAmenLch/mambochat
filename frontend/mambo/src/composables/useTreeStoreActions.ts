// frontend/mambo/src/composables/useTreeStoreActions.ts

import { ref, type Ref } from 'vue';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import { ElMessage } from 'element-plus';

// --- Interface Definitions ---

/**
 * 定义了此 Composable 所需的 API 服务函数集合的接口。
 * 适配懒加载和节点移动的新架构。
 *
 * @template TItem 树节点的数据类型。
 * @template TCreate 创建新条目时所需的数据类型。
 * @template TUpdate 更新条目时所需的数据类型。
 */
interface TreeStoreApi<TItem, TCreate, TUpdate> {
  /** 懒加载获取子节点列表 */
  fetchChildren: (parentIds: string[]) => Promise<TItem[]>;
  /**
   * 获取节点链路 (用于深层回溯)。
   * 可选属性，因为并非所有模块（如资源）都支持深层链接回溯。
   */
  fetchLineage?: (id: string) => Promise<TItem[]>;
  /** 创建新条目 */
  create: (data: TCreate) => Promise<TItem>;
  /** 更新条目 */
  update: (id: string, data: TUpdate) => Promise<TItem>;
  /** 删除条目 */
  remove: (id: string) => Promise<void>;
  /** 移动条目 (替代原有的 reorder) */
  move: (req: MoveRequest) => Promise<void>;
  /** (可选) 复制条目 */
  duplicate?: (id: string) => Promise<TItem>;
}

/**
 * `useTreeStoreActions` Composable 的配置选项接口。
 */
interface TreeStoreActionsOptions<TItem extends BaseTreeItem, TCreate, TUpdate> {
  /** 指向 Store state 中扁平化列表的 Ref。 */
  items: Ref<TItem[]>;
  /** 包含 API 服务函数的对象。 */
  api: TreeStoreApi<TItem, TCreate, TUpdate>;
  /** (可选) 在条目成功删除后执行的回调函数，用于处理副作用。 */
  onDeleteItem?: (deletedItem: TItem) => void;
}

/**
 * `useTreeStoreActions` Composable 的返回值接口。
 */
interface UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  /** 指示全局或初始加载操作是否正在进行的 Ref。 */
  isLoading: Ref<boolean>;
  /** 记录已完成加载子节点的文件夹 ID 集合。 */
  loadedFolderIds: Ref<Set<string>>;
  /** 记录当前正在加载子节点的文件夹 ID 集合。 */
  loadingFolders: Ref<Set<string>>;

  /** 初始化列表 (通常仅加载根节点)。 */
  initializeList: () => Promise<void>;
  /** 加载指定父节点的子节点并合并入列表。 */
  fetchChildren: (parentId: string) => Promise<void>;
  /** 解析并加载特定节点的完整路径 (用于深层链接)。 */
  resolvePath: (targetId: string) => Promise<void>;

  /** 创建一个新条目。 */
  createItem: (data: TCreate) => Promise<TItem | null>;
  /** 更新一个条目的数据。 */
  updateItem: (id: string, data: TUpdate) => Promise<void>;
  /** 删除一个条目。 */
  deleteItem: (id: string) => Promise<void>;
  /** 移动条目位置。 */
  moveItem: (req: MoveRequest) => Promise<void>;
  /** (可选) 复制一个条目。 */
  duplicateItem?: (id: string) => Promise<TItem | null>;
}

// --- Composable Implementation ---

/**
 * 一个通用的 Composable，用于管理 Pinia Store 中的树形数据结构。
 * 封装了增量懒加载、移动、CRUD 等通用逻辑。
 */
export function useTreeStoreActions<TItem extends BaseTreeItem, TCreate, TUpdate>(
  options: TreeStoreActionsOptions<TItem, TCreate, TUpdate>
): UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  const { items, api, onDeleteItem } = options;

  const isLoading = ref(false);
  const loadedFolderIds = ref(new Set<string>());
  const loadingFolders = ref(new Set<string>());

  /**
   * 初始化列表，默认加载根目录内容。
   */
  async function initializeList() {
    isLoading.value = true;
    try {
      // 重置状态
      items.value = [];
      loadedFolderIds.value.clear();
      loadingFolders.value.clear();

      const rootItems = await api.fetchChildren(['root']);
      items.value = rootItems;
      loadedFolderIds.value.add('root');
    } catch (error) {
      console.error('Failed to initialize list:', error);
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * 加载指定父节点的子节点。
   * 采用替换策略：移除列表中该父节点下的旧子节点，插入新获取的子节点。
   */
  async function fetchChildren(parentId: string) {
    if (loadingFolders.value.has(parentId)) return;

    loadingFolders.value.add(parentId);
    try {
      const children = await api.fetchChildren([parentId]);

      // 1. 移除 items 中所有 parentId 为当前目标 ID 的旧项 (保持列表纯净)
      // 注意：这里不递归删除孙子节点，因为它们可能在 UI 上是折叠的，保留它们的数据可能有助于缓存
      // 但为了数据一致性，通常懒加载策略下，刷新父节点意味着重置其直接子级
      const filteredItems = items.value.filter(item => item.parentId !== parentId);

      // 2. 合并新数据
      items.value = [...filteredItems, ...children];

      // 3. 标记为已加载
      loadedFolderIds.value.add(parentId);
    } catch (error) {
      console.error(`Failed to fetch children for ${parentId}:`, error);
      // 加载失败时，确保不标记为已加载，以便重试
      loadedFolderIds.value.delete(parentId);
    } finally {
      loadingFolders.value.delete(parentId);
    }
  }

  /**
   * 通过链路回溯接口加载深层节点路径。
   * 主要用于将路径上的节点合并到当前列表中，确保树结构能正确渲染。
   */
  async function resolvePath(targetId: string) {
    if (!api.fetchLineage) {
      console.warn('resolvePath called but fetchLineage API is not provided.');
      return;
    }

    try {
      const lineage = await api.fetchLineage(targetId);

      // 使用 Map 进行去重合并 (Upsert)
      const itemMap = new Map(items.value.map(i => [i.id, i]));
      lineage.forEach(node => {
        itemMap.set(node.id, node);
      });

      items.value = Array.from(itemMap.values());

      // 注意：这里不自动标记 loadedFolderIds，因为 lineage 可能只包含路径节点而非全部兄弟节点。
      // UI 组件展开路径上的文件夹时，会触发 fetchChildren 来补全兄弟节点。
    } catch (error) {
      console.error(`Failed to resolve path for ${targetId}:`, error);
    }
  }

  async function createItem(data: TCreate): Promise<TItem | null> {
    try {
      const newItem = await api.create(data);
      items.value.push(newItem);

      // 如果新项是文件夹，初始化其加载状态
      if (newItem.itemType === 'folder') {
        loadedFolderIds.value.add(newItem.id); // 新文件夹默认为空，视为已加载
      }
      return newItem;
    } catch (error) {
      console.error('Failed to create item:', error);
      return null;
    }
  }

  async function updateItem(id: string, data: TUpdate) {
    try {
      const updatedItem = await api.update(id, data);
      const index = items.value.findIndex(item => item.id === id);
      if (index !== -1) {
        Object.assign(items.value[index], updatedItem);
      }
    } catch (error) {
      console.error(`Failed to update item ${id}:`, error);
    }
  }

  async function deleteItem(id: string) {
    const index = items.value.findIndex(item => item.id === id);
    if (index === -1) return;

    const itemToDelete = items.value[index];
    // 乐观 UI 更新
    items.value.splice(index, 1);

    try {
      await api.remove(id);
      if (onDeleteItem) {
        onDeleteItem(itemToDelete);
      }
    } catch (error) {
      console.error(`Failed to delete item ${id}:`, error);
      // 回滚
      items.value.splice(index, 0, itemToDelete);
      ElMessage.error('删除失败，已撤销操作');
    }
  }

  /**
   * 移动节点。
   * 成功后会自动刷新受影响的父节点（源父节点和目标父节点），以确保顺序一致性。
   */
  async function moveItem(req: MoveRequest) {
    // 1. 获取移动前的父节点 ID (用于后续刷新)
    // 假设批量移动时，所有项来自同一个父节点，或者我们只关心第一个项的父节点作为刷新目标
    const firstItemId = req.item_ids[0];
    const item = items.value.find(i => i.id === firstItemId);
    const oldParentId = item ? item.parentId : null;

    try {
      await api.move(req);

      // 2. 确定需要刷新的父节点集合
      const parentsToRefresh = new Set<string>();

      // 添加源父节点
      if (oldParentId) parentsToRefresh.add(oldParentId);
      else parentsToRefresh.add('root');

      // 添加目标父节点
      let targetParentId: string | null = null;
      if (req.action === 'inside') {
        targetParentId = req.reference_id;
      } else {
        // before 或 after，目标父节点与参考节点相同
        if (req.reference_id === 'root') {
          targetParentId = null;
        } else {
          const refNode = items.value.find(i => i.id === req.reference_id);
          targetParentId = refNode ? refNode.parentId : null;
        }
      }

      if (targetParentId) parentsToRefresh.add(targetParentId);
      else parentsToRefresh.add('root');

      // 3. 刷新受影响的父节点
      // 使用 Promise.all 并行刷新
      const refreshPromises = Array.from(parentsToRefresh).map(pid => fetchChildren(pid));
      await Promise.all(refreshPromises);

    } catch (error) {
      console.error('Failed to move items:', error);
      ElMessage.error('移动失败');
      // 移动失败可能导致 UI 顺序与服务器不一致，建议重新初始化或刷新相关节点
      // 这里简单处理为刷新源节点
      if (oldParentId) await fetchChildren(oldParentId);
    }
  }

  const duplicateItem = api.duplicate
    ? async (id: string): Promise<TItem | null> => {
        try {
          const newItem = await api.duplicate!(id);
          items.value.push(newItem);
          return newItem;
        } catch (error) {
          console.error(`Failed to duplicate item ${id}:`, error);
          return null;
        }
      }
    : undefined;

  const returnObject: UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> = {
    isLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList,
    fetchChildren,
    resolvePath,
    createItem,
    updateItem,
    deleteItem,
    moveItem,
  };

  if (duplicateItem) {
    returnObject.duplicateItem = duplicateItem;
  }

  return returnObject;
}
