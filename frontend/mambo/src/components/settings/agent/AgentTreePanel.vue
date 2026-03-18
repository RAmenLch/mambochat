<!-- frontend/mambo/src/components/settings/agent/AgentTreePanel.vue -->
<template>
  <el-aside width="300px" class="agent-tree-panel">
    <ExplorerTree
      ref="treeRef"
      :data="treeData"
      :current-id="currentAgentId"
      :is-loading="isAgentListLoading"
      :loading-folder-ids="loadingFolders"
      folder-item-type="folder"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
      @move="handleMove"
      @node-expand="handleNodeExpand"
    >
      <template #header>
        <div class="panel-header">
          <h4>{{ $t('agent.tree.list') }}</h4>
          <el-dropdown trigger="click" @command="handleHeaderCommand">
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="newAgent"><el-icon><User /></el-icon>{{ $t('agent.tree.newAgent') }}</el-dropdown-item>
                <el-dropdown-item command="newFolder"><el-icon><FolderAdd /></el-icon>{{ $t('agent.tree.newFolder') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>

      <template #item-icon="{ data }">
        <el-icon v-if="data.itemType === 'folder'">
          <Folder />
        </el-icon>
        <template v-else>
          <el-avatar
            v-if="(data as unknown as Agent).agentAvatarUrl"
            :size="18"
            :src="(data as unknown as Agent).agentAvatarUrl"
            class="tree-agent-avatar"
          />
          <el-icon v-else><User /></el-icon>
        </template>
      </template>
    </ExplorerTree>

    <el-dropdown ref="contextMenuRef" trigger="contextmenu" @command="handleMenuCommand" popper-class="no-animation-popper">
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newAgent">
            <el-icon><Plus /></el-icon>{{ $t('agent.tree.newAgent') }}
          </el-dropdown-item>
          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newFolder">
            <el-icon><FolderAdd /></el-icon>{{ $t('agent.tree.newFolder') }}
          </el-dropdown-item>
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'">
              <el-icon><EditPen /></el-icon>{{ $t('agent.tree.rename') }}
            </el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item">
              <el-icon><Delete /></el-icon>{{ $t('agent.tree.delete') }}
            </el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      @confirm="onDialogConfirm"
    />
  </el-aside>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Plus, User, Folder, FolderAdd, EditPen, Delete } from '@element-plus/icons-vue';
import { useAgentStore } from '@/stores/agentStore';
import { buildChatTree } from '@/utils/treeHelper';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';
import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog from '@/components/common/EntityFormDialog.vue';
import type { Agent, AgentCreate, AgentUpdate, BaseTreeItem } from '@/api/types';

const { t } = useI18n();
const agentStore = useAgentStore();
const { agentList, currentAgentId, isAgentListLoading, loadingFolders, loadedFolderIds } = storeToRefs(agentStore);

const treeData = computed(() => buildChatTree(agentList.value, loadedFolderIds.value) as unknown as BaseTreeItem[]);

const {
  treeRef, contextMenuRef, contextMenuItem, contextMenuPosition, dialogState, dialogProps,
  handleMove, handleNodeExpand, handleNodeContextMenu, openRootContextMenu, handleMenuCommand, onDialogConfirm
} = useTreeController<Agent, AgentCreate, AgentUpdate>({
  items: agentList,
  crudHandlers: {
    createItem: agentStore.createNewItem,
    updateItem: agentStore.updateAgentSettings,
    deleteItem: agentStore.deleteItem,
    moveItem: agentStore.moveAgentItem,
  },
  onExpand: async (parentId) => { await agentStore.fetchChildren(parentId); },
  getDialogProps: (payload: DialogPayload<Agent>) => {
    if (payload.type === 'rename') return { title: t('agent.tree.rename'), initialName: payload.targetItem?.name || '' };
    if (payload.type === 'newAgent') return { title: t('agent.tree.newAgent'), initialName: t('agent.tree.newAgent') };
    if (payload.type === 'newFolder') return { title: t('agent.tree.newFolder'), initialName: t('agent.tree.newFolder') };
    return { title: '', initialName: '' };
  },
  handleDialogConfirm: async (payload: DialogPayload<Agent>, formPayload: DialogConfirmPayload) => {
    if (payload.type === 'rename' && payload.targetItem) {
      await agentStore.updateAgentSettings(payload.targetItem.id, { name: formPayload.name });
      return null;
    }
    const isFolder = payload.type === 'newFolder';
    const newItem = await agentStore.createNewItem({
      name: formPayload.name,
      itemType: isFolder ? 'folder' : 'agent',
      parentId: payload.parentId || null,
      AgentType: isFolder ? undefined : 'ReActAgent'
    });
    if (newItem && !isFolder) agentStore.selectAgent(newItem.id);
    return newItem;
  }
});

const handleHeaderCommand = (command: string) => handleMenuCommand(command);

const handleNodeClick = (data: BaseTreeItem) => {
  if (data.itemType === 'agent') agentStore.selectAgent(data.id);
};

onMounted(() => {
  agentStore.initializeList();
});
</script>

<style scoped>
.agent-tree-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-right: 1px solid var(--el-border-color);
  background-color: var(--color-background-soft);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: default;
}
.panel-header h4 {
  margin: 0;
  font-size: 16px;
}
.delete-item { color: var(--el-color-danger); }

.tree-agent-avatar {
  margin-right: 6px;
  background-color: transparent;
}
</style>
