<template>
  <el-aside width="300px" class="resource-tree-panel">
    <ExplorerTree
      ref="treeRef"
      :data="data"
      :current-id="currentId"
      :is-loading="isLoading"
      folder-item-type="folder"
      persistence-key="mambo_resource_folder_expanded_state"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
      @reorder="handleReorder"
    >
      <template #header>
        <div class="panel-header">
          <h4>资源列表</h4>
        </div>
      </template>

      <template #item-icon="{ data: itemData }">
        <el-icon>
          <Folder v-if="itemData.itemType === 'folder'" />
          <Memo v-else-if="itemData.resourceType === 'submessage_template'" />
          <Document v-else />
        </el-icon>
      </template>
    </ExplorerTree>
  </el-aside>

  <!-- Context Menu -->
  <el-dropdown
    ref="contextMenuRef"
    trigger="contextmenu"
    @command="handleMenuCommand"
    popper-class="no-animation-popper"
  >
    <span :style="contextMenuPosition" />
    <template #dropdown>
      <el-dropdown-menu>
        <template v-if="!contextMenuItem || contextMenuItem.itemType === 'folder'">
          <el-dropdown-item command="newResource"><el-icon><DocumentAdd /></el-icon>新建资源</el-dropdown-item>
          <el-dropdown-item command="newFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
        </template>
        <template v-if="contextMenuItem">
          <el-dropdown-item command="rename" :divided="!contextMenuItem || contextMenuItem.itemType === 'folder'"><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
          <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
        </template>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- Dialogs -->
  <EntityFormDialog
    v-model:visible="dialogState.visible.value"
    :title="dialogProps.title"
    :initial-name="dialogProps.initialName"
    :select-config="dialogProps.selectConfig"
    @confirm="onDialogConfirm"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { Folder, Document, DocumentAdd, FolderAdd, EditPen, Delete, Memo } from '@element-plus/icons-vue';

import { useResourceStore } from '@/stores/resourceStore';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';
import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog from '@/components/common/EntityFormDialog.vue';

import type {
  Resource,
  ResourceCreate,
  ResourceUpdate,
  ResourceType,
  BaseTreeItem,
} from '@/api/types';

// --- Props & Emits ---

defineProps<{
  data: Resource[];
  currentId: string | null;
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'node-click', data: BaseTreeItem): void;
  (e: 'item-created', data: Resource): void;
  (e: 'item-deleted', id: string): void;
}>();

// --- Store ---
const resourceStore = useResourceStore();
const { resources } = storeToRefs(resourceStore);

// --- Constants ---
const creatableResourceTypes: { value: ResourceType, label: string }[] = [
  { value: 'system_prompt', label: 'System Prompt' },
  { value: 'submessage_template', label: 'SubMessage 模板' },
];

const DEFAULT_SUBMESSAGE_ATTRIBUTES = {
  context_participation_length: 1,
  is_collapsed: false,
};

// --- Tree Controller Logic ---
const {
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
} = useTreeController<Resource, ResourceCreate, ResourceUpdate>({
  items: resources,
  crudHandlers: {
    createItem: resourceStore.addResourceItem,
    updateItem: resourceStore.updateResourceItem,
    deleteItem: async (id: string) => {
      await resourceStore.deleteResourceItem(id);
      emit('item-deleted', id);
    },
    reorderItems: resourceStore.reorderResourceItems,
  },
  getDialogProps: (payload: DialogPayload<Resource>) => {
    switch (payload.type) {
      case 'rename':
        return { title: '重命名', initialName: payload.targetItem?.name || '' };
      case 'newResource':
        return {
          title: '新建资源',
          initialName: '新的资源',
          selectConfig: {
            label: '资源类型',
            options: creatableResourceTypes,
            initialValue: creatableResourceTypes[0].value,
          },
        };
      case 'newFolder':
        return { title: '新建文件夹', initialName: '新的文件夹' };
      default:
        return { title: '', initialName: '' };
    }
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Resource>,
    formPayload: DialogConfirmPayload
  ): Promise<Resource | null> => {
    if (dialogPayload.type === 'rename' && dialogPayload.targetItem) {
      await resourceStore.updateResourceItem(dialogPayload.targetItem.id, { name: formPayload.name });
      return null;
    }

    const sortOrder = calculateSortOrder(dialogPayload.parentId);
    let newItem: Resource | null = null;

    if (dialogPayload.type === 'newResource') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'resource',
        resourceType: formPayload.selectValue as ResourceType,
        parentId: dialogPayload.parentId,
        sortOrder,
        initial_content: '',
        initial_attributes: formPayload.selectValue === 'submessage_template' ? { ...DEFAULT_SUBMESSAGE_ATTRIBUTES } : undefined,
      });
      if (newItem) {
        emit('item-created', newItem);
      }
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId,
        sortOrder
      });
    }
    return newItem;
  }
});

// --- Helper Functions ---
const calculateSortOrder = (parentId: string | null = null): number => {
  return resources.value.filter(r => r.parentId === parentId).length;
};

// --- Handlers ---
function handleNodeClick(data: BaseTreeItem) {
  emit('node-click', data);
}
</script>

<style scoped>
.resource-tree-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color);
  background-color: var(--color-background-soft);
}

.panel-header {
  padding: 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: default;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
}

.delete-item {
  color: var(--el-color-danger);
}
</style>

<style>
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
