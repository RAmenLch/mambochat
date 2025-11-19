// frontend/mambo/src/composables/useTreeController.ts

import { ref, computed, type Ref, type ComputedRef, type CSSProperties } from 'vue';
import { ElMessage, ElMessageBox, type ElDropdown } from 'element-plus';
import type Node from 'element-plus/es/components/tree/src/model/node';

import { useContextMenu } from '@/composables/useContextMenu';
import { useDialogState } from '@/composables/useDialogState';
import type { BaseTreeItem, TreeReorderEvent } from '@/api/types';
import type ExplorerTree from '@/components/common/ExplorerTree.vue';
import type { SelectConfigOption } from '@/components/common/EntityFormDialog.vue';

// --- Interface Definitions ---

/**
 * 在此 Composable 内部定义与 EntityFormDialog.vue props 匹配的类型接口。
 * 这避免了修改 EntityFormDialog.vue 文件来导出类型，从而遵循了重构计划。
 */
export interface EntityFormDialogProps {
  title: string;
  initialName?: string;
  selectConfig?: {
    label: string;
    options: SelectConfigOption[];
    initialValue?: string;
  };
}

/**
 * 定义了一套标准的 CRUD 操作接口，Composable 将通过此接口与外部 Store 交互。
 * @template T - 树节点的数据类型 (e.g., Chat, Resource)。
 * @template TCreate - 创建新条目时 API 需要的数据类型。
 * @template TUpdate - 更新条目时 API 需要的数据类型。
 */
export interface CrudHandlers<T, TCreate, TUpdate> {
  /** 创建一个新条目 */
  create: (data: TCreate) => Promise<T | null>;
  /** 更新一个现有条目 */
  update: (id: string, data: TUpdate) => Promise<void>;
  /** 删除一个条目 */
  remove: (id: string) => Promise<void>;
  /** 批量更新条目的排序和层级 */
  reorder: (updates: TreeReorderEvent[]) => Promise<void>;
  /** (可选) 复制一个条目 */
  duplicate?: (id: string) => Promise<T | null>;
}

/**
 * 定义了弹窗载荷的数据结构。
 * @template T - 树节点的数据类型。
 */
export interface DialogPayload<T> {
  type: string; // e.g., 'rename', 'newChat', 'newFolder'
  targetItem?: T;
  parentId?: string | null;
}

/**
 * 定义了 EntityFormDialog 组件 'confirm' 事件的载荷结构。
 */
export interface DialogConfirmPayload {
  name: string;
  selectValue?: string;
}

/**
 * `useTreeController` Composable 的配置选项接口。
 * @template T - 树节点的数据类型。
 * @template TCreate - 创建新条目时 API 需要的数据类型。
 * @template TUpdate - 更新条目时 API 需要的数据类型。
 */
export interface TreeControllerOptions<T extends BaseTreeItem, TCreate, TUpdate> {
  /** 树形数据的扁平化列表源 */
  items: Ref<T[]>;
  /** CRUD 操作的处理器集合 */
  crudHandlers: CrudHandlers<T, TCreate, TUpdate>;
  /** 根据弹窗载荷动态生成弹窗属性的回调函数 */
  getDialogProps: (payload: DialogPayload<T>) => EntityFormDialogProps;
  /**
   * 处理弹窗确认逻辑的回调函数。
   * @returns 返回创建成功的新条目，用于后续的 UI 操作（如滚动到视图）。
   */
  handleDialogConfirm: (
    dialogPayload: DialogPayload<T>,
    formPayload: DialogConfirmPayload
  ) => Promise<T | null | void>;
}

/**
 * `useTreeController` Composable 的返回值接口。
 * @template T - 树节点的数据类型。
 */
export interface UseTreeControllerReturn<T> {
  treeRef: Ref<InstanceType<typeof ExplorerTree> | undefined>;
  contextMenuRef: Ref<InstanceType<typeof ElDropdown> | undefined>;
  contextMenuItem: Ref<T | null>;
  contextMenuPosition: CSSProperties;
  dialogState: ReturnType<typeof useDialogState<DialogPayload<T>>>;
  dialogProps: ComputedRef<EntityFormDialogProps>;
  handleReorder: (updates: TreeReorderEvent[]) => Promise<void>;
  handleNodeContextMenu: (event: MouseEvent, data: BaseTreeItem, node: Node) => void;
  openRootContextMenu: (event: MouseEvent) => void;
  handleMenuCommand: (command: string) => void;
  onDialogConfirm: (payload: DialogConfirmPayload) => Promise<void>;
}

/**
 * 一个通用的 Composable，封装了树形结构数据的标准交互逻辑。
 * 包括右键菜单、新建/重命名/删除弹窗、拖拽排序等功能。
 *
 * @param options - Composable 的配置对象，用于将其与具体的业务逻辑（Store）解耦。
 * @returns 返回一组响应式状态和事件处理器，可直接在组件模板和脚本中使用。
 */
export function useTreeController<T extends BaseTreeItem, TCreate, TUpdate>(
  options: TreeControllerOptions<T, TCreate, TUpdate>
): UseTreeControllerReturn<T> {
  const { items, crudHandlers, getDialogProps, handleDialogConfirm: handleDialogConfirmCallback } = options;

  // --- Refs & State ---
  const treeRef = ref<InstanceType<typeof ExplorerTree>>();
  const contextMenuRef = ref<InstanceType<typeof ElDropdown>>();
  const { contextMenuItem, contextMenuPosition, handleContextMenu } = useContextMenu<T>();
  const dialogState = useDialogState<DialogPayload<T>>();

  // --- Computed Properties ---
  const dialogProps = computed(() => {
    if (!dialogState.payload.value) {
      return { title: '', initialName: '' };
    }
    return getDialogProps(dialogState.payload.value);
  });

  // --- Core Action Handlers ---
  const handleDelete = async (item: T) => {
    try {
      await ElMessageBox.confirm(`确定要删除 "${item.name}" 吗？此操作不可恢复。`, '警告', {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await crudHandlers.remove(item.id);
      ElMessage.success('删除成功');
    } catch {
      /* User canceled the action */
    }
  };

  const handleDuplicate = async (item: T) => {
    if (!crudHandlers.duplicate) {
      console.warn('Duplicate handler is not implemented.');
      return;
    }
    const newItem = await crudHandlers.duplicate(item.id);
    if (newItem) {
      ElMessage.success('复制成功');
      await treeRef.value?.scrollToKey(newItem.id);
    }
  };

  // --- Event Handlers for Template Binding ---
  const handleReorder = async (updates: TreeReorderEvent[]) => {
    await crudHandlers.reorder(updates);
  };

  const openContextMenu = (event: MouseEvent, data: T | null) => {
    handleContextMenu(event, data, contextMenuRef);
  };

  const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem) => {
    openContextMenu(event, data as T);
  };

  const openRootContextMenu = (event: MouseEvent) => {
    openContextMenu(event, null);
  };

  const handleMenuCommand = (command: string) => {
    const item = contextMenuItem.value;
    // 统一确定 parentId：右键文件夹时，新项在其内部；右键文件时，新项与其同级；右键空白处，新项在根级。
    const parentId = item ? (item.itemType === 'folder' ? item.id : item.parentId) : null;

    // 命令分发
    switch (command) {
      case 'rename':
        if (item) dialogState.open({ type: 'rename', targetItem: item });
        break;
      case 'delete':
        if (item) handleDelete(item);
        break;
      case 'duplicate':
        if (item) handleDuplicate(item);
        break;
      // 动态处理所有 'new' 类型的命令
      default:
        // 约定：所有新建操作的 command 都以 'new' 开头
        if (command.startsWith('new')) {
          dialogState.open({ type: command, parentId });
        } else {
          console.warn(`Unknown context menu command: ${command}`);
        }
        break;
    }
  };

  const onDialogConfirm = async (formPayload: DialogConfirmPayload) => {
    const state = dialogState.payload.value;
    if (!state) return;

    const newItem = await handleDialogConfirmCallback(state, formPayload);

    // 只有当回调返回一个有效的 item 对象时，才执行后续 UI 操作
    if (newItem && typeof newItem === 'object' && 'id' in newItem) {
      ElMessage.success('创建成功');
      await treeRef.value?.scrollToKey(newItem.id);
    }

    // 对于重命名等不返回新条目的操作，成功消息应在具体实现的回调中处理
  };

  return {
    treeRef,
    contextMenuRef,
    contextMenuItem,
    contextMenuPosition,
    dialogState,
    dialogProps,
    handleReorder,
    handleNodeContextMenu,
    openRootContextMenu,
    handleMenuCommand,
    onDialogConfirm,
  };
}
