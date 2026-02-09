// frontend/mambo/src/composables/useTreeController.ts

import { ref, computed, type Ref, type ComputedRef, type CSSProperties } from 'vue';
import { ElMessage, ElMessageBox, type ElDropdown } from 'element-plus';
import type Node from 'element-plus/es/components/tree/src/model/node';

import { useContextMenu } from '@/composables/useContextMenu';
import { useDialogState } from '@/composables/useDialogState';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import type ExplorerTree from '@/components/common/ExplorerTree.vue';
import type { SelectConfigOption } from '@/components/common/EntityFormDialog.vue';

// --- Interface Definitions ---

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
 * 适配懒加载与节点移动。
 */
export interface CrudHandlers<T, TCreate, TUpdate> {
  createItem: (data: TCreate) => Promise<T | null>;
  updateItem: (id: string, data: TUpdate) => Promise<void>;
  deleteItem: (id: string) => Promise<void>;
  /** 移动节点 (替代 reorderItems) */
  moveItem: (req: MoveRequest) => Promise<void>;
  duplicateItem?: (id: string) => Promise<T | null>;
}

export interface DialogPayload<T> {
  type: string;
  targetItem?: T;
  parentId?: string | null;
}

export interface DialogConfirmPayload {
  name: string;
  selectValue?: string;
}

export interface TreeControllerOptions<T extends BaseTreeItem, TCreate, TUpdate> {
  items: Ref<T[]>;
  crudHandlers: CrudHandlers<T, TCreate, TUpdate>;
  getDialogProps: (payload: DialogPayload<T>) => EntityFormDialogProps;
  handleDialogConfirm: (
    dialogPayload: DialogPayload<T>,
    formPayload: DialogConfirmPayload
  ) => Promise<T | null | void>;
  /** (可选) 节点展开时的回调，用于触发懒加载 */
  onExpand?: (parentId: string) => Promise<void>;
}

export interface UseTreeControllerReturn<T> {
  treeRef: Ref<InstanceType<typeof ExplorerTree> | undefined>;
  contextMenuRef: Ref<InstanceType<typeof ElDropdown> | undefined>;
  contextMenuItem: Ref<T | null>;
  contextMenuPosition: CSSProperties;
  dialogState: ReturnType<typeof useDialogState<DialogPayload<T>>>;
  dialogProps: ComputedRef<EntityFormDialogProps>;

  /** 处理节点拖拽移动事件 */
  handleMove: (req: MoveRequest) => Promise<void>;
  /** 处理节点展开事件 (懒加载) */
  handleNodeExpand: (data: BaseTreeItem) => void;

  handleNodeContextMenu: (event: MouseEvent, data: BaseTreeItem, node: Node) => void;
  openRootContextMenu: (event: MouseEvent) => void;
  handleMenuCommand: (command: string) => void;
  onDialogConfirm: (payload: DialogConfirmPayload) => Promise<void>;
}

/**
 * 一个通用的 Composable，封装了树形结构数据的标准交互逻辑。
 * 包括右键菜单、新建/重命名/删除弹窗、节点移动、懒加载触发等功能。
 */
export function useTreeController<T extends BaseTreeItem, TCreate, TUpdate>(
  options: TreeControllerOptions<T, TCreate, TUpdate>
): UseTreeControllerReturn<T> {
  const { items, crudHandlers, getDialogProps, handleDialogConfirm: handleDialogConfirmCallback, onExpand } = options;

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
      await crudHandlers.deleteItem(item.id);
      ElMessage.success('删除成功');
    } catch {
      /* User canceled the action */
    }
  };

  const handleDuplicate = async (item: T) => {
    if (!crudHandlers.duplicateItem) {
      console.warn('Duplicate handler is not implemented.');
      return;
    }
    const newItem = await crudHandlers.duplicateItem(item.id);
    if (newItem) {
      ElMessage.success('复制成功');
      await treeRef.value?.scrollToKey(newItem.id);
    }
  };

  // --- Event Handlers for Template Binding ---

  /**
   * 处理从 ExplorerTree 传来的移动请求。
   */
  const handleMove = async (req: MoveRequest) => {
    await crudHandlers.moveItem(req);
  };

  /**
   * 处理节点展开，触发外部提供的懒加载逻辑。
   */
  const handleNodeExpand = (data: BaseTreeItem) => {
    if (onExpand) {
      onExpand(data.id);
    }
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
    const parentId = item ? (item.itemType === 'folder' ? item.id : item.parentId) : null;

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
      default:
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

    if (newItem && typeof newItem === 'object' && 'id' in newItem) {
      ElMessage.success('创建成功');
      await treeRef.value?.scrollToKey(newItem.id);
    }
  };

  return {
    treeRef,
    contextMenuRef,
    contextMenuItem,
    contextMenuPosition,
    dialogState,
    dialogProps,
    handleMove,
    handleNodeExpand,
    handleNodeContextMenu,
    openRootContextMenu,
    handleMenuCommand,
    onDialogConfirm,
  };
}
