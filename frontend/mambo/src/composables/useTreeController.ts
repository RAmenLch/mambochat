// frontend/mambo/src/composables/useTreeController.ts

import { ref, computed, type Ref, type ComputedRef } from 'vue';
import { ElMessage, ElMessageBox, type ElDropdown } from 'element-plus';
/** Element Plus Tree 内部节点结构（避免依赖内部路径） */
interface ElTreeNode {
  data: Record<string, any>;
  parent: ElTreeNode | null;
  level: number;
  childNodes: ElTreeNode[];
}

import { useI18n } from 'vue-i18n';

import { useContextMenu } from '@/composables/useContextMenu';
import { useDialogState } from '@/composables/useDialogState';
import type { BaseTreeItem, MoveRequest } from '@/api/types';
import type ExplorerTree from '@/components/common/ExplorerTree.vue';
import type { SelectConfigOption } from '@/components/common/EntityFormDialog.vue';

// --- Interface Definitions ---

export interface EntityFormDialogProps {
  title: string;
  initialName?: string;
  showChatMode?: boolean;
  selectConfig?: {
    label: string;
    options: SelectConfigOption[];
    initialValue?: string;
  };
  agentSelectConfig?: {
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
  contextMenuPosition: Record<string, any>; // 修改：使用 Record 代替 CSSProperties
  dialogState: ReturnType<typeof useDialogState<DialogPayload<T>>>;
  dialogProps: ComputedRef<EntityFormDialogProps>;

  /** 处理节点拖拽移动事件 */
  handleMove: (req: MoveRequest) => Promise<void>;
  /** 处理节点展开事件 (懒加载) */
  handleNodeExpand: (data: BaseTreeItem) => void;

  handleNodeContextMenu: (event: MouseEvent, data: BaseTreeItem, node: any) => void;
  openRootContextMenu: (event: MouseEvent) => void;
  handleMenuCommand: (command: string) => Promise<T | null>; // 修改：返回 Promise<T | null>
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

  const { t } = useI18n();

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
      await ElMessageBox.confirm(
        t('common.dialog.confirmDelete', { name: item.name }),
        t('common.dialog.warning'),
        {
          confirmButtonText: t('common.action.confirmDelete'),
          cancelButtonText: t('common.action.cancel'),
          type: 'warning',
        }
      );
      await crudHandlers.deleteItem(item.id);
      ElMessage.success(t('common.msg.deleteSuccess'));
    } catch {
      /* User canceled the action */
    }
  };

  // 修改：返回 newItem 以便外部处理跳转
  const handleDuplicate = async (item: T): Promise<T | null> => {
    if (!crudHandlers.duplicateItem) {
      console.warn('Duplicate handler is not implemented.');
      return null;
    }
    const newItem = await crudHandlers.duplicateItem(item.id);
    if (newItem) {
      ElMessage.success(t('common.msg.duplicateSuccess'));
      await treeRef.value?.scrollToKey(newItem.id);
      return newItem;
    }
    return null;
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

  // 修改：异步函数，返回操作结果
  const handleMenuCommand = async (command: string): Promise<T | null> => {
    const item = contextMenuItem.value;
    const parentId = item ? (item.itemType === 'folder' ? item.id : item.parentId) : null;

    switch (command) {
      case 'rename':
        if (item) dialogState.open({ type: 'rename', targetItem: item });
        return null;
      case 'delete':
        if (item) await handleDelete(item);
        return null;
      case 'duplicate':
        if (item) return await handleDuplicate(item);
        return null;
      default:
        if (command.startsWith('new')) {
          dialogState.open({ type: command, parentId });
          return null;
        } else {
          console.warn(`Unknown context menu command: ${command}`);
          return null;
        }
    }
  };

  const onDialogConfirm = async (formPayload: DialogConfirmPayload) => {
    const state = dialogState.payload.value;
    if (!state) return;

    const newItem = await handleDialogConfirmCallback(state, formPayload);

    if (newItem && typeof newItem === 'object' && 'id' in newItem) {
      ElMessage.success(t('common.msg.createSuccess'));
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
