<!-- frontend/mambo/src/components/chat/ChatWindow.vue -->
<template>
  <div class="chat-window-container">
    <input type="file" ref="fileInputRef" @change="onFileSelected" multiple style="display: none;" />

    <div v-if="!currentChat" class="welcome-view">
      <el-empty :description="$t('chat.window.welcome')" />
    </div>

    <template v-else>
      <ChatHeader
        v-if="!isSidebarCollapsed"
        :current-chat="currentChat"
        :is-title-refreshing="isTitleRefreshing"
        :messages="currentChatMessages"
        @save-title="(newTitle) => chatListStore.updateChatSettings(currentChat!.id, { name: newTitle })"
        @refresh-title="handleRefreshTitle"
      />

      <div class="scroll-area-wrapper">
        <el-scrollbar ref="scrollbarRef" class="message-list-scrollbar" v-loading="isChatHistoryLoading" @scroll="handleScroll">
          <div class="message-list-wrapper">
            <MessageItem
              v-for="(message, index) in currentChatMessages"
              :key="message.id"
              :id="'msg-' + message.id"
              :message="message"
              :is-last-message="index === currentChatMessages.length - 1"
              @suggestion-click="handleSuggestionClick"
              @open-tool-dialog="handleOpenToolDialog"
            />
          </div>
        </el-scrollbar>

        <ChatNavigator
          :messages="currentChatMessages"
          :active-message-id="currentVisibleMessageId"
          @jump="handleJumpToMessage"
        />
      </div>

      <div
        class="input-container-wrapper"
        :style="{ height: `${inputAreaHeight}px` }"
        @dragenter.prevent.stop="handleContainerDragEnter"
        @dragover.prevent.stop="handleContainerDragOver"
        @drop.prevent.stop="handleContainerDrop"
      >
        <div
          v-if="isDraggingOver"
          class="drag-over-overlay"
          @dragleave.prevent.stop="isDraggingOver = false"
          @drop.prevent.stop="handleContainerDrop"
        >
          <div class="drag-over-content">
            <el-icon size="50"><UploadFilled /></el-icon>
            <span>{{ $t('chat.window.dropFiles') }}</span>
          </div>
        </div>

        <div class="resize-handle" @mousedown.prevent="startResizeInputArea"></div>
        <ChatToolbar
          :current-chat="currentChat"
          :messages="currentChatMessages"
          :estimated-tokens="estimatedTokens"
          @open-settings="handleOpenSettings"
          @toggle-multi-part-mode="toggleMultiPartMode"
          @trigger-file-upload="handleTriggerFileUpload"
          @open-resource-selector="resourceSelectorVisible = true"
          @jump-to-message="handleJumpToMessage"
          @toggle-web-search="handleToggleWebSearch"
          @toggle-mcp-tool="handleToggleMcpTool"
        />

        <AttachmentPreview
          ref="attachmentPreviewRef"
          :uploaded-files="uploadedFiles"
          :attached-resources="attachedSubmessageResources"
          :attached-knowledge-bases="attachedKnowledgeBases"
          @remove-file="removeUploadedFile"
          @remove-resource="removeAttachedResource"
          @remove-knowledge-base="handleRemoveKnowledgeBase"
          @update:attached-resources="(newList) => attachedSubmessageResources = newList"
        />

        <ChatInputBox
          ref="chatInputBoxRef"
          :is-multi-part-mode="isMultiPartMode"
          :is-generating="isGenerating"
          :is-send-button-disabled="isSendButtonDisabled"
          :is-pending-review="isPendingReview"
          v-model:singlePartDraft="singlePartDraft"
          v-model:multiPartDraft="multiPartDraft"
          :active-partition-index="activePartitionIndex"
          @update:active-partition-index="index => activePartitionIndex = index"
          @send="handleSendMessage"
          @stop-generation="handleStopGeneration"
          @open-review="handleOpenReviewFromInput"
          @undo="undo"
          @redo="redo"
          @files-pasted="handleFileUploads"
        />
      </div>
    </template>

    <ChatSettingsDrawer
      v-model:visible="settingsDrawerVisible"
      :chat-data="currentChat"
      :grouped-models="groupedModels"
      @save="handleSaveSettings"
    />

    <ChatAgentSettingsDrawer
      v-model:visible="agentSettingsDrawerVisible"
      :chat-data="currentChat"
      @save="handleSaveAgentSettings"
    />

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      context="chat-toolbar"
      @mount-resources="handleMountResources"
      @append-resources="handleAppendResources"
      @mount-knowledge-base="handleMountKnowledgeBase"
    />

    <McpToolDialog
      v-model:visible="toolDialogVisible"
      :parent-message-id="toolDialogMessageId"
      :initial-sub-message-id="toolDialogInitialId"
      :mode="toolDialogMode"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElMessage } from 'element-plus';
import { UploadFilled } from '@element-plus/icons-vue';
import type { Ref } from 'vue';
import type { ChatUpdate, SubMessageCreate, AIModel, Resource, Message, SubMessage } from '@/api/types';
import { uploadFile } from '@/api/fileService';

import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useChatInput } from '@/composables/useChatInput';
import { useResizablePanels } from '@/composables/useResizablePanels';
import { useTokenEstimator } from '@/composables/useTokenEstimator';

import MessageItem from './MessageItem.vue';
import ChatToolbar from './ChatToolbar.vue';
import ChatSettingsDrawer from './ChatSettingsDrawer.vue';
import ChatAgentSettingsDrawer from './ChatAgentSettingsDrawer.vue';
import ResourceSelectorDialog from '../common/dialogs/ResourceSelectorDialog.vue';
import ChatHeader from './ChatHeader.vue';
import AttachmentPreview from './AttachmentPreview.vue';
import ChatInputBox from './ChatInputBox.vue';
import McpToolDialog from './dialogs/McpToolDialog.vue';
import ChatNavigator from './ChatNavigator.vue';

interface GroupedModels { label: string; options: AIModel[]; }

const props = defineProps<{
  isSidebarCollapsed: boolean;
}>();

const { t } = useI18n();

const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const chatInteractionStore = useChatInteractionStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();

const { refreshingTitleChatId } = storeToRefs(chatListStore);
const {
  currentChat,
  currentChatId,
  currentChatMessages,
  isChatHistoryLoading,
  isGenerating,
  contextForTokenEstimation,
  searchTargetSubMessageId,
  systemPromptResources
} = storeToRefs(chatSessionStore);
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]>};

const {
  isMultiPartMode,
  singlePartDraft,
  multiPartDraft,
  activePartitionIndex,
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
const isInputAreaCollapsed = ref(false);
const MIN_INPUT_HEIGHT = 100;
const MAX_INPUT_HEIGHT = 600;

const { startResize: startResizeInputArea } = useResizablePanels(inputAreaHeight, isInputAreaCollapsed, {
  min: MIN_INPUT_HEIGHT,
  max: MAX_INPUT_HEIGHT,
  orientation: 'vertical',
  inverted: true
});

const pendingMessageTextForTokenEstimation = computed(() => {
  const parts: string[] = [];
  if (currentUserInputText.value) {
    parts.push(currentUserInputText.value);
  }
  attachedSubmessageResources.value.forEach(resource => {
    if (resource.resourceType === 'submessage_template' && resource.latest_version) {
      const cpl = resource.latest_version.attributes?.context_participation_length;
      if (cpl === undefined || cpl === null || (typeof cpl === 'number' && cpl >= 1)) {
        if (resource.latest_version.content) {
          parts.push(resource.latest_version.content);
        }
      }
    }
  });
  return parts.join('\n');
});

const { estimatedTokens } = useTokenEstimator(contextForTokenEstimation, pendingMessageTextForTokenEstimation);

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const fileInputRef = ref<HTMLInputElement | null>(null);
const chatInputBoxRef = ref<InstanceType<typeof ChatInputBox>>();
const attachmentPreviewRef = ref<InstanceType<typeof AttachmentPreview> | null>(null);
const settingsDrawerVisible = ref(false);
const agentSettingsDrawerVisible = ref(false);
const resourceSelectorVisible = ref(false);
const userHasScrolledUp = ref(false);
const previousPreviewHeight = ref(0);
const isDraggingOver = ref(false);

// 新增：当前视口可见的消息ID
const currentVisibleMessageId = ref<string | null>(null);

const toolDialogVisible = ref(false);
const toolDialogMessageId = ref<string | null>(null);
const toolDialogInitialId = ref<string | undefined>(undefined);
const toolDialogMode = ref<'review_all' | 'single'>('single');

onMounted(() => {
  systemConfigStore.fetchSystemConfig();
});

const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value);

const attachedKnowledgeBases = computed(() => {
  return systemPromptResources.value.filter(r => r.resourceType === 'knowledge_base');
});

const pendingReviewSubMessages = computed<SubMessage[]>(() => {
  const pendingMsg = currentChatMessages.value.find(msg => msg.status === 'pending_review');
  if (!pendingMsg) return [];
  return pendingMsg.sub_messages.filter(sm => sm.type === 'ReviewTool' && sm.status === 'pending_review');
});

const isPendingReview = computed(() => pendingReviewSubMessages.value.length > 0);

function handleOpenToolDialog(message: Message, subMessageId: string, mode: 'review_all' | 'single' = 'single') {
  toolDialogMessageId.value = message.id;
  toolDialogInitialId.value = subMessageId;
  toolDialogMode.value = mode;
  toolDialogVisible.value = true;
}

function handleOpenReviewFromInput() {
  if (pendingReviewSubMessages.value.length > 0) {
    const pendingSubMsg = pendingReviewSubMessages.value[0];
    const parentMsg = currentChatMessages.value.find(m => m.id === pendingSubMsg.messageId);
    if (parentMsg) {
      handleOpenToolDialog(parentMsg, pendingSubMsg.id, 'review_all');
    }
  }
}

async function handleMountResources(resources: Resource[]) {
  let hasFileAdded = false;
  for (const resource of resources) {
    if (resource.resourceType === 'submessage_template') {
      addAttachedResource(resource);
    } else if (resource.resourceType === 'file') {
      const fileInfo = resource.latest_version?.file_info;
      if (fileInfo) {
        addUploadedFile(fileInfo);
        hasFileAdded = true;
      } else {
        ElMessage.warning(t('chat.attachment.resourceFileEmpty', { name: resource.name }));
      }
    }
  }
  if (hasFileAdded) {
    ElMessage.success(t('chat.attachment.resourceFileAdded'));
  }
}

async function handleAppendResources(resources: Resource[]) {
  const contentsToAppend = resources
    .map(res => res.latest_version?.content)
    .filter((content): content is string => !!content);

  if (contentsToAppend.length > 0) {
    appendContentToDraft(contentsToAppend.join('\n'));
    await nextTick();
    chatInputBoxRef.value?.focus();
  }
}

async function handleMountKnowledgeBase(resources: Resource[]) {
  if (!currentChat.value) return;
  const currentList = currentChat.value.resource_prompt_list || [];
  const newIds = resources.map(r => r.id).filter(id => !currentList.includes(id));
  if (newIds.length > 0) {
    const updatedList = [...currentList, ...newIds];
    await chatListStore.updateChatSettings(currentChat.value.id, {
      resource_prompt_list: updatedList
    });
    ElMessage.success(t('chat.attachment.kbEnabled', { names: resources.map(r => r.name).join(', ') }));
  }
}

async function handleRemoveKnowledgeBase(resourceId: string) {
  if (!currentChat.value) return;
  const currentList = currentChat.value.resource_prompt_list || [];
  const updatedList = currentList.filter(id => id !== resourceId);
  await chatListStore.updateChatSettings(currentChat.value.id, {
    resource_prompt_list: updatedList.length > 0 ? updatedList : null
  });
  ElMessage.success(t('chat.attachment.kbDisabled'));
}

async function handleFileUploads(files: FileList) {
  if (!files || files.length === 0) return;
  for (const file of Array.from(files)) {
    try {
      const fileInfo = await uploadFile(file);
      addUploadedFile(fileInfo);
    } catch (error) {
      console.error(`Failed to upload file ${file.name}:`, error);
      ElMessage.error(t('chat.attachment.fileUploadFailed', { name: file.name }));
    }
  }
}

function handleContainerDragEnter(event: DragEvent) {
  if (event.dataTransfer && event.dataTransfer.types.includes('Files')) {
    isDraggingOver.value = true;
  }
}

function handleContainerDragOver(event: DragEvent) {
  if (isDraggingOver.value && event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy';
  }
}

function handleContainerDrop(event: DragEvent) {
  isDraggingOver.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    handleFileUploads(files);
  }
}

function handleTriggerFileUpload() {
  fileInputRef.value?.click();
}

async function onFileSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  if (!target.files) return;
  await handleFileUploads(target.files);
  target.value = '';
}

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

function handleRefreshTitle() {
  if (currentChat.value) {
    chatListStore.refreshChatTitle(currentChat.value.id);
  }
}

async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return;
  const finalSettings = { ...settings };
  if (settings.resource_prompt_list !== undefined) {
    const kbIds = attachedKnowledgeBases.value.map(r => r.id);
    const promptIds = settings.resource_prompt_list || [];
    finalSettings.resource_prompt_list = [...new Set([...promptIds, ...kbIds])];
  }
  await chatListStore.updateChatSettings(currentChat.value.id, finalSettings);
  settingsDrawerVisible.value = false;
  ElMessage.success(t('chat.settings.saveSuccess'));
}

async function handleSaveAgentSettings(settings: ChatUpdate) {
  if (!currentChat.value) return;
  await chatListStore.updateChatSettings(currentChat.value.id, settings);
  agentSettingsDrawerVisible.value = false;
  ElMessage.success(t('chat.settings.saveSuccess'));
}

function handleOpenSettings() {
  if (currentChat.value?.chatMode === 'agent') {
    agentSettingsDrawerVisible.value = true;
  } else {
    settingsDrawerVisible.value = true;
  }
}

async function handleToggleWebSearch() {
  if (!currentChat.value) return;
  const SEARCH_TOOL_ID = 'system-ddgs-search';
  const currentIds = currentChat.value.enabled_mcp_ids || [];
  const newIds = currentIds.includes(SEARCH_TOOL_ID)
    ? currentIds.filter(id => id !== SEARCH_TOOL_ID)
    : [...currentIds, SEARCH_TOOL_ID];
  await chatListStore.updateChatSettings(currentChat.value.id, { enabled_mcp_ids: newIds });
  ElMessage.success(newIds.includes(SEARCH_TOOL_ID) ? t('chat.toolbar.webSearchEnabled') : t('chat.toolbar.webSearchDisabled'));
}

async function handleToggleMcpTool(mcpId: string) {
  if (!currentChat.value) return;
  const currentIds = currentChat.value.enabled_mcp_ids || [];
  const newIds = currentIds.includes(mcpId)
    ? currentIds.filter(id => id !== mcpId)
    : [...currentIds, mcpId];
  await chatListStore.updateChatSettings(currentChat.value.id, { enabled_mcp_ids: newIds });
}



// 计算当前视口可见的消息ID (只检测用户消息)
const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const el = scrollbarRef.value?.wrapRef;
  if (!el) return;

  userHasScrolledUp.value = el.scrollHeight - el.clientHeight - scrollTop > 20;

  const containerRect = el.getBoundingClientRect();
  // 设定检测线为视口顶部往下 30% 处，符合阅读视线习惯
  const detectY = containerRect.top + containerRect.height * 0.3;

  let activeUserId: string | null = null;

  // 仅筛选出用户消息
  const userMsgs = currentChatMessages.value.filter(m => m.role === 'user');

  // 倒序遍历，找到最后一个突破检测线的用户消息
  for (let i = userMsgs.length - 1; i >= 0; i--) {
    const msg = userMsgs[i];
    const dom = document.getElementById(`msg-${msg.id}`);
    if (dom) {
      const rect = dom.getBoundingClientRect();
      if (rect.top <= detectY) {
        activeUserId = msg.id;
        break;
      }
    }
  }

  // 如果所有用户消息都在检测线下方，则默认选中第一条
  if (!activeUserId && userMsgs.length > 0) {
    activeUserId = userMsgs[0].id;
  }

  if (activeUserId) {
    currentVisibleMessageId.value = activeUserId;
  }
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

function handleJumpToMessage(messageId: string) {
  const elementId = `msg-${messageId}`;
  const element = document.getElementById(elementId);

  if (element && scrollbarRef.value) {
    const offset = element.offsetTop - 10;
    scrollbarRef.value.setScrollTop(offset);
  }
}

function handleJumpToSubMessage(subMessageId: string) {
  const message = currentChatMessages.value.find(msg =>
    msg.sub_messages.some(sm => sm.id === subMessageId)
  );

  if (message) {
    handleJumpToMessage(message.id);

    nextTick(() => {
      nextTick(() => {
        const subMessageElement = document.getElementById(`sub-msg-${subMessageId}`);
        const scrollbarWrap = scrollbarRef.value?.wrapRef;

        if (subMessageElement && scrollbarWrap) {
          const elementRect = subMessageElement.getBoundingClientRect();
          const containerRect = scrollbarWrap.getBoundingClientRect();
          const relativeTop = elementRect.top - containerRect.top;
          const currentScrollTop = scrollbarWrap.scrollTop;
          const offset = currentScrollTop + relativeTop - 20;

          scrollbarRef.value!.setScrollTop(offset);

          subMessageElement.classList.add('search-highlight-target');
          setTimeout(() => {
            subMessageElement.classList.remove('search-highlight-target');
          }, 3000);
        }
      });
    });
  }
}

function handleSuggestionClick(text: string) {
  if (isMultiPartMode.value) {
    if (multiPartDraft.value[activePartitionIndex.value]) {
       multiPartDraft.value[activePartitionIndex.value].content = text;
    }
  } else {
    singlePartDraft.value = text;
  }
  nextTick(() => {
    chatInputBoxRef.value?.focus();
  });
}

watch([uploadedFiles, attachedSubmessageResources, attachedKnowledgeBases], async () => {
  await nextTick();
  const previewEl = (attachmentPreviewRef.value?.$el as HTMLDivElement);
  const currentPreviewHeight = previewEl?.offsetHeight ?? 0;
  const heightDifference = currentPreviewHeight - previousPreviewHeight.value;

  if (heightDifference !== 0) {
    const newTotalHeight = inputAreaHeight.value + heightDifference;
    inputAreaHeight.value = Math.max(MIN_INPUT_HEIGHT, Math.min(newTotalHeight, MAX_INPUT_HEIGHT));
  }
  previousPreviewHeight.value = currentPreviewHeight;
}, { deep: true });

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
    previousPreviewHeight.value = 0;
    currentVisibleMessageId.value = null; // 重置

    const stopWatch = watch(isChatHistoryLoading, (loading) => {
      if (!loading) {
        if (searchTargetSubMessageId.value) {
          handleJumpToSubMessage(searchTargetSubMessageId.value);
          chatSessionStore.setSearchTarget(null);
        } else {
          scrollToBottom(true);
        }
        nextTick(() => {
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

.scroll-area-wrapper {
  position: relative;
  flex-grow: 1;
  display: flex;
  overflow: hidden;
}

.message-list-scrollbar { width: 100%; height: 100%; }
.message-list-wrapper { padding: 20px; }
.input-container-wrapper { flex-shrink: 0; position: relative; display: flex; flex-direction: column; border-top: 1px solid var(--color-border); }
.resize-handle { position: absolute; top: -3px; left: 0; width: 100%; height: 6px; cursor: ns-resize; z-index: 10; }

.drag-over-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 123, 255, 0.1);
  border: 2px dashed var(--el-color-primary);
  border-radius: 4px;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 20;
  pointer-events: all;
}

.drag-over-content {
  text-align: center;
  color: var(--el-color-primary);
}

.drag-over-content span {
  display: block;
  margin-top: 8px;
  font-weight: bold;
}

:deep(.search-highlight-target) {
  animation: highlight-pulse 0.5s ease-in-out 3;
  background-color: var(--el-color-warning-light-9);
  border-radius: 6px;
  box-shadow: 0 0 8px var(--el-color-warning-light-5);
}

@keyframes highlight-pulse {
  0%, 100% {
    background-color: var(--el-color-warning-light-9);
    box-shadow: 0 0 8px var(--el-color-warning-light-7);
  }
  50% {
    background-color: var(--el-color-warning-light-7);
    box-shadow: 0 0 12px var(--el-color-warning-light-5);
  }
}

.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical) {
  width: 14px;
}

.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical .el-scrollbar__thumb) {
  width: 6px;
  margin-left: auto;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical:hover .el-scrollbar__thumb),
.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical:active .el-scrollbar__thumb) {
  width: 14px;
}
</style>
