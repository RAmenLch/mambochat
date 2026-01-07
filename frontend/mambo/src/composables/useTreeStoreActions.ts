// frontend/mambo/src/composables/useTreeStoreActions.ts

import { ref, type Ref } from 'vue';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import { ElMessage } from 'element-plus';

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
    // 简单的防重入和防重复加载
    if (loadingFolders.value.has(parentId)) return;
    if (loadedFolderIds.value.has(parentId)) return;

    loadingFolders.value.add(parentId);
    try {
      const children = await api.fetchChildren([parentId]);

      // 过滤旧数据防止 ID 冲突
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

  // [Fix Problem 3]: 深层路径解析 + 完整上下文加载
  async function resolvePath(targetId: string) {
    if (!api.fetchLineage) return;
    try {
      // 1. 获取目标 ID 回溯到 root 的所有节点
      const lineage = await api.fetchLineage(targetId);

      // 2. 先把这些节点放入 list，避免 UI 报错
      const itemMap = new Map(items.value.map(i => [i.id, i]));
      lineage.forEach(node => {
        itemMap.set(node.id, node);
      });
      items.value = Array.from(itemMap.values());

      // 3. 找出所有需要加载子项的“父文件夹”
      // 如果路径是 Root -> A -> B -> Target，我们需要加载 Root, A, B 的子项
      const parentIdsToLoad = new Set<string>();

      lineage.forEach(item => {
        // 如果它有父节点（非 Root），其父节点需要被加载（为了显示该 item 的兄弟）
        if (item.parentId && item.parentId !== 'root' && !loadedFolderIds.value.has(item.parentId)) {
          parentIdsToLoad.add(item.parentId);
        }
        // 如果它自己是文件夹，且未加载，也需要加载（为了显示它里面的内容）
        if (item.itemType === 'folder' && !loadedFolderIds.value.has(item.id)) {
          parentIdsToLoad.add(item.id);
        }
      });

      // 4. 并发加载缺失的层级
      if (parentIdsToLoad.size > 0) {
        await Promise.all(Array.from(parentIdsToLoad).map(pid => fetchChildren(pid)));
      }

    } catch (error) {
      console.error(`Failed to resolve path for ${targetId}:`, error);
    }
  }

  // ... (其余 create/update/move 代码保持之前优化过的版本)

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

  async function moveItem(req: MoveRequest) {
    const firstItemId = req.item_ids[0];
    const itemIndex = items.value.findIndex(i => i.id === firstItemId);
    const itemRef = items.value[itemIndex];
    if (itemIndex === -1) return;

    const originalState = { parentId: itemRef.parentId, sortOrder: itemRef.sortOrder };

    let targetParentId: string | null = null;
    let newSortOrder = itemRef.sortOrder;

    if (req.action === 'inside') {
      targetParentId = req.reference_id === 'root' ? null : req.reference_id;
      const siblings = items.value.filter(i => {
        const pId = targetParentId === 'root' ? null : targetParentId;
        const iP = i.parentId === 'root' ? null : i.parentId;
        return iP === pId && i.id !== itemRef.id;
      });
      newSortOrder = siblings.length > 0 ? Math.max(...siblings.map(s => s.sortOrder)) + 1024 : 0;
    } else {
      const refNode = items.value.find(i => i.id === req.reference_id);
      if (refNode) {
        targetParentId = refNode.parentId;
        newSortOrder = req.action === 'before' ? refNode.sortOrder - 0.5 : refNode.sortOrder + 0.5;
      }
    }

    itemRef.parentId = targetParentId;
    itemRef.sortOrder = newSortOrder;

    try {
      await api.move(req);
      const parentsToRefresh = new Set<string>();
      parentsToRefresh.add(originalState.parentId || 'root');
      parentsToRefresh.add(targetParentId || 'root');

      Array.from(parentsToRefresh).forEach(pid => loadedFolderIds.value.delete(pid));
      await Promise.all(Array.from(parentsToRefresh).map(pid => fetchChildren(pid)));
    } catch (error) {
      console.error('Failed to move items:', error);
      ElMessage.error('移动失败');
      Object.assign(itemRef, originalState); // Rollback
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
        } catch (error) { return null; }
      }
    : undefined;

  const returnObject: UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> = {
    isLoading, loadedFolderIds, loadingFolders, initializeList, fetchChildren, resolvePath,
    createItem, updateItem, deleteItem, moveItem,
  };
  if (duplicateItem) returnObject.duplicateItem = duplicateItem;

  return returnObject;
}
