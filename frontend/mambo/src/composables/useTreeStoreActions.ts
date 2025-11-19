// frontend/mambo/src/composables/useTreeStoreActions.ts

import { ref, type Ref } from 'vue';
import type { BaseTreeItem, TreeReorderEvent } from '@/api/types';
import { ElMessage } from 'element-plus';

// --- Interface Definitions ---

/**
 * 定义了此 Composable 所需的 API 服务函数集合的接口。
 * @template TItem 树节点的数据类型。
 * @template TCreate 创建新条目时所需的数据类型。
 * @template TUpdate 更新条目时所需的数据类型。
 */
interface TreeStoreApi<TItem, TCreate, TUpdate> {
  fetchAll: () => Promise<TItem[]>;
  create: (data: TCreate) => Promise<TItem>;
  update: (id: string, data: TUpdate) => Promise<TItem>;
  remove: (id: string) => Promise<void>;
  reorder: (updates: TreeReorderEvent[]) => Promise<void>;
  duplicate?: (id: string) => Promise<TItem>;
}

/**
 * `useTreeStoreActions` Composable 的配置选项接口。
 * @template TItem 树节点的数据类型。
 * @template TCreate 创建新条目时所需的数据类型。
 * @template TUpdate 更新条目时所需的数据类型。
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
 * @template TItem 树节点的数据类型。
 * @template TCreate 创建新条目时所需的数据类型。
 * @template TUpdate 更新条目时所需的数据类型。
 */
interface UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  /** 指示 fetch 操作是否正在进行的 Ref。 */
  isLoading: Ref<boolean>;
  /** 从服务器获取所有条目并填充 state。 */
  fetchItems: () => Promise<void>;
  /** 创建一个新条目，将其添加到 state 中，并返回该新条目。 */
  createItem: (data: TCreate) => Promise<TItem | null>;
  /** 在服务器和 state 中更新一个条目的数据。 */
  updateItem: (id: string, data: TUpdate) => Promise<void>;
  /** 从服务器和 state 中删除一个条目，采用乐观 UI 和本地回滚策略。 */
  deleteItem: (id: string) => Promise<void>;
  /** 对条目进行重排序，采用乐观 UI 和失败时全量重新获取的回滚策略。 */
  reorderItems: (updates: TreeReorderEvent[]) => Promise<void>;
  /** (可选) 复制一个条目，将其添加到 state 中，并返回该新条目。 */
  duplicateItem?: (id: string) => Promise<TItem | null>;
}

// --- Composable Implementation ---

/**
 * 一个通用的 Composable，用于管理 Pinia Store 中的树形数据结构。
 * 它封装了获取、创建、更新、删除和重排序条目的通用逻辑，
 * 包括乐观更新和错误处理。
 *
 * @param options 包含 state Ref 和 API 处理器的配置对象。
 * @returns 返回一个包含标准化 action 函数的对象。
 */
export function useTreeStoreActions<TItem extends BaseTreeItem, TCreate, TUpdate>(
  options: TreeStoreActionsOptions<TItem, TCreate, TUpdate>
): UseTreeStoreActionsReturn<TItem, TCreate, TUpdate> {
  const { items, api, onDeleteItem } = options;
  const isLoading = ref(false);

  async function fetchItems() {
    isLoading.value = true;
    try {
      items.value = await api.fetchAll();
    } catch (error) {
      console.error('Failed to fetch items:', error);
      // 错误已由全局拦截器处理，此处不再显示消息
    } finally {
      isLoading.value = false;
    }
  }

  async function createItem(data: TCreate): Promise<TItem | null> {
    try {
      const newItem = await api.create(data);
      items.value.push(newItem);
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
        // 使用 Object.assign 确保响应性
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
      // 成功后，如果提供了回调，则执行副作用
      if (onDeleteItem) {
        onDeleteItem(itemToDelete);
      }
    } catch (error) {
      console.error(`Failed to delete item ${id}:`, error);
      // 失败时执行本地回滚
      items.value.splice(index, 0, itemToDelete);
      ElMessage.error('删除失败，已撤销操作');
    }
  }

  async function reorderItems(updates: TreeReorderEvent[]) {
    // 乐观 UI 更新
    updates.forEach(update => {
      const item = items.value.find(c => c.id === update.id);
      if (item) {
        item.parentId = update.parentId;
        item.sortOrder = update.sortOrder;
      }
    });
    // 对列表进行重新排序以反映 UI 变化
    items.value.sort((a, b) => a.sortOrder - b.sortOrder);

    try {
      await api.reorder(updates);
    } catch (error) {
      console.error('Failed to reorder items:', error);
      // 失败时通过重新获取全量数据进行回滚
      ElMessage.error('排序失败，正在从服务器恢复...');
      await fetchItems();
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
    fetchItems,
    createItem,
    updateItem,
    deleteItem,
    reorderItems,
  };

  if (duplicateItem) {
    returnObject.duplicateItem = duplicateItem;
  }

  return returnObject;
}
