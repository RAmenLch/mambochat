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
        @imported="handleChatImported"
      />

      <div class="scroll-area-wrapper">
        <el-scrollbar ref="scrollbarRef" class="message-list-scrollbar" v-loading="isChatHistoryLoading" @scroll="handleScroll">
          <div class="message-list-wrapper" :class="{ 'gal-shifted': galAvatarState.visible }">
            <MessageItem
              v-for="(message, index) in currentChatMessages"
              :key="message.id"
              :id="'msg-' + message.id"
              :message="message"
              :is-last-message="index === currentChatMessages.length - 1"
              :hide-avatar="galAvatarState.visible && message.role === 'assistant' && hasGalAvatar(message)"
              @suggestion-click="handleSuggestionClick"
              @open-tool-dialog="handleOpenToolDialog"
              @view-logs="handleViewLogs"
              @duplicate-upto="handleDuplicateUpTo"
              @switch-branch="(targetId) => handleSwitchBranch(message.id, targetId)"
            />
          </div>
        </el-scrollbar>

        <ChatNavigator
          :messages="currentChatMessages"
          :active-message-id="currentVisibleMessageId"
          @jump="handleJumpToMessage"
        />
      </div>

      <transition name="gal-fade">
        <div v-if="galAvatarState.visible" class="gal-avatar-panel">
          <transition name="gal-img">
            <img :key="galAvatarState.imageUrl ?? undefined" :src="galAvatarState.imageUrl!" class="gal-avatar-image" />
          </transition>
        </div>
      </transition>

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
          @open-version-history="versionHistoryDrawerVisible = true"
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
          :agent-id="resourceCompletionAgentId"
          v-model:singlePartDraft="singlePartDraft"
          v-model:multiPartDraft="multiPartDraft"
          :active-partition-index="activePartitionIndex"
          @update:active-partition-index="(index: number) => activePartitionIndex = index"
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

    <VersionHistoryDrawer
      v-model:visible="versionHistoryDrawerVisible"
      :chat-id="currentChatId"
      :messages="currentChatMessages"
      @refreshed="handleVersionHistoryRefreshed"
    />

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      :context="currentChat?.chatMode === 'agent' ? 'agent-toolbar' : 'chat-toolbar'"
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

    <AskUserDialog
      v-model:visible="askUserDialogVisible"
      :parent-message-id="askUserDialogMessageId"
      :initial-sub-message-id="askUserDialogInitialSubMessageId"
    />

    <LogViewerDialog
      v-model:visible="logDialogVisible"
      :message-id="logDialogMessageId"
      :chat-id="currentChatId"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElMessage } from 'element-plus';
import { UploadFilled } from '@element-plus/icons-vue';
import type { Ref } from 'vue';
import type { ChatUpdate, SubMessageCreate, AIModel, Resource, Message, SubMessage } from '@/api/types';
import { uploadFile } from '@/api/fileService';
import { duplicateChat } from '@/api/chatService';

import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useAgentStore } from '@/stores/agentStore';
import { useBackendStore } from '@/stores/backendStore';
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
import AskUserDialog from './dialogs/AskUserDialog.vue';
import LogViewerDialog from './dialogs/LogViewerDialog.vue';
import ChatNavigator from './ChatNavigator.vue';
import VersionHistoryDrawer from './dialogs/VersionHistoryDrawer.vue';

interface GroupedModels { label: string; options: AIModel[]; }

const props = defineProps<{
  isSidebarCollapsed: boolean;
}>();

const { t } = useI18n();
const router = useRouter();

const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const chatInteractionStore = useChatInteractionStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const agentStore = useAgentStore();
const backendStore = useBackendStore();

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
const isSwitchingBranch = ref(false);
const versionHistoryDrawerVisible = ref(false);

const currentVisibleMessageId = ref<string | null>(null);

/** Gal_Avatar 模式：查找当前活跃的 Gal 头像图片 */
const galAvatarImageUrl = ref<string | null>(null)
const galIsScrolledPast = ref(false)

// 所有包含 Gal_Avatar 的消息：messageId → imageUrl
const galAvatarMap = computed(() => {
  const map = new Map<string, string>()
  for (const msg of currentChatMessages.value) {
    const file = msg.sub_messages.find(
      sm => sm.type === 'File' &&
        sm.config?.show_tool_mode === 'Gal_Avatar' &&
        sm.file_info?.mime_type?.startsWith('image/')
    )
    if (file) {
      map.set(msg.id, file.file_info!.url)
    }
  }
  return map
})

const galAvatarState = computed(() => ({
  visible: galAvatarImageUrl.value !== null && !galIsScrolledPast.value,
  imageUrl: galAvatarImageUrl.value,
  messageId: null as string | null,
}))

/** 判断某条消息是否含有 Gal_Avatar（用于隐藏该消息的头像） */
function hasGalAvatar(msg: Message): boolean {
  return msg.sub_messages.some(
    sm => sm.type === 'File' &&
      sm.config?.show_tool_mode === 'Gal_Avatar' &&
      sm.file_info?.mime_type?.startsWith('image/')
  )
}

/** 根据当前视口内容更新 Gal_Avatar 显隐状态（无滚动事件时也需主动调用） */
function updateGalAvatarState(): void {
  const el = scrollbarRef.value?.wrapRef;
  if (!el) return;

  const containerRect = el.getBoundingClientRect();

  if (galAvatarMap.value.size > 0) {
    let bestUrl: string | null = null

    for (const [msgId, url] of galAvatarMap.value) {
      const dom = document.getElementById(`msg-${msgId}`)
      if (!dom) continue
      const rect = dom.getBoundingClientRect()

      // 消息在滚动容器内（至少部分可见）→ 显示它的 Gal_Avatar
      if (rect.bottom > containerRect.top && rect.top < containerRect.bottom) {
        bestUrl = url
        break // 优先第一个可见的（从前往后遍历，即最早的消息）
      }
    }

    if (bestUrl) {
      galAvatarImageUrl.value = bestUrl
      galIsScrolledPast.value = false
    } else {
      galIsScrolledPast.value = true
    }
  } else {
    galAvatarImageUrl.value = null
    galIsScrolledPast.value = true
  }
}

// Gal_Avatar 消息集合变化（增删 / 图片就绪）时主动重新检测，
// 避免内容不足无滚动事件导致立绘不显示或残留
watch(galAvatarMap, () => {
  nextTick(() => updateGalAvatarState());
});

function onWindowResize() {
  nextTick(() => updateGalAvatarState());
}

const toolDialogVisible = ref(false);
const toolDialogMessageId = ref<string | null>(null);
const toolDialogInitialId = ref<string | undefined>(undefined);
const toolDialogMode = ref<'review_all' | 'single'>('single');

const askUserDialogVisible = ref(false);
const askUserDialogMessageId = ref<string | null>(null);
/** 单合模式：指定打开的 subMessageId（时间线点击）；null = 多合模式（所有 pending） */
const askUserDialogInitialSubMessageId = ref<string | null>(null);

const logDialogVisible = ref(false);
const logDialogMessageId = ref<string | null>(null);

onMounted(() => {
  systemConfigStore.fetchSystemConfig();
  if (agentStore.allAgents.length === 0) {
    agentStore.fetchAllAgents();
  }
  if (backendStore.backendList.length === 0) {
    backendStore.fetchBackends();
  }
  nextTick(() => updateGalAvatarState());
  window.addEventListener('resize', onWindowResize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize);
});

// 仅当当前会话 Agent 挂载了 ResourceBackend 时才启用资源补全，
// 避免未挂载的 Agent 触发补全接口
const resourceCompletionAgentId = computed(() => {
  const chat = currentChat.value;
  if (!chat?.agentId) return null;

  const agent =
    agentStore.allAgents.find((a) => a.id === chat.agentId) ||
    agentStore.agentList.find((a) => a.id === chat.agentId);
  if (!agent?.backendIds || agent.backendIds.length === 0) return null;

  const mountedIds = new Set(agent.backendIds);
  const hasResourceBackend = backendStore.backendList.some(
    (b) => b.backendType === 'resource' && mountedIds.has(b.id),
  );
  return hasResourceBackend ? chat.agentId : null;
});

const isTitleRefreshing = computed(() => refreshingTitleChatId.value === currentChat.value?.id);
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value);

const attachedKnowledgeBases = computed(() => {
  return systemPromptResources.value.filter(r => r.resourceType === 'knowledge_base');
});

const pendingReviewSubMessages = computed<SubMessage[]>(() => {
  const pendingMsg = currentChatMessages.value.find(msg => msg.status === 'pending_review');
  if (!pendingMsg) return [];
  return pendingMsg.sub_messages.filter(
    sm => (sm.type === 'ReviewTool' || sm.type === 'AskUser') && sm.status === 'pending_review'
  );
});

const isPendingReview = computed(() => pendingReviewSubMessages.value.length > 0);

function handleOpenToolDialog(message: Message, subMessageId: string, mode: 'review_all' | 'single' = 'single') {
  // 检查是否是 AskUser 类型，打开对应的对话框
  const sub = message.sub_messages.find(sm => sm.id === subMessageId);
  if (sub && sub.type === 'AskUser') {
    handleOpenAskUserDialog(message, sub);
    return;
  }
  toolDialogMessageId.value = message.id;
  toolDialogInitialId.value = subMessageId;
  toolDialogMode.value = mode;
  toolDialogVisible.value = true;
}

function handleOpenAskUserDialog(message: Message, subMessage: SubMessage) {
  askUserDialogMessageId.value = message.id;
  askUserDialogInitialSubMessageId.value = subMessage.id;
  askUserDialogVisible.value = true;
}

function handleViewLogs(messageId: string) {
  logDialogMessageId.value = messageId;
  logDialogVisible.value = true;
}

function handleOpenReviewFromInput() {
  if (pendingReviewSubMessages.value.length > 0) {
    const firstSubMsg = pendingReviewSubMessages.value[0];
    const parentMsg = currentChatMessages.value.find(m => m.id === firstSubMsg.messageId);
    if (parentMsg) {
      if (firstSubMsg.type === 'AskUser') {
        askUserDialogMessageId.value = parentMsg.id;
        askUserDialogInitialSubMessageId.value = null;  // 多合模式：显示所有 pending
        askUserDialogVisible.value = true;
      } else {
        handleOpenToolDialog(parentMsg, firstSubMsg.id, 'review_all');
      }
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

async function handleChatImported(chatId: string) {
  // 刷新会话树并跳转到新导入的会话
  await chatListStore.initializeList();
  await chatSessionStore.selectChat(chatId);
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
  const currentMode = currentChat.value.web_search_mode;
  let nextMode: 'direct_read' | 'search_and_read' | 'disable';
  if (!currentMode || currentMode === 'disable') {
    nextMode = 'direct_read';
  } else if (currentMode === 'direct_read') {
    nextMode = 'search_and_read';
  } else {
    nextMode = 'disable';
  }
  await chatListStore.updateChatSettings(currentChat.value.id, { web_search_mode: nextMode });
  if (nextMode === 'direct_read') {
    ElMessage.success(t('chat.toolbar.webSearchEnabled'));
  } else if (nextMode === 'search_and_read') {
    ElMessage.success(t('chat.toolbar.webSearchEnabled'));
  } else {
    ElMessage.info(t('chat.toolbar.webSearchDisabled'));
  }
}

async function handleToggleMcpTool(mcpId: string) {
  if (!currentChat.value) return;
  const currentIds = currentChat.value.enabled_mcp_ids || [];
  const newIds = currentIds.includes(mcpId)
    ? currentIds.filter(id => id !== mcpId)
    : [...currentIds, mcpId];
  await chatListStore.updateChatSettings(currentChat.value.id, { enabled_mcp_ids: newIds });
}

function handleVersionHistoryRefreshed() {
  if (currentChatId.value) {
    chatSessionStore.selectChat(currentChatId.value, true);
  }
}

const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const el = scrollbarRef.value?.wrapRef;
  if (!el) return;

  userHasScrolledUp.value = el.scrollHeight - el.clientHeight - scrollTop > 20;

  const containerRect = el.getBoundingClientRect();
  const detectY = containerRect.top + containerRect.height * 0.3;

  let activeUserId: string | null = null;

  const userMsgs = currentChatMessages.value.filter(m => m.role === 'user');

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

  if (!activeUserId && userMsgs.length > 0) {
    activeUserId = userMsgs[0].id;
  }

  if (activeUserId) {
    currentVisibleMessageId.value = activeUserId;
  }

  updateGalAvatarState();
};

const scrollToBottom = (force = false) => {
  if (isSwitchingBranch.value) return;
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

async function handleDuplicateUpTo(messageId: string) {
  if (!currentChatId.value) return;
  try {
    const newChat = await duplicateChat(currentChatId.value, { up_to_message_id: messageId });
    ElMessage.success(t('common.msg.duplicateSuccess'));

    const exists = chatListStore.chatList.some(c => c.id === newChat.id);
    if (!exists) {
      chatListStore.chatList.push(newChat);
    }
    await chatSessionStore.selectChat(newChat.id)
  } catch (error) {
    console.error('Failed to duplicate chat up to message:', error);
    ElMessage.error(t('common.error.operationFailed'));
  }
}


async function handleSwitchBranch(currentMessageId: string, targetMessageId: string) {
  if (isGenerating.value) return;

  isSwitchingBranch.value = true;
  const scrollbarWrap = scrollbarRef.value?.wrapRef;
  let relativeTop = 0;

  if (scrollbarWrap) {
    const currentElement = document.getElementById(`msg-${currentMessageId}`);
    if (currentElement) {
      const elementRect = currentElement.getBoundingClientRect();
      const containerRect = scrollbarWrap.getBoundingClientRect();
      relativeTop = elementRect.top - containerRect.top;
    }
  }

  try {
    await chatInteractionStore.activateBranch(targetMessageId);

    await nextTick();
    await new Promise(resolve => requestAnimationFrame(resolve));

    if (scrollbarWrap) {
      const targetElement = document.getElementById(`msg-${targetMessageId}`);
      if (targetElement) {
        const targetRect = targetElement.getBoundingClientRect();
        const containerRect = scrollbarWrap.getBoundingClientRect();
        const currentRelativeTop = targetRect.top - containerRect.top;

        const diff = currentRelativeTop - relativeTop;
        scrollbarWrap.scrollTop += diff;
      }
    }
  } finally {
    isSwitchingBranch.value = false;
  }
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
  galAvatarImageUrl.value = null;
  galIsScrolledPast.value = true;
  if (newId) {
    userHasScrolledUp.value = false;
    previousPreviewHeight.value = 0;
    currentVisibleMessageId.value = null;

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
            updateGalAvatarState();
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
.message-list-wrapper.gal-shifted {
  padding-left: 240px;
}
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

/* ========== Gal_Avatar 模式：左侧固定头像面板 ========== */
.gal-avatar-panel {
  position: relative;
  left: 8px;
  z-index: 15;
  height: 0;
}

.gal-avatar-image {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 210px;
  height: 285px;
  object-fit: cover;
  border-radius: 10px;
  border: 2px solid var(--el-border-color-light);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}

.gal-fade-enter-active,
.gal-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.gal-fade-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.gal-fade-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}

/* 相邻 Gal_Avatar 切换：淡入淡出同时进行 */
.gal-img-enter-active,
.gal-img-leave-active {
  transition: opacity 0.15s ease;
}
.gal-img-leave-active {
  position: absolute;
}
.gal-img-enter-from,
.gal-img-leave-to {
  opacity: 0;
}
</style>
