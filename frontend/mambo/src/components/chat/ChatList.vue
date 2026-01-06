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

          <!-- Common actions for any item -->
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'"><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item v-if="contextMenuItem.itemType === 'chat'" command="duplicate"><el-icon><CopyDocument /></el-icon>复制会话</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>

          <!-- Search option at the bottom -->
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
import { onMounted, computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter, useRoute } from 'vue-router';
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
  // 绑定懒加载 Action
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

    // 在懒加载模式下，新创建的节点默认排在最后，具体顺序由后端决定
    // 前端不再负责计算 sortOrder，传递 0 或由后端处理默认值
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
  // 初始化加载根节点
  await chatListStore.initializeList();

  // 处理深层链接或默认选中
  const routeChatId = route.params.id as string;
  if (routeChatId) {
    // 如果 URL 中有 ID，先解析路径以确保树结构完整，再选中
    await chatListStore.resolvePath(routeChatId);
    await handleSelectChat(routeChatId);
    // 确保树节点展开并滚动到视图
    await treeRef.value?.scrollToKey(routeChatId);
  } else {
    // 否则尝试选中最近打开的（仅限当前已加载的列表）
    const lastOpenedChat = chatList.value
      .filter(c => c.itemType === 'chat' && c.lastOpenedAt)
      .sort((a, b) => new Date(b.lastOpenedAt!).getTime() - new Date(a.lastOpenedAt!).getTime())[0];

    if (lastOpenedChat) {
      await handleSelectChat(lastOpenedChat.id);
    }
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

  // 注意：在懒加载模式下，如果父节点未加载，此路径可能不完整
  // 但对于已加载的上下文菜单项，其祖先通常已存在于列表中
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
  // 1. 设置目标ID
  if (data.subMessageId) {
    chatSessionStore.setSearchTarget(data.subMessageId);
  }

  // 2. 确保目标节点在树中可见（加载路径）
  await chatListStore.resolvePath(data.chatId);

  // 3. 切换会话
  await handleSelectChat(data.chatId);

  // 4. 滚动定位树节点
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
/* This style remains global as it targets a popper rendered outside the component scope */
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
