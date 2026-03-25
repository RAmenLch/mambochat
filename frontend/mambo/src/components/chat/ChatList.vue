<!-- frontend/mambo/src/components/chat/ChatList.vue -->
<template>
  <div class="chat-list-container">
    <template v-if="showTree">
      <ExplorerTree
        ref="treeRef"
        :data="treeData"
        :current-id="currentChatId"
        :is-loading="isChatListLoading"
        :loading-folder-ids="loadingFolders"
        folder-item-type="folder"
        persistence-key="mambo_chat_folder_expanded_state"
        :enable-multi-select="true"
        class="chat-tree"
        @node-click="handleNodeClick"
        @node-contextmenu="handleNodeContextMenu"
        @root-contextmenu="openRootContextMenu"
        @move="handleMove"
        @node-expand="handleNodeExpand"
      >
        <template #header>
          <div class="chat-list-header">
            <h4>{{ $t('chat.sidebar.title') }}</h4>
          </div>
        </template>

        <template #item-icon="{ data }">
          <el-icon>
            <Folder v-if="data.itemType === 'folder'" />
            <ChatDotRound v-else />
          </el-icon>
        </template>
      </ExplorerTree>

      <el-dropdown
        ref="contextMenuRef"
        trigger="contextmenu"
        @command="handleMenuCommand"
        popper-class="no-animation-popper"
      >
        <span :style="contextMenuPosition" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'"
              command="newChat"
            >
              <el-icon><Plus /></el-icon>{{ $t('chat.sidebar.newChat') }}
            </el-dropdown-item>
            <el-dropdown-item
              v-if="!contextMenuItem || contextMenuItem?.itemType === 'folder'"
              command="newFolder"
            >
              <el-icon><FolderAdd /></el-icon>{{ $t('chat.sidebar.newFolder') }}
            </el-dropdown-item>

            <template v-if="contextMenuItem">
              <el-dropdown-item command="archive" divided>
                <el-icon><FolderChecked /></el-icon>{{ $t('chat.sidebar.archive') }}
              </el-dropdown-item>

              <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'"
                ><el-icon><EditPen /></el-icon>{{ $t('chat.sidebar.rename') }}</el-dropdown-item
              >
              <el-dropdown-item v-if="contextMenuItem.itemType === 'chat'" command="duplicate"
                ><el-icon><CopyDocument /></el-icon
                >{{ $t('chat.sidebar.duplicate') }}</el-dropdown-item
              >
              <el-dropdown-item command="delete" class="delete-item"
                ><el-icon><Delete /></el-icon>{{ $t('chat.sidebar.delete') }}</el-dropdown-item
              >
            </template>

            <el-dropdown-item command="search" :divided="true"
              ><el-icon><Search /></el-icon>{{ $t('chat.sidebar.search') }}</el-dropdown-item
            >
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>

    <ChatHeader
      v-else
      mode="vertical"
      :current-chat="currentChat"
      :is-title-refreshing="isTitleRefreshing"
      @save-title="handleSaveTitle"
      @refresh-title="handleRefreshTitle"
      @expand="$emit('expand')"
      class="vertical-header"
    />

    <el-divider />

    <div class="footer" :class="{ collapsed: !showTree }">
      <el-tooltip v-if="!showTree" :content="$t('settings.tabs.globalSettings')" placement="right">
        <el-button :icon="Setting" circle @click="goToSettings" />
      </el-tooltip>
      <el-button v-else :icon="Setting" circle @click="goToSettings" />
    </div>

    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      :select-config="dialogProps.selectConfig"
      :show-chat-mode="dialogProps.showChatMode"
      :agent-select-config="dialogProps.agentSelectConfig"
      @confirm="onDialogConfirm"
    />

    <SearchDialog
      v-model:visible="searchDialogVisible"
      :root-id="searchRootId"
      :root-name="searchRootName"
      :root-path="searchRootPath"
      @select-result="handleSearchResultSelect"
    />

    <el-dialog
      v-model="archiveDialogVisible"
      :title="$t('chat.sidebar.archiveTitle')"
      width="400px"
    >
      <el-form @submit.prevent>
        <el-form-item :label="$t('chat.sidebar.folderName')">
          <el-input v-model="archiveFolderName" @keyup.enter="confirmArchive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="archiveDialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="confirmArchive" :loading="isArchiving">{{ $t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter, useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument, Search, FolderChecked } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import type { Chat, ChatCreate, ChatUpdate, BaseTreeItem } from '@/api/types';
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore, LAST_ACTIVE_CHAT_KEY } from '@/stores/chatSessionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useAgentStore } from '@/stores/agentStore';

import { buildChatTree } from '@/utils/treeHelper';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';

import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog, { type SelectConfigOption, type ConfirmPayload } from '@/components/common/EntityFormDialog.vue';
import SearchDialog from '@/components/chat/dialogs/SearchDialog.vue';
import ChatHeader from '@/components/chat/ChatHeader.vue';

const props = defineProps<{
  isCollapsed: boolean;
  width: number;
}>();

const emit = defineEmits<{
  (e: 'expand'): void;
}>();

const { t } = useI18n();

const VISUAL_COLLAPSE_THRESHOLD = 150;

const showTree = computed(() => {
  return !props.isCollapsed && props.width >= VISUAL_COLLAPSE_THRESHOLD;
});

const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const agentStore = useAgentStore();
const router = useRouter();
const route = useRoute();

const { chatList, isChatListLoading, loadingFolders, loadedFolderIds, refreshingTitleChatId } = storeToRefs(chatListStore);
const { currentChatId, currentChat } = storeToRefs(chatSessionStore);
const { providers } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);
const { agentList } = storeToRefs(agentStore);

const treeData = computed(() => buildChatTree(chatList.value, loadedFolderIds.value) as unknown as BaseTreeItem[]);

const modelOptions = computed((): SelectConfigOption[] => {
  return providers.value
    .map(p => ({
      label: p.name,
      options: p.models
        .filter(m => m.model_type === 'chat')
        .map(m => ({
          label: m.name,
          value: m.id
        }))
    }))
    .filter(p => p.options.length > 0);
});

const agentOptions = computed((): SelectConfigOption[] => {
  return agentStore.allAgents
    .filter(a => a.itemType === 'agent')
    .map(a => ({
      label: a.name,
      value: a.id
    }));
});

const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);

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
          title: t('chat.sidebar.rename'),
          initialName: payload.targetItem?.name || '',
        };
      case 'newChat':
        return {
          title: t('chat.sidebar.newChat'),
          initialName: t('chat.sidebar.initChatName'),
          showChatMode: true,
          selectConfig: {
            label: t('chat.settings.model'),
            options: modelOptions.value,
            initialValue: globalSettings.value.default_model_id || undefined,
          },
          agentSelectConfig: {
            label: t('chat.settings.agent'),
            options: agentOptions.value,
          }
        };
      case 'newFolder':
        return {
          title: t('chat.sidebar.newFolder'),
          initialName: t('chat.sidebar.initFolderName'),
        };
      default:
        return { title: '', initialName: '' };
    }
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Chat>,
    rawFormPayload: DialogConfirmPayload
  ): Promise<Chat | null> => {
    const formPayload = rawFormPayload as unknown as ConfirmPayload;

    if (dialogPayload.type === 'rename' && dialogPayload.targetItem) {
      await chatListStore.updateChatSettings(dialogPayload.targetItem.id, { name: formPayload.name });
      return null;
    }

    let newItem: Chat | null = null;

    if (dialogPayload.type === 'newChat') {
      newItem = await chatListStore.createNewItem({
        name: formPayload.name,
        aiModelId: formPayload.chatMode === 'normal' ? formPayload.selectValue : null,
        chatMode: formPayload.chatMode,
        agentId: formPayload.chatMode === 'agent' ? formPayload.agentId : null,
        itemType: 'chat',
        parentId: dialogPayload.parentId || null,
      });
      if (newItem) {
        await handleSelectChat(newItem.id);
      }
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await chatListStore.createNewItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId || null,
      });
    }
    return newItem;
  },
});

onMounted(async () => {
  await providerStore.fetchProviders();
  await agentStore.fetchAllAgents();
  await chatListStore.initializeList();
  await router.isReady();

  let targetChatId = route.params.id as string;

  if (!targetChatId) {
    const match = window.location.pathname.match(/\/chat\/([a-zA-Z0-9-]+)/);
    if (match && match[1]) {
      targetChatId = match[1];
    }
  }

  if (!targetChatId) {
    const lastActiveId = localStorage.getItem(LAST_ACTIVE_CHAT_KEY);
    if (lastActiveId) {
      targetChatId = lastActiveId;
    }
  }

  if (targetChatId) {
    await chatListStore.resolvePath(targetChatId);
    await handleSelectChat(targetChatId);
    await treeRef.value?.scrollToKey(targetChatId);
  } else {
    const lastOpenedChat = chatList.value
      .filter(c => c.itemType === 'chat' && c.lastOpenedAt)
      .sort((a, b) => new Date(b.lastOpenedAt!).getTime() - new Date(a.lastOpenedAt!).getTime())[0];

    if (lastOpenedChat) {
      await handleSelectChat(lastOpenedChat.id);
    }
  }
});

watch(
  () => route.params.id,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      if (currentChatId.value !== newId) {
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

function handleSaveTitle(newTitle: string) {
  if (currentChat.value) {
    chatListStore.updateChatSettings(currentChat.value.id, { name: newTitle });
  }
}

function handleRefreshTitle() {
  if (currentChat.value) {
    chatListStore.refreshChatTitle(currentChat.value.id);
  }
}

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

const archiveDialogVisible = ref(false);
const archiveFolderName = ref('');
const isArchiving = ref(false);

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

  if (command === 'archive') {
    archiveFolderName.value = t('chat.sidebar.newArchiveFolder');
    archiveDialogVisible.value = true;
    return;
  }

  const result = await originalHandleMenuCommand(command);

  if (result && result.itemType === 'chat') {
    await handleSelectChat(result.id);
  }
}

async function confirmArchive() {
  if (!archiveFolderName.value.trim()) {
    ElMessage.warning(t('common.rule.nameRequired'));
    return;
  }

  const selectedIds = treeRef.value?.selectedIds;
  if (!selectedIds || selectedIds.size === 0) return;

  const itemIds = Array.from(selectedIds);
  const parentId = chatList.value.find(c => c.id === itemIds[0])?.parentId || null;

  isArchiving.value = true;
  try {
    const newFolder = await chatListStore.archiveItems({
      item_ids: itemIds,
      new_folder_name: archiveFolderName.value.trim(),
      parent_id: parentId
    });
    ElMessage.success(t('common.msg.operationSuccess'));
    archiveDialogVisible.value = false;
    treeRef.value?.clearSelection();

    // [新增] 自动滚动并展开新文件夹，避免用户疑惑
    if (newFolder) {
      await treeRef.value?.scrollToKey(newFolder.id);
      await treeRef.value?.expandNode(newFolder.id);
    }
  } catch (error) {
    ElMessage.error(t('common.error.operationFailed'));
  } finally {
    isArchiving.value = false;
  }
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
.chat-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100%;
  overflow: hidden;
}

.chat-tree {
  flex-grow: 1;
  min-height: 0;
}

.vertical-header {
  flex-grow: 1;
  min-height: 0;
}

.chat-list-header {
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-list-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.el-divider {
  margin: 0;
  flex-shrink: 0;
}

.delete-item {
  color: var(--el-color-danger);
}

.footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 8px 12px;
}

.footer.collapsed {
  justify-content: center;
  padding: 12px 0;
}
</style>

<style>
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
