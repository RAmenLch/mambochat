// frontend/mambo/src/composables/useTreeStoreActions.ts

import { ref, type Ref } from 'vue';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';

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
  const { t } = useI18n();

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
      if (parentId !== 'root') {
        const parentExists = items.value.some((item) => item.id === parentId)
        if (!parentExists) {
          console.log(
            `[TreeStore] Parent ${parentId} was removed while fetching children. Discarding results.`,
          )
          return
        }
      }
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

      const parentIdsToLoad = new Set<string>();

      lineage.forEach(item => {
        if (item.parentId && item.parentId !== 'root' && !loadedFolderIds.value.has(item.parentId)) {
          parentIdsToLoad.add(item.parentId);
        }
        if (item.itemType === 'folder' && !loadedFolderIds.value.has(item.id)) {
          parentIdsToLoad.add(item.id);
        }
      });

      if (parentIdsToLoad.size > 0) {
        await Promise.all(Array.from(parentIdsToLoad).map(pid => fetchChildren(pid)));
      }

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
    const targetItem = items.value.find(item => item.id === id);
    if (!targetItem) return;

    const idsToRemove = new Set<string>();
    idsToRemove.add(id);

    let foundNew = true;
    while (foundNew) {
      foundNew = false;
      for (const item of items.value) {
        if (item.parentId && idsToRemove.has(item.parentId) && !idsToRemove.has(item.id)) {
          idsToRemove.add(item.id);
          foundNew = true;
        }
      }
    }

    const itemsToDelete = items.value.filter(item => idsToRemove.has(item.id));

    items.value = items.value.filter(item => !idsToRemove.has(item.id));

    idsToRemove.forEach(removeId => {
      loadedFolderIds.value.delete(removeId);
      loadingFolders.value.delete(removeId);
    });

    try {
      await api.remove(id);
      if (onDeleteItem && targetItem) {
        onDeleteItem(targetItem);
      }
    } catch (error) {
      console.error('Failed to delete item:', error);
      items.value.push(...itemsToDelete);
      ElMessage.error(t('common.error.deleteFailed'));
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
      ElMessage.error(t('common.error.moveFailed'));
      Object.assign(itemRef, originalState);
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
