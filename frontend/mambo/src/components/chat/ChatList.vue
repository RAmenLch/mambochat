<!-- frontend/mambo/src/components/chat/ChatList.vue -->
<template>
  <div class="chat-list-container">
    <ExplorerTree
      ref="treeRef"
      :data="treeData"
      :current-id="currentChatId"
      :is-loading="isChatListLoading"
      folder-item-type="folder"
      persistence-key="mambo_chat_folder_expanded_state"
      class="chat-tree"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
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
      @command="handleMenuCommand"
      popper-class="no-animation-popper"
    >
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <!-- Search option for root, folder, and chat -->
          <el-dropdown-item command="search"><el-icon><Search /></el-icon>搜索</el-dropdown-item>

          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newChat" :divided="true">
            <el-icon><Plus /></el-icon>新建会话
          </el-dropdown-item>
          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newFolder">
            <el-icon><FolderAdd /></el-icon>新建文件夹
          </el-dropdown-item>

          <!-- Common actions for any item -->
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
      @confirm="onDialogConfirm"
    />

    <SearchDialog
      v-model:visible="searchDialogVisible"
      :root-id="searchRootId"
      :root-name="searchRootName"
      :root-path="searchRootPath"
      @select-result="handleSearchResultSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument, Search } from '@element-plus/icons-vue';

import type { Chat, ChatCreate, ChatUpdate, BaseTreeItem } from '@/api/types';
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';

import { buildChatTree } from '@/utils/treeHelper';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';

import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog, { type SelectConfigOption } from '@/components/common/EntityFormDialog.vue';
import SearchDialog from '@/components/chat/dialogs/SearchDialog.vue';

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

// -- Data Transformation --
const treeData = computed(() => buildChatTree(chatList.value) as unknown as BaseTreeItem[]);

const modelOptions = computed((): SelectConfigOption[] => {
  return providers.value.map(p => ({
    label: p.name,
    options: p.models.map(m => ({
      label: m.name,
      value: m.id
    }))
  }));
});

// -- Tree Controller Logic --
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
  handleMenuCommand: originalHandleMenuCommand,
  onDialogConfirm,
} = useTreeController<Chat, ChatCreate, ChatUpdate>({
  items: chatList,
  crudHandlers: {
    // 更新：将 store actions 映射到 useTreeController 的新接口
    createItem: chatListStore.createNewItem,
    updateItem: chatListStore.updateChatSettings,
    deleteItem: chatListStore.deleteItem,
    reorderItems: chatListStore.reorderChatItems,
    duplicateItem: chatListStore.duplicateChat,
  },
  getDialogProps: (payload: DialogPayload<Chat>) => {
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
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Chat>,
    formPayload: DialogConfirmPayload
  ): Promise<Chat | null> => {
    if (dialogPayload.type === 'rename' && dialogPayload.targetItem) {
      // 注意：此处调用的 store action 名称未变，因为在 store 中做了别名处理
      await chatListStore.updateChatSettings(dialogPayload.targetItem.id, { name: formPayload.name });
      return null;
    }

    const sortOrder = calculateSortOrder(dialogPayload.parentId);
    let newItem: Chat | null = null;

    if (dialogPayload.type === 'newChat') {
      newItem = await chatListStore.createNewItem({
        name: formPayload.name,
        aiModelId: formPayload.selectValue,
        itemType: 'chat',
        parentId: dialogPayload.parentId || null,
        sortOrder,
      });
      if (newItem) {
        await handleSelectChat(newItem.id);
      }
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await chatListStore.createNewItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId || null,
        sortOrder,
      });
    }
    return newItem;
  },
});

// -- Helper Functions --
const calculateSortOrder = (parentId?: string | null): number => {
  return chatList.value.filter(item => item.parentId === (parentId || null)).length;
};

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

// -- Component-Specific Actions --
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

const goToSettings = () => router.push('/settings');

// -- Search Dialog --
const searchDialogVisible = ref(false);
const searchRootId = ref<string | null>(null);
const searchRootName = ref<string | null>(null);
const searchRootPath = ref<string | null>(null);

// Helper function to get the full path of a chat/folder
function getItemPath(itemId: string): string {
  const path: string[] = [];
  let currentId: string | null = itemId;

  while (currentId) {
    const item = chatList.value.find(c => c.id === currentId);
    if (!item) break;

    path.unshift(item.name);
    currentId = item.parentId;
  }

  return path.join(' / ');
}

// Wrapper function to handle search command
async function handleMenuCommand(command: string) {
  if (command === 'search') {
    const selectedItem = contextMenuItem.value;

    if (selectedItem) {
      // Set search root info
      searchRootId.value = selectedItem.id;
      searchRootName.value = selectedItem.name;

      // Calculate full path (excluding the current item)
      const fullPath = getItemPath(selectedItem.id);
      const pathParts = fullPath.split(' / ');
      const pathWithoutCurrent = pathParts.slice(0, -1).join(' / ');
      searchRootPath.value = pathWithoutCurrent || null;
    } else {
      // Global search
      searchRootId.value = null;
      searchRootName.value = null;
      searchRootPath.value = null;
    }

    searchDialogVisible.value = true;
    return;
  }

  // Delegate other commands to original handler
  await originalHandleMenuCommand(command);
}

async function handleSearchResultSelect(data: { chatId: string; subMessageId: string | null }) {
  // [修复] 1. 先设置目标ID，确保 ChatWindow 在监听到会话切换并加载完成时，能第一时间读到这个值
  if (data.subMessageId) {
    chatSessionStore.setSearchTarget(data.subMessageId);
  }

  // [修复] 2. 再切换会话
  await handleSelectChat(data.chatId);

  // 注意：原先在这里设置 setSearchTarget 会因为 await 的存在导致设置得太晚
}
</script>

<style scoped>
.chat-list-container { height: 100%; display: flex; flex-direction: column; box-sizing: border-box; }
.chat-tree { flex-grow: 1; min-height: 0; }
.chat-list-header { cursor: default; }
.chat-list-header h4 { margin: 0; font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.el-divider { margin: 0; flex-shrink: 0; }
.delete-item { color: var(--el-color-danger); }
.footer { flex-shrink: 0; display: flex; justify-content: flex-end; align-items: center; padding: 8px 12px; }
</style>
<style>
/* This style remains global as it targets a popper rendered outside the component scope */
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
