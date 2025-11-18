<!-- frontend/mambo/src/components/chat/ChatWindow.vue -->
<template>
  <div class="chat-window-container">
    <input type="file" ref="fileInputRef" @change="onFileSelected" multiple style="display: none;" />

    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <template v-else>
      <div class="chat-window-header">
        <div v-if="!isEditingTitle" class="title-display-area">
          <h3 class="chat-title">{{ currentChat.name }}</h3>
          <div class="title-actions">
            <el-tooltip content="编辑标题" placement="bottom" :show-after="500">
              <el-button :icon="Edit" circle text @click="startTitleEdit" />
            </el-tooltip>
            <el-tooltip content="刷新标题" placement="bottom" :show-after="500">
              <el-button
                :icon="Refresh"
                circle
                text
                @click="handleRefreshTitle"
                :loading="isTitleRefreshing"
              />
            </el-tooltip>
          </div>
        </div>
        <div v-else class="title-edit-area">
          <el-input
            ref="titleInputRef"
            v-model="titleInput"
            @blur="saveTitle"
            @keydown.enter.prevent="saveTitle"
            class="title-input"
          />
        </div>
      </div>

      <el-scrollbar ref="scrollbarRef" class="message-list-scrollbar" v-loading="isChatHistoryLoading" @scroll="handleScroll">
        <div class="message-list-wrapper">
          <MessageItem
            v-for="(message, index) in currentChatMessages"
            :key="message.id"
            :message="message"
            :is-last-message="index === currentChatMessages.length - 1"
          />
        </div>
      </el-scrollbar>

      <div class="input-container-wrapper" :style="{ height: `${inputAreaHeight}px` }">
        <div class="resize-handle" @mousedown.prevent="startResizeInputArea"></div>
        <ChatToolbar
          :current-chat="currentChat"
          :estimated-tokens="estimatedTokens"
          @open-settings="settingsDrawerVisible = true"
          @toggle-multi-part-mode="toggleMultiPartMode"
          @trigger-file-upload="handleTriggerFileUpload"
          @open-resource-selector="resourceSelectorVisible = true"
        />
        <!-- Uploaded Files Preview Area -->
        <div v-if="uploadedFiles.length > 0" class="uploaded-files-preview">
          <div v-for="file in uploadedFiles" :key="file.id" class="file-item">
            <el-image
              v-if="file.mime_type.startsWith('image/')"
              :src="file.url"
              fit="cover"
              class="file-thumbnail"
            >
              <template #error>
                <div class="image-slot-error">
                  <el-icon><Picture /></el-icon>
                </div>
              </template>
            </el-image>
            <div v-else class="file-icon">
              <el-icon><Document /></el-icon>
            </div>
            <span class="file-name" :title="file.filename">{{ file.filename }}</span>
            <el-button
              :icon="Close"
              circle
              text
              class="remove-file-btn"
              @click="removeUploadedFile(file.id)"
            />
          </div>
        </div>

        <div class="chat-input-area" @keydown="handleGlobalKeydown">
          <MultiPartInput
            v-if="isMultiPartMode"
            ref="multiPartInputRef"
            v-model="multiPartDraft"
            class="input-field"
            @send="handleSendMessage"
          />
          <el-input
            v-else
            ref="inputRef"
            v-model="singlePartDraft"
            type="textarea"
            :autosize="false"
            resize="none"
            placeholder="输入消息... (Shift + Enter 换行)"
            :disabled="isGenerating"
            @keydown="handleSingleInputKeydown"
            class="input-field"
          />
          <el-button
            v-if="!isGenerating"
            type="primary"
            class="action-button"
            :disabled="isSendButtonDisabled"
            @click="handleSendMessage"
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
          <el-button v-else type="warning" class="action-button" @click="handleStopGeneration">
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </div>
    </template>

    <ChatSettingsDrawer
      v-model:visible="settingsDrawerVisible"
      :chat-data="currentChat"
      :grouped-models="groupedModels"
      @save="handleSaveSettings"
    />

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      @append-content="handleAppendResourceContent"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElInput, ElMessage } from 'element-plus';
import { Promotion, VideoPause, Edit, Refresh, Document, Picture, Close } from '@element-plus/icons-vue';
import type { Ref } from 'vue';
import type { ChatUpdate, SubMessageCreate, AIModel } from '@/api/types';
import { uploadFile } from '@/api/chatService';

// --- Stores & Composables ---
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useChatInput } from '@/composables/useChatInput';
import { useResizablePanels } from '@/composables/useResizablePanels';
import { useTokenEstimator } from '@/composables/useTokenEstimator';

// --- Components ---
import MessageItem from './MessageItem.vue';
import ChatToolbar from './ChatToolbar.vue';
import MultiPartInput from './MultiPartInput.vue';
import ChatSettingsDrawer from './ChatSettingsDrawer.vue';
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue';

interface GroupedModels { label: string; options: AIModel[]; }

// --- Store Instances ---
const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const chatInteractionStore = useChatInteractionStore();
const providerStore = useProviderStore();

// --- State from Stores ---
const { refreshingTitleChatId } = storeToRefs(chatListStore);
const { currentChat, currentChatId, currentChatMessages, isChatHistoryLoading, isGenerating, contextForTokenEstimation } = storeToRefs(chatSessionStore);
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]>};

// --- State from Composables ---
const {
  isMultiPartMode,
  singlePartDraft,
  multiPartDraft,
  uploadedFiles,
  isReadyToSend,
  toggleMultiPartMode,
  currentUserInputText,
  addUploadedFile,
  removeUploadedFile,
  undo,
  redo,
  resetDraft,
  appendContentToDraft,
} = useChatInput(currentChatId);

const inputAreaHeight = ref(150);
const { startResize: startResizeInputArea } = useResizablePanels(inputAreaHeight, {
  min: 100, max: 600, orientation: 'vertical', inverted: true
});

const { estimatedTokens } = useTokenEstimator(contextForTokenEstimation, currentUserInputText);

// --- Local Component State ---
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const inputRef = ref<InstanceType<typeof ElInput>>();
const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>();
const fileInputRef = ref<HTMLInputElement | null>(null);
const settingsDrawerVisible = ref(false);
const resourceSelectorVisible = ref(false);
const isEditingTitle = ref(false);
const titleInput = ref('');
const titleInputRef = ref<InstanceType<typeof ElInput>>();
const userHasScrolledUp = ref(false);

// --- Computed Properties ---
const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value);

// --- Methods ---

/**
 * Handles appending content from the resource selector to the current input draft
 * and focuses the input area.
 * @param content The string content to append.
 */
async function handleAppendResourceContent(content: string) {
  appendContentToDraft(content);

  await nextTick();
  if (isMultiPartMode.value) {
    multiPartInputRef.value?.focus();
  } else {
    inputRef.value?.focus();
  }
}

// File Upload Logic
function handleTriggerFileUpload() {
  fileInputRef.value?.click();
}

async function onFileSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  if (!target.files) return;

  const files = Array.from(target.files);
  target.value = '';

  for (const file of files) {
    try {
      const fileInfo = await uploadFile(file);
      addUploadedFile(fileInfo);
    } catch (error) {
      console.error(`Failed to upload file ${file.name}:`, error);
    }
  }
}

// Send & Stop Logic
async function handleSendMessage() {
  if (isSendButtonDisabled.value) return;

  const textSubMessages: SubMessageCreate[] = isMultiPartMode.value
    ? (multiPartInputRef.value?.getData() || [])
    : singlePartDraft.value.trim() !== ''
      ? [{ content: singlePartDraft.value, sortOrder: 0, type: 'Normal' }]
      : [];

  const fileSubMessages: SubMessageCreate[] = uploadedFiles.value.map(file => ({
    content: file.id,
    type: 'File',
    sortOrder: 0
  }));

  const finalSubMessages = [...textSubMessages, ...fileSubMessages].map((subMessage, index) => ({
    ...subMessage,
    sortOrder: index,
  }));

  if (finalSubMessages.length > 0) {
    await chatInteractionStore.sendMessage(finalSubMessages);
    resetDraft();
  }
}

function handleStopGeneration() {
  const genMsg = currentChatMessages.value.find(m => m.status === 'generating');
  if (genMsg) chatInteractionStore.cancelGeneration(genMsg.id);
}

// Title Actions
function startTitleEdit() {
  if (!currentChat.value) return;
  isEditingTitle.value = true;
  titleInput.value = currentChat.value.name;
  nextTick(() => titleInputRef.value?.focus());
}

function saveTitle() {
  if (!currentChat.value || !isEditingTitle.value) return;
  const newName = titleInput.value.trim();
  if (newName && newName !== currentChat.value.name) {
    chatListStore.updateChatSettings(currentChat.value.id, { name: newName });
  }
  isEditingTitle.value = false;
}

function handleRefreshTitle() {
  if (currentChat.value) {
    chatListStore.refreshChatTitle(currentChat.value.id);
  }
}

// Settings
async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return;
  await chatListStore.updateChatSettings(currentChat.value.id, settings);
  settingsDrawerVisible.value = false;
  ElMessage.success('设置已保存');
}

// Keyboard & Scroll
function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    undo();
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    redo();
  }
}

function handleSingleInputKeydown(event: Event) {
  if (!(event instanceof KeyboardEvent)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSendMessage();
  }
}

const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const el = scrollbarRef.value?.wrapRef;
  if (!el) return;
  userHasScrolledUp.value = el.scrollHeight - el.clientHeight - scrollTop > 20;
};

const scrollToBottom = (force = false) => {
  if (!force && userHasScrolledUp.value && isGenerating.value) return;
  nextTick(() => {
    const scrollbar = scrollbarRef.value;
    if (scrollbar && scrollbar.wrapRef) {
      scrollbar.setScrollTop(scrollbar.wrapRef.scrollHeight);
    }
  });
};

// --- Watchers ---

watch(
  () => currentChatMessages.value[currentChatMessages.value.length - 1]?.sub_messages.slice(-1)[0]?.content,
  (newContent, oldContent) => {
    if (newContent !== oldContent) {
      scrollToBottom();
    }
  }
);

watch(currentChatId, (newId) => {
  if (newId) {
    isEditingTitle.value = false;
    userHasScrolledUp.value = false;

    const stopWatch = watch(isChatHistoryLoading, (loading) => {
      if (!loading) {
        scrollToBottom(true);
        nextTick(() => {
            inputRef.value?.focus();
        });
        stopWatch();
      }
    }, { immediate: true });
  }
});
</script>

<style scoped>
.chat-window-container { height: 100%; display: flex; flex-direction: column; background-color: var(--color-background); overflow: hidden; }
.welcome-view { display: flex; justify-content: center; align-items: center; height: 100%; }
.chat-window-header { flex-shrink: 0; padding: 0 20px; height: 60px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-border); }
.title-display-area { display: flex; align-items: center; gap: 8px; overflow: hidden; }
.chat-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--color-heading); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.title-actions { display: flex; align-items: center; }
.title-edit-area { width: 100%; }
.message-list-scrollbar { flex-grow: 1; }
.message-list-wrapper { padding: 20px; }
.input-container-wrapper { flex-shrink: 0; position: relative; display: flex; flex-direction: column; border-top: 1px solid var(--color-border); }
.resize-handle { position: absolute; top: -3px; left: 0; width: 100%; height: 6px; cursor: ns-resize; z-index: 10; }

.uploaded-files-preview {
  padding: 8px 20px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background-color: var(--color-background-soft);
  max-height: 100px; /* Example max height */
  overflow-y: auto;
}
.file-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  font-size: 13px;
}
.file-thumbnail {
  width: 24px;
  height: 24px;
  border-radius: 3px;
}
.image-slot-error {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.file-icon {
  font-size: 18px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
}
.file-name {
  max-width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.remove-file-btn {
  margin-left: 4px;
  font-size: 14px;
  --el-button-text-color: var(--el-text-color-placeholder);
}
.remove-file-btn:hover {
  --el-button-text-color: var(--el-color-danger);
  background-color: transparent;
}

.chat-input-area { flex-grow: 1; padding: 10px 20px; background-color: var(--color-background-soft); display: flex; align-items: stretch; min-height: 0; }
.input-field { flex-grow: 1; margin-right: 10px; }
.input-field:deep(.el-textarea__inner) { height: 100% !important; }
.action-button { width: 54px; font-size: 20px; flex-shrink: 0; align-self: flex-end; height: calc(100% - 2px); }
</style>
