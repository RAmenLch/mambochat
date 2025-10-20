<template>
  <div class="chat-list-container">
    <div class="chat-list-header" @contextmenu.prevent="openContextMenu($event, null)">
      <h4>会话列表</h4>
    </div>

    <el-scrollbar
      class="chat-list-scrollbar"
      @contextmenu.prevent="openContextMenu($event, null)"
    >
      <div v-if="isChatListLoading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      <el-tree
        v-else-if="treeData.length > 0"
        ref="treeRef"
        :data="treeData"
        node-key="id"
        :current-node-key="currentChatId || undefined"
        highlight-current
        :expand-on-click-node="false"
        draggable
        :allow-drop="allowDrop"
        :indent="8"
        @node-click="handleNodeClick"
        @node-drop="handleNodeDrop"
        @node-contextmenu="openContextMenu"
        @node-expand="handleNodeExpand"
        @node-collapse="handleNodeCollapse"
        class="chat-tree"
        :props="{ label: 'name', children: 'children' }"
      >
        <template #default="{ node, data }">
          <span class="custom-tree-node">
            <el-icon class="node-icon">
              <Folder v-if="data.itemType === 'folder'" />
              <ChatDotRound v-else />
            </el-icon>
            <el-tooltip
              :content="node.label"
              placement="top"
              :show-after="500"
              effect="dark"
              :disabled="!node.label || node.label.length < 15"
            >
              <span class="node-label">{{ node.label }}</span>
            </el-tooltip>
          </span>
        </template>
      </el-tree>
      <el-empty v-else description="右键新建会话" />
    </el-scrollbar>

    <el-divider />

    <div class="footer">
      <el-button :icon="Setting" circle @click="goToSettings" />
    </div>

    <el-dropdown
      ref="contextMenuRef"
      trigger="contextmenu"
      @command="handleCommand"
      popper-class="no-animation-popper"
    >
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <template v-if="contextMenuItem?.itemType === 'folder'">
            <el-dropdown-item command="newChatInFolder"><el-icon><Plus /></el-icon>新建会话</el-dropdown-item>
            <el-dropdown-item command="newFolderInFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
          </template>

          <template v-if="!contextMenuItem">
            <el-dropdown-item command="newRootChat"><el-icon><Plus /></el-icon>新建会话</el-dropdown-item>
            <el-dropdown-item command="newRootFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
          </template>

          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'"><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item v-if="contextMenuItem.itemType === 'chat'" command="duplicate"><el-icon><CopyDocument /></el-icon>复制会话</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <ItemNameDialog
      v-model:visible="itemNameDialog.visible"
      :title="itemNameDialog.title"
      :initial-name="itemNameDialog.initialName"
      @confirm="handleConfirmItemName"
    />

    <NewChatDialog
      v-model:visible="newChatDialogVisible"
      :grouped-models="groupedModelsForDialog"
      :default-model-id="globalSettings.default_model_id"
      @confirm="handleCreateChat"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, nextTick, watch } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTree } from 'element-plus';
import type { NodeDropType } from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import type { Chat, ChatReorderItem } from '@/api/types';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument } from '@element-plus/icons-vue';

import { buildChatTree } from '@/utils/treeHelper';
import { useContextMenu } from '@/composables/useContextMenu';
import ItemNameDialog from './dialogs/ItemNameDialog.vue';
import NewChatDialog from './dialogs/NewChatDialog.vue';

// -- Stores & Router --
const chatStore = useChatStore();
const providerStore = useProviderStore();
const router = useRouter();
const { chatList, currentChatId, isChatListLoading } = storeToRefs(chatStore);
const { providers, globalSettings } = storeToRefs(providerStore);
const treeRef = ref<InstanceType<typeof ElTree>>();
const contextMenuRef = ref();

// -- State & Composables --
const currentParentId = ref<string | null>(null); // For creating new items
const { contextMenuItem, contextMenuPosition, handleContextMenu } = useContextMenu<Chat>();

const itemNameDialog = reactive({
  visible: false,
  title: '',
  initialName: '',
  isRenaming: false,
});
const newChatDialogVisible = ref(false);

// -- Data Transformation --
const treeData = computed(() => buildChatTree(chatList.value));
const groupedModelsForDialog = computed(() => providers.value.map(p => ({
  id: p.id,
  label: p.name,
  options: p.models.map(m => ({ id: m.id, name: m.name })),
})));

// -- Folder Expansion State Management --
const FOLDER_STATE_KEY = 'mambo_folder_expanded_state';
const expandedState = ref<Record<string, boolean>>({});

const loadExpandedState = () => {
  const savedState = localStorage.getItem(FOLDER_STATE_KEY);
  if (savedState) {
    try {
      expandedState.value = JSON.parse(savedState);
    } catch (e) {
      console.error('Failed to parse folder state', e);
      localStorage.removeItem(FOLDER_STATE_KEY);
    }
  }
};

const saveExpandedState = () => {
  localStorage.setItem(FOLDER_STATE_KEY, JSON.stringify(expandedState.value));
};

const handleNodeExpand = (data: Chat) => {
  if (data.itemType === 'folder') {
    expandedState.value[data.id] = true;
    saveExpandedState();
  }
};
const handleNodeCollapse = (data: Chat) => {
  if (data.itemType === 'folder') {
    delete expandedState.value[data.id];
    saveExpandedState();
  }
};

watch(chatList, (newList) => {
  const folderIds = new Set(newList.filter(item => item.itemType === 'folder').map(item => item.id));
  const hasChanged = Object.keys(expandedState.value).some(id => !folderIds.has(id));
  if (hasChanged) {
    expandedState.value = Object.fromEntries(Object.entries(expandedState.value).filter(([key]) => folderIds.has(key)));
    saveExpandedState();
  }
}, { deep: true });

watch(treeData, (newTreeData) => {
  if (newTreeData.length > 0 && treeRef.value) {
    nextTick(() => {
      Object.keys(expandedState.value).forEach(key => treeRef.value!.getNode(key)?.expand());
    });
  }
}, { flush: 'post' });


// -- Lifecycle --
onMounted(async () => {
  loadExpandedState();
  await providerStore.fetchProviders();
  await chatStore.fetchChatList();

  const lastOpenedChat = chatList.value
    .filter(c => c.itemType === 'chat' && c.lastOpenedAt)
    .sort((a, b) => new Date(b.lastOpenedAt!).getTime() - new Date(a.lastOpenedAt!).getTime())[0];

  if (lastOpenedChat) {
    await handleSelectChat(lastOpenedChat.id);
  }
});

// -- Tree Operations --
const handleNodeClick = (data: Chat) => {
  if (data.itemType === 'chat') {
    handleSelectChat(data.id);
  }
};

const handleSelectChat = async (chatId: string) => {
  await chatStore.selectChat(chatId);
  if (chatStore.currentChat) {
    router.push(`/chat/${chatId}`);
  }
};

const scrollToChat = async (chatId: string) => {
  await handleSelectChat(chatId);
  await nextTick();
  const node = treeRef.value?.$el.querySelector('.is-current');
  node?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

const allowDrop = (draggingNode: Node, dropNode: Node, type: NodeDropType) => {
  return !((dropNode.data as Chat).itemType === 'chat' && type === 'inner');
};

const handleNodeDrop = async (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
  let parentId: string | null = null;
  let siblings: Node[] = [];

  if (dropType === 'inner') {
    parentId = (dropNode.data as Chat).id;
    siblings = dropNode.childNodes || [];
  } else {
    parentId = (dropNode.data as Chat).parentId;
    siblings = dropNode.parent?.childNodes || treeRef.value?.root.childNodes || [];
  }

  const updates: ChatReorderItem[] = siblings.map((node, index) => ({
    id: (node.data as Chat).id,
    parentId,
    sortOrder: index,
  }));

  if (updates.length > 0) {
    await chatStore.reorderChatItems(updates);
  }
};

// -- Context Menu & Dialogs --
const openContextMenu = (event: MouseEvent, data: Chat | null) => {
  handleContextMenu(event, data, contextMenuRef);
};

const handleCommand = (command: string) => {
  const item = contextMenuItem.value;
  switch (command) {
    case 'rename': if (item) openRenameDialog(item); break;
    case 'delete': if (item) handleDelete(item); break;
    case 'duplicate': if (item) handleDuplicateChat(item); break;
    case 'newChatInFolder': openNewChatDialog(item?.id ?? null); break;
    case 'newFolderInFolder': openNewFolderDialog(item?.id ?? null); break;
    case 'newRootChat': openNewChatDialog(null); break;
    case 'newRootFolder': openNewFolderDialog(null); break;
  }
};

const openRenameDialog = (item: Chat) => {
  itemNameDialog.title = '重命名';
  itemNameDialog.initialName = item.name;
  itemNameDialog.isRenaming = true;
  itemNameDialog.visible = true;
};

const openNewFolderDialog = (parentId: string | null) => {
  currentParentId.value = parentId;
  itemNameDialog.title = '新建文件夹';
  itemNameDialog.initialName = '新的文件夹';
  itemNameDialog.isRenaming = false;
  itemNameDialog.visible = true;
};

const openNewChatDialog = (parentId: string | null) => {
  currentParentId.value = parentId;
  newChatDialogVisible.value = true;
};

const handleConfirmItemName = async (name: string) => {
  if (itemNameDialog.isRenaming && contextMenuItem.value) {
    await chatStore.updateChatSettings(contextMenuItem.value.id, { name });
  } else {
    const parentId = currentParentId.value;
    const sortOrder = chatList.value.filter(item => item.parentId === parentId).length;

    await chatStore.createNewItem({
      name,
      itemType: 'folder',
      parentId,
      sortOrder,
    });

    if (parentId) {
      treeRef.value?.getNode(parentId)?.expand();
      handleNodeExpand({ id: parentId } as Chat);
    }
  }
};

const handleCreateChat = async (formData: { name: string; modelId: string }) => {
  const parentId = currentParentId.value;
  const sortOrder = chatList.value.filter(item => item.parentId === parentId).length;

  const newChat = await chatStore.createNewItem({
    ...formData,
    aiModelId: formData.modelId,
    itemType: 'chat',
    parentId,
    sortOrder,
  });

  if (newChat) {
    ElMessage.success('创建成功');
    if (parentId) {
      treeRef.value?.getNode(parentId)?.expand();
      handleNodeExpand({ id: parentId } as Chat);
    }
    await scrollToChat(newChat.id);
  } else {
    ElMessage.error('创建失败');
  }
};

const handleDelete = async (item: Chat) => {
  try {
    await ElMessageBox.confirm(`确定要删除 "${item.name}" 吗？此操作不可恢复。`, '警告', {
      confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning'
    });
    await chatStore.deleteItem(item.id);
    ElMessage.success('删除成功');
  } catch { /* User canceled */ }
};

const handleDuplicateChat = async (item: Chat) => {
  if (item.itemType !== 'chat') return;
  const newChat = await chatStore.duplicateChat(item.id);
  if (newChat) {
    ElMessage.success('复制成功');
    await scrollToChat(newChat.id);
  } else {
    ElMessage.error('复制失败');
  }
};

// -- Navigation --
const goToSettings = () => router.push('/settings');
</script>


<style>
.chat-tree { background-color: transparent; }
.chat-tree .el-tree-node__content { height: 40px; border-radius: 6px; margin: 0 4px 4px 4px; }
.chat-tree .el-tree-node.is-current > .el-tree-node__content { background-color: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-7); }
.chat-tree .el-tree-node__content:hover { background-color: var(--color-background-mute); }
.no-animation-popper { transition: none !important; animation: none !important; }
</style>
<style scoped>
.chat-list-container { height: 100%; display: flex; flex-direction: column; box-sizing: border-box; }
.chat-list-header { flex-shrink: 0; padding: 16px 16px 8px 16px; cursor: default; }
.chat-list-header h4 { margin: 0; font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.el-divider { margin: 0; flex-shrink: 0; }
.chat-list-scrollbar { flex-grow: 1; padding: 0 12px; }
.loading-container { padding: 0 10px; }
.custom-tree-node { flex: 1; display: flex; align-items: center; justify-content: space-between; font-size: 14px; padding-right: 8px; overflow: hidden; width: 100%; height: 100%; }
.node-icon { margin-right: 8px; font-size: 16px; }
.node-label { flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; margin-right: 8px; }
.delete-item { color: var(--el-color-danger); }
.footer { flex-shrink: 0; display: flex; justify-content: flex-end; align-items: center; padding: 8px 12px; }
</style>
