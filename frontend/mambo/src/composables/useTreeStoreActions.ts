// frontend/mambo/src/composables/useTreeStoreActions.ts

import { ref, type Ref } from 'vue';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import { ElMessage } from 'element-plus';

// --- Interface Definitions ---

interface TreeStoreApi<TItem, TCreate, TUpdate> {
  fetchChildren: (parentIds: string[]) => Promise<TItem[]>;
  fetchLineage?: (id: string) => Promise<TItem[]>;
  create: (data: TCreate) => Promise<TItem>;
  update: (id: string, data: TUpdate) => Promise<TItem>;
  remove: (id: string) => Promise<void>;
  move: (req: MoveRequest) => Promise<void>;
  duplicate?: (id: string) => Promise<TItem>;
}

interface TreeStoreActionsOptions<TItem extends BaseTreeItem, TCreate, TUpdate> {
  items: Ref<TItem[]>;
  api: TreeStoreApi<TItem, TCreate, TUpdate>;
  onDeleteItem?: (deletedItem: TItem) => void;
}

interface UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  isLoading: Ref<boolean>;
  loadedFolderIds: Ref<Set<string>>;
  loadingFolders: Ref<Set<string>>;
  initializeList: () => Promise<void>;
  fetchChildren: (parentId: string) => Promise<void>;
  resolvePath: (targetId: string) => Promise<void>;
  createItem: (data: TCreate) => Promise<TItem | null>;
  updateItem: (id: string, data: TUpdate) => Promise<void>;
  deleteItem: (id: string) => Promise<void>;
  moveItem: (req: MoveRequest) => Promise<void>;
  duplicateItem?: (id: string) => Promise<TItem | null>;
}

// --- Composable Implementation ---

export function useTreeStoreActions<TItem extends BaseTreeItem, TCreate, TUpdate>(
  options: TreeStoreActionsOptions<TItem, TCreate, TUpdate>
): UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  const { items, api, onDeleteItem } = options;

  const isLoading = ref(false);
  const loadedFolderIds = ref(new Set<string>());
  const loadingFolders = ref(new Set<string>());

  async function initializeList() {
    isLoading.value = true;
    try {
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

  async function fetchChildren(parentId: string) {
    if (loadingFolders.value.has(parentId)) return;
    if (loadedFolderIds.value.has(parentId)) return;

    loadingFolders.value.add(parentId);
    try {
      const children = await api.fetchChildren([parentId]);

      // [修复逻辑 1]: 增强过滤，避免重复 Key
      const filteredItems = items.value.filter(item => {
        if (parentId === 'root') {
          return item.parentId !== 'root' && item.parentId !== null;
        }
        return item.parentId !== parentId;
      });

      items.value = [...filteredItems, ...children];
      loadedFolderIds.value.add(parentId);
    } catch (error) {
      console.error(`Failed to fetch children for ${parentId}:`, error);
      loadedFolderIds.value.delete(parentId);
    } finally {
      loadingFolders.value.delete(parentId);
    }
  }

  async function resolvePath(targetId: string) {
    if (!api.fetchLineage) return;
    try {
      const lineage = await api.fetchLineage(targetId);
      const itemMap = new Map(items.value.map(i => [i.id, i]));
      lineage.forEach(node => {
        itemMap.set(node.id, node);
      });
      items.value = Array.from(itemMap.values());
    } catch (error) {
      console.error(`Failed to resolve path for ${targetId}:`, error);
    }
  }

  async function createItem(data: TCreate): Promise<TItem | null> {
    try {
      const newItem = await api.create(data);
      items.value.push(newItem);
      if (newItem.itemType === 'folder') {
        loadedFolderIds.value.add(newItem.id);
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
    items.value.splice(index, 1);
    try {
      await api.remove(id);
      if (onDeleteItem) onDeleteItem(itemToDelete);
    } catch (error) {
      items.value.splice(index, 0, itemToDelete);
      ElMessage.error('删除失败，已撤销操作');
    }
  }

  /**
   * 移动节点。
   * 包含乐观更新逻辑：同时预判修改 parentId 和 sortOrder，确保 UI 不回弹。
   */
  async function moveItem(req: MoveRequest) {
    const firstItemId = req.item_ids[0];
    const itemIndex = items.value.findIndex(i => i.id === firstItemId);
    if (itemIndex === -1) return;

    // 1. 保存旧状态用于回滚
    const itemRef = items.value[itemIndex];
    const originalState = {
      parentId: itemRef.parentId,
      sortOrder: itemRef.sortOrder
    };

    let targetParentId: string | null = null;
    let newSortOrder = itemRef.sortOrder;

    // 2. 计算目标位置和估算新的 sortOrder
    // 我们使用简单的数学估算（+/- 0.5）来欺骗本地排序，等后端刷新后会变成正确的整数/序号
    if (req.action === 'inside') {
      targetParentId = req.reference_id === 'root' ? null : req.reference_id;

      // 移入内部通常是追加到最后，找到当前最大的 sortOrder
      const siblings = items.value.filter(i => {
        const pId = targetParentId === 'root' ? null : targetParentId;
        const iP = i.parentId === 'root' ? null : i.parentId;
        return iP === pId && i.id !== itemRef.id;
      });

      if (siblings.length > 0) {
        const maxOrder = Math.max(...siblings.map(s => s.sortOrder));
        newSortOrder = maxOrder + 1024; // 加上一个大数确保排在最后
      } else {
        newSortOrder = 0;
      }

    } else {
      // before 或 after
      const refNode = items.value.find(i => i.id === req.reference_id);
      if (refNode) {
        targetParentId = refNode.parentId;
        if (req.action === 'before') {
          // 插在参考节点前面：比它小一点点
          newSortOrder = refNode.sortOrder - 0.5;
        } else {
          // 插在参考节点后面：比它大一点点
          newSortOrder = refNode.sortOrder + 0.5;
        }
      } else {
        targetParentId = null;
      }
    }

    // 3. [关键修复] 乐观更新：同时修改 parentId 和 sortOrder
    itemRef.parentId = targetParentId;
    itemRef.sortOrder = newSortOrder;

    try {
      await api.move(req);

      // 4. API 成功后，刷新相关父节点以获取后端计算的精确 sortOrder
      const parentsToRefresh = new Set<string>();

      const oldP = originalState.parentId ? originalState.parentId : 'root';
      const newP = targetParentId ? targetParentId : 'root';

      parentsToRefresh.add(oldP);
      parentsToRefresh.add(newP);

      const parentsArray = Array.from(parentsToRefresh);
      parentsArray.forEach(pid => loadedFolderIds.value.delete(pid));

      await Promise.all(parentsArray.map(pid => fetchChildren(pid)));

    } catch (error) {
      console.error('Failed to move items:', error);
      ElMessage.error('移动失败');

      // 5. 失败回滚
      const rollbackItem = items.value.find(i => i.id === firstItemId);
      if (rollbackItem) {
        rollbackItem.parentId = originalState.parentId;
        rollbackItem.sortOrder = originalState.sortOrder;
      }

      // 刷新源目录恢复 UI
      const sourceParent = originalState.parentId || 'root';
      loadedFolderIds.value.delete(sourceParent);
      await fetchChildren(sourceParent);
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
