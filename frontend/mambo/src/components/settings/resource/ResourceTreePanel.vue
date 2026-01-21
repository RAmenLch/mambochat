<!-- frontend/mambo/src/components/settings/resource/ResourceTreePanel.vue -->
<template>
  <el-aside width="300px" class="resource-tree-panel">
    <ExplorerTree
      ref="treeRef"
      :data="data"
      :current-id="currentId"
      :is-loading="isLoading"
      :loading-folder-ids="loadingFolders"
      folder-item-type="folder"
      persistence-key="mambo_resource_folder_expanded_state"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
      @move="handleMove"
      @node-expand="handleNodeExpand"
    >
      <template #header>
        <div class="panel-header">
          <h4>资源列表</h4>
        </div>
      </template>

      <template #item-icon="{ data: itemData }">
        <el-icon>
          <!-- 优先匹配知识库类型 -->
          <Collection v-if="itemData.resourceType === 'knowledge_base'" />
          <Folder v-else-if="itemData.itemType === 'folder'" />
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
          <el-dropdown-item command="newKB"><el-icon><Collection /></el-icon>新建知识库</el-dropdown-item>
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
import { onMounted, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import {
  Folder,
  Document,
  DocumentAdd,
  FolderAdd,
  EditPen,
  Delete,
  Memo,
  Collection
} from '@element-plus/icons-vue';

import { useResourceStore } from '@/stores/resourceStore';
import { useProviderStore } from '@/stores/providerStore';
import { createKnowledgeBase } from '@/api/kbService';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';
import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog from '@/components/common/EntityFormDialog.vue';
import type { SelectConfigOption } from '@/components/common/EntityFormDialog.vue';

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
const providerStore = useProviderStore();
const { resources, loadingFolders } = storeToRefs(resourceStore);

// --- Constants ---
const creatableResourceTypes: { value: ResourceType, label: string }[] = [
  { value: 'system_prompt', label: '系统提示词' },
  { value: 'submessage_template', label: '消息模板' },
];

const DEFAULT_SUBMESSAGE_ATTRIBUTES = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: true,
};

// --- Computed Options ---

// 计算可用的 Embedding 模型选项，按服务商分组
const embeddingModelOptions = computed<SelectConfigOption[]>(() => {
  const models = providerStore.allModels.filter(m => m.model_type === 'embedding');
  const groups: Record<string, { label: string, options: { label: string, value: string }[] }> = {};

  models.forEach(m => {
    const providerName = providerStore.providers.find(p => p.id === m.providerId)?.name || 'Unknown Provider';
    if (!groups[providerName]) {
      groups[providerName] = { label: providerName, options: [] };
    }
    groups[providerName].options.push({ label: m.name, value: m.id });
  });

  return Object.values(groups);
});

// --- Tree Controller Logic ---
const {
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
} = useTreeController<Resource, ResourceCreate, ResourceUpdate>({
  items: resources,
  crudHandlers: {
    createItem: resourceStore.addResourceItem,
    updateItem: resourceStore.updateResourceItem,
    deleteItem: async (id: string) => {
      await resourceStore.deleteResourceItem(id);
      emit('item-deleted', id);
    },
    moveItem: resourceStore.moveResourceItem,
  },
  onExpand: resourceStore.fetchResourceChildren,
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
      case 'newKB':
        return {
          title: '新建知识库',
          initialName: '新的知识库',
          selectConfig: {
            label: '嵌入模型',
            options: embeddingModelOptions.value,
            // 尝试自动选中第一个可用的模型
            initialValue: embeddingModelOptions.value.length > 0
              ? (embeddingModelOptions.value[0] as any).options?.[0]?.value
              : undefined
          }
        };
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

    let newItem: Resource | null = null;

    if (dialogPayload.type === 'newResource') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'resource',
        resourceType: formPayload.selectValue as ResourceType,
        parentId: dialogPayload.parentId,
        initial_content: '',
        initial_attributes: formPayload.selectValue === 'submessage_template' ? { ...DEFAULT_SUBMESSAGE_ATTRIBUTES } : undefined,
      });
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId,
      });
    } else if (dialogPayload.type === 'newKB') {
      // 校验模型选择
      if (!formPayload.selectValue) {
        ElMessage.warning('创建知识库必须选择一个嵌入模型');
        return null;
      }

      // 知识库创建逻辑：调用专用服务接口
      newItem = await createKnowledgeBase({
        name: formPayload.name,
        parent_id: dialogPayload.parentId,
        embedding_model_id: formPayload.selectValue // 必填，从 Select 获取
      });

      // 手动将新知识库同步到 Store 列表，保持视图一致性
      if (newItem) {
        resourceStore.resources.push(newItem);
        if (newItem.itemType === 'folder') {
          resourceStore.loadedFolderIds.add(newItem.id);
        }
      }
    }

    if (newItem) {
      emit('item-created', newItem);
    }
    return newItem;
  }
});

// --- Lifecycle ---
onMounted(() => {
  // 初始化资源列表（加载根节点）
  resourceStore.initializeList();
  // 预加载服务商列表，以便创建知识库时有模型可选
  providerStore.fetchProviders();
});

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
