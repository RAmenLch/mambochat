<template>
  <div class="chat-list-container">
    <ExplorerTree
      ref="treeRef"
      :data="treeData"
      :current-id="currentChatId"
      :is-loading="isChatListLoading"
      folder-item-type="folder"
      persistence-key="mambo_chat_folder_expanded_state"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openContextMenu($event, null)"
      @reorder="handleReorder"
    >
      <template #header>
        <div class="chat-list-header">
          <h4>会话列表</h4>
        </div>
      </template>

      <template #item-icon="{ data }">
        <el-icon>
          <Folder v-if="data.itemType === 'folder'" />
          <ChatDotRound v-else />
        </el-icon>
      </template>
    </ExplorerTree>

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

    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      :select-config="dialogProps.selectConfig"
      @confirm="handleDialogConfirm"
    />
  </div>
</template>

<script setup lang="ts">
// ... (Script 部分保持不变)
import { ref, onMounted, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import type Node from 'element-plus/es/components/tree/src/model/node';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument } from '@element-plus/icons-vue';

import type { Chat, ChatReorderItem, BaseTreeItem, TreeReorderEvent } from '@/api/types';
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';

import { buildChatTree } from '@/utils/treeHelper';
import { useContextMenu } from '@/composables/useContextMenu';
import { useDialogState } from '@/composables/useDialogState';

import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog, {type SelectConfigOption} from '@/components/common/EntityFormDialog.vue';

// --- Types ---
type DialogType = 'rename' | 'newChat' | 'newFolder';
interface DialogPayload {
  type: DialogType;
  parentId?: string | null;
  targetItem?: Chat;
}

// -- Store Instances & State --
const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const router = useRouter();

const { chatList, isChatListLoading } = storeToRefs(chatListStore);
const { currentChatId } = storeToRefs(chatSessionStore);
const { providers } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);

// -- Local Component State --
const treeRef = ref<InstanceType<typeof ExplorerTree>>();
const contextMenuRef = ref();
const { contextMenuItem, contextMenuPosition, handleContextMenu } = useContextMenu<Chat>();
const dialogState = useDialogState<DialogPayload>();

// -- Data Transformation --
const treeData = computed(() => buildChatTree(chatList.value) as unknown as BaseTreeItem[]);

const modelOptions = computed((): SelectConfigOption[] => {
  return providers.value.map(p => ({
    label: p.name, // 分组标题 (如 OpenAI)
    options: p.models.map(m => ({
      label: m.name, // 选项标题 (如 gpt-4o)
      value: m.id    // 选项值
    }))
  }));
});

const dialogProps = computed(() => {
  const payload = dialogState.payload.value;
  if (!payload) return { title: '', initialName: '' };

  switch (payload.type) {
    case 'rename':
      return {
        title: '重命名',
        initialName: payload.targetItem?.name || '',
      };
    case 'newChat':
      return {
        title: '新建会话',
        initialName: '新的会话',
        selectConfig: {
          label: '模型',
          options: modelOptions.value,
          initialValue: globalSettings.value.default_model_id || undefined,
        },
      };
    case 'newFolder':
      return {
        title: '新建文件夹',
        initialName: '新的文件夹',
      };
    default:
      return { title: '', initialName: '' };
  }
});

// -- Lifecycle --
onMounted(async () => {
  await providerStore.fetchProviders();
  await chatListStore.fetchChatList();

  const lastOpenedChat = chatList.value
    .filter(c => c.itemType === 'chat' && c.lastOpenedAt)
    .sort((a, b) => new Date(b.lastOpenedAt!).getTime() - new Date(a.lastOpenedAt!).getTime())[0];

  if (lastOpenedChat) {
    await handleSelectChat(lastOpenedChat.id);
  }
});

// -- Tree Operations --
const handleNodeClick = (data: BaseTreeItem) => {
  if (data.itemType === 'chat') {
    handleSelectChat(data.id);
  }
};

const handleSelectChat = async (chatId: string) => {
  await chatSessionStore.selectChat(chatId);
  if (chatSessionStore.currentChat) {
    router.push(`/chat/${chatId}`);
  }
};

const handleReorder = async (updates: TreeReorderEvent[]) => {
  await chatListStore.reorderChatItems(updates as ChatReorderItem[]);
};

// -- Context Menu --
const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem, node: Node) => {
  openContextMenu(event, data as unknown as Chat);
};

const openContextMenu = (event: MouseEvent, data: Chat | null) => {
  handleContextMenu(event, data, contextMenuRef);
};

const handleCommand = (command: string) => {
  const item = contextMenuItem.value;
  switch (command) {
    case 'rename':
      if (item) dialogState.open({ type: 'rename', targetItem: item });
      break;
    case 'delete':
      if (item) handleDelete(item);
      break;
    case 'duplicate':
      if (item) handleDuplicateChat(item);
      break;
    case 'newChatInFolder':
      dialogState.open({ type: 'newChat', parentId: item?.id });
      break;
    case 'newFolderInFolder':
      dialogState.open({ type: 'newFolder', parentId: item?.id });
      break;
    case 'newRootChat':
      dialogState.open({ type: 'newChat', parentId: null });
      break;
    case 'newRootFolder':
      dialogState.open({ type: 'newFolder', parentId: null });
      break;
  }
};

// -- Dialog Handling --
const handleDialogConfirm = async (payload: { name: string; selectValue?: string }) => {
  const state = dialogState.payload.value;
  if (!state) return;

  if (state.type === 'rename' && state.targetItem) {
    await chatListStore.updateChatSettings(state.targetItem.id, { name: payload.name });
  } else if (state.type === 'newChat') {
    const sortOrder = calculateSortOrder(state.parentId);
    const newChat = await chatListStore.createNewItem({
      name: payload.name,
      aiModelId: payload.selectValue,
      itemType: 'chat',
      parentId: state.parentId || null,
      sortOrder,
    });
    if (newChat) {
      ElMessage.success('创建成功');
      await handleSelectChat(newChat.id);
      await treeRef.value?.scrollToKey(newChat.id);
    }
  } else if (state.type === 'newFolder') {
    const sortOrder = calculateSortOrder(state.parentId);
    await chatListStore.createNewItem({
      name: payload.name,
      itemType: 'folder',
      parentId: state.parentId || null,
      sortOrder,
    });
  }
};

const calculateSortOrder = (parentId?: string | null): number => {
  return chatList.value.filter(item => item.parentId === (parentId || null)).length;
};

// -- Other Actions --
const handleDelete = async (item: Chat) => {
  try {
    await ElMessageBox.confirm(`确定要删除 "${item.name}" 吗？此操作不可恢复。`, '警告', {
      confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning'
    });
    await chatListStore.deleteItem(item.id);
    ElMessage.success('删除成功');
  } catch { /* User canceled */ }
};

const handleDuplicateChat = async (item: Chat) => {
  if (item.itemType !== 'chat') return;
  const newChat = await chatListStore.duplicateChat(item.id);
  if (newChat) {
    ElMessage.success('复制成功');
    await treeRef.value?.scrollToKey(newChat.id);
  }
};

const goToSettings = () => router.push('/settings');
</script>

<style scoped>
.chat-list-container { height: 100%; display: flex; flex-direction: column; box-sizing: border-box; }
.chat-list-header { cursor: default; }
.chat-list-header h4 { margin: 0; font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.el-divider { margin: 0; flex-shrink: 0; }
.delete-item { color: var(--el-color-danger); }
.footer { flex-shrink: 0; display: flex; justify-content: flex-end; align-items: center; padding: 8px 12px; }
</style>
<style>
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
