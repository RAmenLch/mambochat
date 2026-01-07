<!-- frontend/mambo/src/components/chat/ChatList.vue -->
<template>
  <div class="chat-list-container">
    <ExplorerTree
      ref="treeRef"
      :data="treeData"
      :current-id="currentChatId"
      :is-loading="isChatListLoading"
      :loading-folder-ids="loadingFolders"
      folder-item-type="folder"
      persistence-key="mambo_chat_folder_expanded_state"
      class="chat-tree"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
      @move="handleMove"
      @node-expand="handleNodeExpand"
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
          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newChat">
            <el-icon><Plus /></el-icon>新建会话
          </el-dropdown-item>
          <el-dropdown-item v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'" command="newFolder">
            <el-icon><FolderAdd /></el-icon>新建文件夹
          </el-dropdown-item>

          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'"><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item v-if="contextMenuItem.itemType === 'chat'" command="duplicate"><el-icon><CopyDocument /></el-icon>复制会话</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>

          <el-dropdown-item command="search" :divided="true"><el-icon><Search /></el-icon>搜索</el-dropdown-item>
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
import { onMounted, computed, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter, useRoute } from 'vue-router';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument, Search } from '@element-plus/icons-vue';

import type { Chat, ChatCreate, ChatUpdate, BaseTreeItem } from '@/api/types';
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore, LAST_ACTIVE_CHAT_KEY } from '@/stores/chatSessionStore';
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
const route = useRoute();

const { chatList, isChatListLoading, loadingFolders, loadedFolderIds } = storeToRefs(chatListStore);
const { currentChatId } = storeToRefs(chatSessionStore);
const { providers } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);

// -- Data Transformation --
const treeData = computed(() => buildChatTree(chatList.value, loadedFolderIds.value) as unknown as BaseTreeItem[]);

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
  handleMove,
  handleNodeExpand,
  handleNodeContextMenu,
  openRootContextMenu,
  handleMenuCommand: originalHandleMenuCommand,
  onDialogConfirm,
} = useTreeController<Chat, ChatCreate, ChatUpdate>({
  items: chatList,
  crudHandlers: {
    createItem: chatListStore.createNewItem,
    updateItem: chatListStore.updateChatSettings,
    deleteItem: chatListStore.deleteItem,
    moveItem: chatListStore.moveChatItem,
    duplicateItem: chatListStore.duplicateChat,
  },
  onExpand: chatListStore.fetchChatChildren,
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
      await chatListStore.updateChatSettings(dialogPayload.targetItem.id, { name: formPayload.name });
      return null;
    }

    const sortOrder = 0;
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

// -- Lifecycle --
onMounted(async () => {
  await providerStore.fetchProviders();
  await chatListStore.initializeList();

  // 确保路由参数已就绪
  await router.isReady();

  let targetChatId = route.params.id as string;

  // 1. 如果路由参数为空，尝试从 URL 路径解析（解决刷新时 params 延迟问题）
  if (!targetChatId) {
    const match = window.location.pathname.match(/\/chat\/([a-zA-Z0-9-]+)/);
    if (match && match[1]) {
      targetChatId = match[1];
    }
  }

  // 2. 如果 URL 中确实没有 ID，尝试从 LocalStorage 恢复上下文
  if (!targetChatId) {
    const lastActiveId = localStorage.getItem(LAST_ACTIVE_CHAT_KEY);
    if (lastActiveId) {
      targetChatId = lastActiveId;
    }
  }

  // 3. 执行加载与选中逻辑
  if (targetChatId) {
    // 确保目标节点及其父级路径已加载（懒加载支持）
    await chatListStore.resolvePath(targetChatId);
    await handleSelectChat(targetChatId);
    await treeRef.value?.scrollToKey(targetChatId);
  } else {
    // 4. 兜底逻辑：加载 Root 层最近打开的会话
    const lastOpenedChat = chatList.value
      .filter(c => c.itemType === 'chat' && c.lastOpenedAt)
      .sort((a, b) => new Date(b.lastOpenedAt!).getTime() - new Date(a.lastOpenedAt!).getTime())[0];

    if (lastOpenedChat) {
      await handleSelectChat(lastOpenedChat.id);
    }
  }
});

// 监听路由变化，处理应用内导航
watch(
  () => route.params.id,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      if (currentChatId.value !== newId) {
        // 确保树中存在该节点
        const exists = chatList.value.some(c => c.id === newId);
        if (!exists) {
          await chatListStore.resolvePath(newId);
        }
        await handleSelectChat(newId);
        await treeRef.value?.scrollToKey(newId);
      }
    }
  }
);

// -- Component-Specific Actions --
const handleNodeClick = (data: BaseTreeItem) => {
  if (data.itemType === 'chat') {
    handleSelectChat(data.id);
  }
};

const handleSelectChat = async (chatId: string) => {
  await chatSessionStore.selectChat(chatId);
  if (chatSessionStore.currentChat) {
    if (route.params.id !== chatId) {
      router.push(`/chat/${chatId}`);
    }
  }
};

const goToSettings = () => router.push('/settings');

// -- Search Dialog --
const searchDialogVisible = ref(false);
const searchRootId = ref<string | null>(null);
const searchRootName = ref<string | null>(null);
const searchRootPath = ref<string | null>(null);

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

async function handleMenuCommand(command: string) {
  if (command === 'search') {
    const selectedItem = contextMenuItem.value;

    if (selectedItem) {
      searchRootId.value = selectedItem.id;
      searchRootName.value = selectedItem.name;

      const fullPath = getItemPath(selectedItem.id);
      const pathParts = fullPath.split(' / ');
      const pathWithoutCurrent = pathParts.slice(0, -1).join(' / ');
      searchRootPath.value = pathWithoutCurrent || null;
    } else {
      searchRootId.value = null;
      searchRootName.value = null;
      searchRootPath.value = null;
    }

    searchDialogVisible.value = true;
    return;
  }

  await originalHandleMenuCommand(command);
}

async function handleSearchResultSelect(data: { chatId: string; subMessageId: string | null }) {
  if (data.subMessageId) {
    chatSessionStore.setSearchTarget(data.subMessageId);
  }

  await chatListStore.resolvePath(data.chatId);
  await handleSelectChat(data.chatId);
  await treeRef.value?.scrollToKey(data.chatId);
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
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
