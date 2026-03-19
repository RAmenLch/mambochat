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
      <!-- ... template 内部保持不变 ... -->
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
import { computed, onMounted, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router'; // 引入 useRouter
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Plus, User, Folder, FolderAdd, EditPen, Delete } from '@element-plus/icons-vue';
import { useAgentStore } from '@/stores/agentStore';
import { getAgent, getAgentChildren } from '@/api/agentService';
import { buildChatTree } from '@/utils/treeHelper';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';
import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog from '@/components/common/EntityFormDialog.vue';
import type { Agent, AgentCreate, AgentUpdate, BaseTreeItem } from '@/api/types';

const { t } = useI18n();
const route = useRoute();
const router = useRouter(); // 初始化 router
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

// [修改] 点击节点时，更新 URL
const handleNodeClick = (data: BaseTreeItem) => {
  if (data.itemType === 'agent') {
    // 如果点击的是当前已选中的，仅更新 URL（确保参数存在），不再重复触发 selectAgent 逻辑
    // 如果点击的是新的 Agent，更新 URL 会触发 watch -> checkAndLoadAgent -> selectAgent
    if (route.query.agentId !== data.id) {
      router.replace({
        query: {
          ...route.query,
          tab: 'agentManager',
          agentId: data.id
        }
      });
    } else {
      // 即使 ID 相同，也确保 Store 状态同步（例如首次加载）
       agentStore.selectAgent(data.id);
    }
  }
};

// ================= [修复] 深度链接跳转与树形展开逻辑 =================

// 强行展开底层 el-tree 的指定节点
const expandTreeFolder = (folderId: string) => {
  if (!treeRef.value) return;
  // 兼容不同层级的 ref 嵌套，找到真正的 el-tree 实例
  const treeInstance = (treeRef.value as any).treeRef || (treeRef.value as any).$refs?.treeRef || (treeRef.value as any).$refs?.tree || treeRef.value;
  if (treeInstance && treeInstance.store && treeInstance.store.nodesMap) {
    const node = treeInstance.store.nodesMap[folderId];
    if (node) {
      node.expanded = true;
    }
  }
};

// 提取已存在节点的父级并展开
const expandParents = (agentId: string) => {
  const agent = agentList.value.find(a => a.id === agentId);
  if (!agent) return;
  let parentId = agent.parentId;
  const foldersToExpand: string[] = [];
  while (parentId) {
    foldersToExpand.unshift(parentId);
    const parent = agentList.value.find(a => a.id === parentId);
    parentId = parent ? parent.parentId : null;
  }
  nextTick(() => {
    foldersToExpand.forEach(folderId => expandTreeFolder(folderId));
  });
};

const checkAndLoadAgent = async (agentId: string) => {
  if (!agentId) return;

  // 1. 等待根目录初始化完成
  if (isAgentListLoading.value) {
    const unwatch = watch(isAgentListLoading, (loading) => {
      if (!loading) {
        unwatch();
        checkAndLoadAgent(agentId);
      }
    });
    return;
  }

  // 2. 如果已经在列表中，直接选中并展开父级
  if (agentList.value.find(a => a.id === agentId)) {
    agentStore.selectAgent(agentId);
    expandParents(agentId);
    return;
  }

  try {
    const targetAgent = await getAgent(agentId);
    if (!targetAgent) return;

    const foldersToExpand: string[] = [];
    let currentParentId = targetAgent.parentId;

    // 3. 向上溯源，收集需要展开的父文件夹
    while (currentParentId) {
      foldersToExpand.unshift(currentParentId);
      const parentInList = agentList.value.find(a => a.id === currentParentId);
      if (parentInList) {
        currentParentId = parentInList.parentId;
      } else {
        const parentAgent = await getAgent(currentParentId);
        if (parentAgent) {
          currentParentId = parentAgent.parentId;
          // 必须将缺失的父节点推入列表，否则树组件会判定子节点为孤儿节点
          if (!agentList.value.find(a => a.id === parentAgent.id)) {
            agentList.value.push(parentAgent);
          }
        } else {
          break;
        }
      }
    }

    // 4. 依次加载父文件夹的子节点
    for (const folderId of foldersToExpand) {
      // [修复] loadedFolderIds 是 Set 类型，应使用 has 方法
      if (!loadedFolderIds.value.has(folderId)) {
        const children = await getAgentChildren([folderId]); // 明确传入数组
        const newChildren = children.filter(c => !agentList.value.find(a => a.id === c.id));
        agentList.value.push(...newChildren);
        // [修复] loadedFolderIds 是 Set 类型，应使用 add 方法
        loadedFolderIds.value.add(folderId);
      }
    }

    // 5. 确保目标 Agent 在列表中
    if (!agentList.value.find(a => a.id === targetAgent.id)) {
      agentList.value.push(targetAgent);
    }

    // 6. 选中
    agentStore.selectAgent(agentId);

    // 7. 等待 DOM 更新后，视觉上展开所有收集到的父文件夹
    nextTick(() => {
      foldersToExpand.forEach(folderId => {
        expandTreeFolder(folderId);
      });
    });

  } catch (e) {
    console.error('Failed to load agent lineage from url', e);
  }
};

onMounted(() => {
  agentStore.initializeList();
  // 检查 URL 参数
  if (route.query.agentId) {
    checkAndLoadAgent(route.query.agentId as string);
  }
});

// 监听同页面内的路由变化
watch(() => route.query.agentId, (newId) => {
  if (newId) {
    checkAndLoadAgent(newId as string);
  }
});
</script>

<style scoped>
/* ... 保持原有样式不变 ... */
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
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.delete-item { color: var(--el-color-danger); }

.tree-agent-avatar {
  margin-right: 6px;
  background-color: transparent;
}
</style>

