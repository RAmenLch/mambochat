<!-- frontend/mambo/src/components/chat/ChatWindow.vue -->
<template>
  <div class="chat-window-container">
    <input type="file" ref="fileInputRef" @change="onFileSelected" multiple style="display: none;" />

    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <template v-else>
      <ChatHeader
        :current-chat="currentChat"
        :is-title-refreshing="isTitleRefreshing"
        @save-title="(newTitle) => chatListStore.updateChatSettings(currentChat!.id, { name: newTitle })"
        @refresh-title="handleRefreshTitle"
      />

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

        <AttachmentPreview
          :uploaded-files="uploadedFiles"
          :attached-resources="attachedSubmessageResources"
          @remove-file="removeUploadedFile"
          @remove-resource="removeAttachedResource"
        />

        <ChatInputBox
          ref="chatInputBoxRef"
          :is-multi-part-mode="isMultiPartMode"
          :is-generating="isGenerating"
          :is-send-button-disabled="isSendButtonDisabled"
          v-model:singlePartDraft="singlePartDraft"
          v-model:multiPartDraft="multiPartDraft"
          @send="handleSendMessage"
          @stop-generation="handleStopGeneration"
          @undo="undo"
          @redo="redo"
        />
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
      @select-resource="handleResourceSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElMessage } from 'element-plus';
import type { Ref } from 'vue';
import type { ChatUpdate, SubMessageCreate, AIModel, Resource } from '@/api/types';
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
import ChatSettingsDrawer from './ChatSettingsDrawer.vue';
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue';
import ChatHeader from './ChatHeader.vue';
import AttachmentPreview from './AttachmentPreview.vue';
import ChatInputBox from './ChatInputBox.vue';

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
  attachedSubmessageResources,
  isReadyToSend,
  toggleMultiPartMode,
  currentUserInputText,
  addUploadedFile,
  removeUploadedFile,
  addAttachedResource,
  removeAttachedResource,
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
const fileInputRef = ref<HTMLInputElement | null>(null);
const chatInputBoxRef = ref<InstanceType<typeof ChatInputBox>>();
const settingsDrawerVisible = ref(false);
const resourceSelectorVisible = ref(false);
const userHasScrolledUp = ref(false);

// --- Computed Properties ---
const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value);

// --- Methods ---

/**
 * Handles the selection of a resource from the resource selector dialog.
 * Appends content for system prompts or attaches submessage templates.
 * @param resource The selected resource object.
 */
async function handleResourceSelected(resource: Resource) {
  if (resource.resourceType === 'system_prompt') {
    if (resource.latest_version?.content) {
      appendContentToDraft(resource.latest_version.content);
      await nextTick();
      // Assuming ChatInputBox exposes a focus method
      chatInputBoxRef.value?.focus();
    }
  } else if (resource.resourceType === 'submessage_template') {
    addAttachedResource(resource);
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

  const textParts = isMultiPartMode.value
    ? multiPartDraft.value.map(p => p.content)
    : [singlePartDraft.value];

  const textSubMessages: SubMessageCreate[] = textParts
    .map(content => content.trim())
    .filter(content => content !== '')
    .map((content, index) => ({
      content,
      sortOrder: index,
      type: 'Normal',
    }));

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
    const attachedResourceIds = attachedSubmessageResources.value.map(r => r.id);
    await chatInteractionStore.sendMessage(finalSubMessages, attachedResourceIds);
    resetDraft();
  }
}

function handleStopGeneration() {
  const genMsg = currentChatMessages.value.find(m => m.status === 'generating');
  if (genMsg) chatInteractionStore.cancelGeneration(genMsg.id);
}

// Title Actions
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

// Scroll
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
    userHasScrolledUp.value = false;

    const stopWatch = watch(isChatHistoryLoading, (loading) => {
      if (!loading) {
        scrollToBottom(true);
        nextTick(() => {
            // Assuming ChatInputBox exposes a focus method
            chatInputBoxRef.value?.focus();
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
.message-list-scrollbar { flex-grow: 1; }
.message-list-wrapper { padding: 20px; }
.input-container-wrapper { flex-shrink: 0; position: relative; display: flex; flex-direction: column; border-top: 1px solid var(--color-border); }
.resize-handle { position: absolute; top: -3px; left: 0; width: 100%; height: 6px; cursor: ns-resize; z-index: 10; }
</style>
