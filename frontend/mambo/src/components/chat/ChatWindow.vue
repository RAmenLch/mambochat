<!-- frontend/mambo/src/components/chat/ChatWindow.vue -->
<template>
  <div class="chat-window-container">
    <input type="file" ref="fileInputRef" @change="onFileSelected" multiple style="display: none;" />

    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <template v-else>
      <!-- 仅在非折叠模式下显示 Header，折叠模式下 Header 显示在 ChatList 中 -->
      <ChatHeader
        v-if="!isSidebarCollapsed"
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
            :id="'msg-' + message.id"
            :message="message"
            :is-last-message="index === currentChatMessages.length - 1"
          />
        </div>
      </el-scrollbar>

      <div
        class="input-container-wrapper"
        :style="{ height: `${inputAreaHeight}px` }"
        @dragenter.prevent.stop="isDraggingOver = true"
        @dragover.prevent.stop
      >
        <!-- 拖拽文件时的覆盖层 -->
        <div
          v-if="isDraggingOver"
          class="drag-over-overlay"
          @dragleave.prevent.stop="isDraggingOver = false"
          @drop.prevent.stop="handleDrop"
        >
          <div class="drag-over-content">
            <el-icon size="50"><UploadFilled /></el-icon>
            <span>松开即可上传文件</span>
          </div>
        </div>

        <div class="resize-handle" @mousedown.prevent="startResizeInputArea"></div>
        <ChatToolbar
          :current-chat="currentChat"
          :messages="currentChatMessages"
          :estimated-tokens="estimatedTokens"
          @open-settings="settingsDrawerVisible = true"
          @toggle-multi-part-mode="toggleMultiPartMode"
          @trigger-file-upload="handleTriggerFileUpload"
          @open-resource-selector="resourceSelectorVisible = true"
          @jump-to-message="handleJumpToMessage"
          @toggle-bing-search="handleToggleBingSearch"
        />

        <AttachmentPreview
          ref="attachmentPreviewRef"
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
          :active-partition-index="activePartitionIndex"
          @update:active-partition-index="index => activePartitionIndex = index"
          @send="handleSendMessage"
          @stop-generation="handleStopGeneration"
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

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      @select-resource="handleResourceSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElMessage } from 'element-plus';
import { UploadFilled } from '@element-plus/icons-vue';
import type { Ref } from 'vue';
import type { ChatUpdate, SubMessageCreate, AIModel, Resource } from '@/api/types';
import { uploadFile } from '@/api/chatService';

// --- Stores & Composables ---
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
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

const props = defineProps<{
  isSidebarCollapsed: boolean;
}>();

// --- Store Instances ---
const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const chatInteractionStore = useChatInteractionStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();

// --- State from Stores ---
const { refreshingTitleChatId } = storeToRefs(chatListStore);
const { currentChat, currentChatId, currentChatMessages, isChatHistoryLoading, isGenerating, contextForTokenEstimation, searchTargetSubMessageId } = storeToRefs(chatSessionStore);
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]>};

// --- State from Composables ---
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

// --- Resizable Input Area Logic ---
const inputAreaHeight = ref(150);
const isInputAreaCollapsed = ref(false); // 用于配合 useResizablePanels，但在输入框上下调整场景下不涉及折叠逻辑
const MIN_INPUT_HEIGHT = 100;
const MAX_INPUT_HEIGHT = 600;

// useResizablePanels 需要 isCollapsed 参数，即使在此场景下不使用
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

// --- Local Component State ---
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const fileInputRef = ref<HTMLInputElement | null>(null);
const chatInputBoxRef = ref<InstanceType<typeof ChatInputBox>>();
const attachmentPreviewRef = ref<InstanceType<typeof AttachmentPreview> | null>(null);
const settingsDrawerVisible = ref(false);
const resourceSelectorVisible = ref(false);
const userHasScrolledUp = ref(false);
const previousPreviewHeight = ref(0);
const isDraggingOver = ref(false);

// --- Lifecycle Hooks ---
onMounted(() => {
  systemConfigStore.fetchSystemConfig();
});

// --- Computed Properties ---
const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value);

// --- Methods ---

async function handleResourceSelected(resources: Resource[]) {
  const promptContents: string[] = [];

  for (const resource of resources) {
    if (resource.resourceType === 'system_prompt') {
      if (resource.latest_version?.content) {
        promptContents.push(resource.latest_version.content);
      }
    } else if (resource.resourceType === 'submessage_template') {
      addAttachedResource(resource);
    }
  }

  if (promptContents.length > 0) {
    appendContentToDraft(promptContents.join('\n'));
    await nextTick();
    chatInputBoxRef.value?.focus();
  }
}

// --- File Upload Logic ---

async function handleFileUploads(files: FileList) {
  if (!files || files.length === 0) return;

  for (const file of Array.from(files)) {
    try {
      const fileInfo = await uploadFile(file);
      addUploadedFile(fileInfo);
    } catch (error) {
      console.error(`Failed to upload file ${file.name}:`, error);
      ElMessage.error(`文件 ${file.name} 上传失败`);
    }
  }
}

function handleDrop(event: DragEvent) {
  isDraggingOver.value = false;
  const files = event.dataTransfer?.files;
  if (files) {
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

// --- Send & Stop Logic ---
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

// --- Title Actions ---
function handleRefreshTitle() {
  if (currentChat.value) {
    chatListStore.refreshChatTitle(currentChat.value.id);
  }
}

// --- Settings & Tools ---
async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return;
  await chatListStore.updateChatSettings(currentChat.value.id, settings);
  settingsDrawerVisible.value = false;
  ElMessage.success('设置已保存');
}

/**
 * 处理 Bing 搜索工具的启用/停用切换。
 */
async function handleToggleBingSearch() {
  if (!currentChat.value) return;

  const BING_SEARCH_ID = 'bing-search';
  const currentParams = currentChat.value.modelParameters || {};
  const currentMcpIds: string[] = currentParams.enabled_mcp_ids || [];

  const isEnabled = currentMcpIds.includes(BING_SEARCH_ID);
  const newMcpIds = isEnabled
    ? currentMcpIds.filter(id => id !== BING_SEARCH_ID)
    : [...currentMcpIds, BING_SEARCH_ID];

  const updatedSettings: ChatUpdate = {
    modelParameters: {
      ...currentParams,
      enabled_mcp_ids: newMcpIds,
    },
  };

  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings);
  ElMessage.success(`联网搜索已${isEnabled ? '禁用' : '启用'}`);
}


// --- Scroll & Navigation ---
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

function handleJumpToMessage(messageId: string) {
  const elementId = `msg-${messageId}`;
  const element = document.getElementById(elementId);

  if (element && scrollbarRef.value) {
    const offset = element.offsetTop - 10;
    scrollbarRef.value.setScrollTop(offset);
  }
}

function handleJumpToSubMessage(subMessageId: string) {
  // 找到包含该subMessage的message
  const message = currentChatMessages.value.find(msg =>
    msg.sub_messages.some(sm => sm.id === subMessageId)
  );

  if (message) {
    // 1. 先尝试跳转到父消息位置，让滚动条大致到位
    handleJumpToMessage(message.id);

    // 2. 使用双重 nextTick 确保子组件（如 SubMessageItem）已完全展开并渲染
    nextTick(() => {
      nextTick(() => {
        const subMessageElement = document.getElementById(`sub-msg-${subMessageId}`);
        const scrollbarWrap = scrollbarRef.value?.wrapRef;

        if (subMessageElement && scrollbarWrap) {
          // 获取subMessage相对于滚动容器的实际位置
          const elementRect = subMessageElement.getBoundingClientRect();
          const containerRect = scrollbarWrap.getBoundingClientRect();

          // 计算相对位移
          const relativeTop = elementRect.top - containerRect.top;
          const currentScrollTop = scrollbarWrap.scrollTop;

          // 目标位置 = 当前滚动位置 + 相对位移 - 顶部留白(20px)
          const offset = currentScrollTop + relativeTop - 20;

          scrollbarRef.value!.setScrollTop(offset);

          // 高亮显示该subMessage
          subMessageElement.classList.add('search-highlight-target');
          setTimeout(() => {
            subMessageElement.classList.remove('search-highlight-target');
          }, 3000);
        }
      });
    });
  }
}

// --- Watchers ---

watch([uploadedFiles, attachedSubmessageResources], async () => {
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

    const stopWatch = watch(isChatHistoryLoading, (loading) => {
      if (!loading) {
        if (searchTargetSubMessageId.value) {
          // 场景 A: 有搜索目标，执行精准跳转，不滚动到底部
          handleJumpToSubMessage(searchTargetSubMessageId.value);
          chatSessionStore.setSearchTarget(null); // 跳转后清除目标
        } else {
          // 场景 B: 普通切换，滚动到底部
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
.message-list-scrollbar { flex-grow: 1; }
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

/* 搜索高亮目标样式 */
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

/* 覆盖 Element Plus 滚动条样式 */
.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical) {
  width: 14px; /* 增加感应区域宽度 */
}

/* 默认视觉状态：细条、靠右 */
.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical .el-scrollbar__thumb) {
  width: 6px;
  margin-left: auto;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 交互状态（悬停或拖动）：变宽 */
.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical:hover .el-scrollbar__thumb),
.message-list-scrollbar :deep(.el-scrollbar__bar.is-vertical:active .el-scrollbar__thumb) {
  width: 14px;
}
</style>
