<!-- frontend/mambo/src/components/chat/ChatWindow.vue -->
<template>
  <div class="chat-window-container">
    <input type="file" ref="fileInputRef" @change="onFileSelected" multiple style="display: none;" />

    <div v-if="!currentChat" class="welcome-view">
      <el-empty :description="$t('chat.window.welcome')" />
    </div>

    <template v-else>
      <!-- 仅在非折叠模式下显示 Header，折叠模式下 Header 显示在 ChatList 中 -->
      <ChatHeader
        v-if="!isSidebarCollapsed"
        :current-chat="currentChat"
        :is-title-refreshing="isTitleRefreshing"
        :messages="currentChatMessages"
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
            @suggestion-click="handleSuggestionClick"
          />
        </div>
      </el-scrollbar>

      <div
        class="input-container-wrapper"
        :style="{ height: `${inputAreaHeight}px` }"
        @dragenter.prevent.stop="handleContainerDragEnter"
        @dragover.prevent.stop="handleContainerDragOver"
        @drop.prevent.stop="handleContainerDrop"
      >
        <!-- 拖拽文件时的覆盖层 -->
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
          @open-settings="settingsDrawerVisible = true"
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
      source="toolbar"
      @mount-resources="handleMountResources"
      @append-resources="handleAppendResources"
      @mount-knowledge-base="handleMountKnowledgeBase"
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
import type { ChatUpdate, SubMessageCreate, AIModel, Resource } from '@/api/types';
import { uploadFile } from '@/api/chatService';

// --- Stores & Composables ---
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useResourceStore } from '@/stores/resourceStore';
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

const { t } = useI18n();

// --- Store Instances ---
const chatListStore = useChatListStore();
const chatSessionStore = useChatSessionStore();
const chatInteractionStore = useChatInteractionStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const resourceStore = useResourceStore();

// --- State from Stores ---
const { refreshingTitleChatId } = storeToRefs(chatListStore);
const { currentChat, currentChatId, currentChatMessages, isChatHistoryLoading, isGenerating, contextForTokenEstimation, searchTargetSubMessageId } = storeToRefs(chatSessionStore);
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]>};
const { resources: allResources } = storeToRefs(resourceStore);

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

/**
 * 提取当前启用的知识库ID
 * 逻辑：解析 modelParameters.enabled_mcp_ids['system-knowledge-base']['MAMBOCHAT_RESOURCE_ID']
 */
const activeKnowledgeBaseId = computed(() => {
  const params = currentChat.value?.modelParameters;
  if (!params?.enabled_mcp_ids) return null;

  // 仅支持新的字典结构
  if (!Array.isArray(params.enabled_mcp_ids) && typeof params.enabled_mcp_ids === 'object') {
    const kbConfig = params.enabled_mcp_ids['system-knowledge-base'];
    return kbConfig?.['MAMBOCHAT_RESOURCE_ID'] || null;
  }
  return null;
});

/**
 * 获取当前挂载的知识库资源对象列表 (用于 AttachmentPreview)
 */
const attachedKnowledgeBases = computed(() => {
  const id = activeKnowledgeBaseId.value;
  if (!id) return [];

  const resource = allResources.value.find(r => r.id === id);
  if (resource) {
    return [resource];
  }

  // 如果 Store 中没有找到（可能未加载详情），返回一个占位对象
  // 注意：这里使用类型断言构造一个最小化的 Resource 对象
  return [{
    id,
    name: '加载中...',
    description: '正在获取知识库详情',
    itemType: 'resource',
    resourceType: 'knowledge_base',
    parentId: null,
    sortOrder: 0,
    createdAt: '',
    updatedAt: '',
    latest_version: null,
    kb_id: null,
    kb_config: null
  } as Resource];
});

// --- Watchers for Knowledge Base ---
watch(activeKnowledgeBaseId, (newId) => {
  if (newId) {
    // 如果有ID但本地没有详情，尝试获取
    const exists = allResources.value.some(r => r.id === newId);
    if (!exists) {
      resourceStore.fetchResourceDetails(newId);
    }
  }
}, { immediate: true });

// --- Methods ---

/**
 * 辅助函数：将 enabled_mcp_ids 统一标准化为字典格式
 * 兼容旧的数组格式，转换为 Key-Value 结构 (Value 为空对象)
 */
function normalizeMcpIds(currentIds: any): Record<string, any> {
  if (!currentIds) return {};
  if (Array.isArray(currentIds)) {
    return currentIds.reduce((acc, id) => {
      acc[id] = {};
      return acc;
    }, {} as Record<string, any>);
  }
  if (typeof currentIds === 'object') {
    return { ...currentIds };
  }
  return {};
}

/**
 * 处理资源挂载操作 (Toolbar 场景)
 * 支持: submessage_template, file
 */
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
        ElMessage.warning(`资源 "${resource.name}" 文件信息为空，已跳过`);
      }
    }
  }

  if (hasFileAdded) {
    ElMessage.success('已从资源库添加文件');
  }
}

/**
 * 处理资源追加操作 (Toolbar 场景)
 * 支持: system_prompt, submessage_template, knowledge_base_chunk
 */
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

/**
 * 处理知识库挂载操作
 * 将知识库ID写入 enabled_mcp_ids 的 system-knowledge-base 配置中
 */
async function handleMountKnowledgeBase(resource: Resource) {
  if (!currentChat.value) return;

  const currentParams = currentChat.value.modelParameters || {};
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids);

  // 设置知识库配置
  mcpIds['system-knowledge-base'] = {
    MAMBOCHAT_RESOURCE_ID: resource.id
  };

  const updatedSettings: ChatUpdate = {
    modelParameters: {
      ...currentParams,
      enabled_mcp_ids: mcpIds,
    },
  };

  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings);
  ElMessage.success(`已启用知识库: ${resource.name}`);
}

/**
 * 处理知识库移除操作
 */
async function handleRemoveKnowledgeBase(resourceId: string) {
  if (!currentChat.value) return;

  const currentParams = currentChat.value.modelParameters || {};
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids);

  // 移除配置
  if (mcpIds['system-knowledge-base']) {
    delete mcpIds['system-knowledge-base'];

    const updatedSettings: ChatUpdate = {
      modelParameters: {
        ...currentParams,
        enabled_mcp_ids: mcpIds,
      },
    };

    await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings);
    ElMessage.success('已停用知识库检索');
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

function handleContainerDragEnter(event: DragEvent) {
  // 仅当拖拽内容包含文件时才显示上传遮罩，避免与内部 Tag 拖拽冲突
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
  ElMessage.success(t('chat.settings.saveSuccess'));
}

/**
 * 处理联网搜索工具的启用/停用切换。
 * 目标 ID: system-ddgs-search
 */
async function handleToggleWebSearch() {
  if (!currentChat.value) return;

  const SEARCH_TOOL_ID = 'system-ddgs-search';
  const currentParams = currentChat.value.modelParameters || {};
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids);

  if (mcpIds[SEARCH_TOOL_ID]) {
    delete mcpIds[SEARCH_TOOL_ID];
  } else {
    mcpIds[SEARCH_TOOL_ID] = {};
  }

  const updatedSettings: ChatUpdate = {
    modelParameters: {
      ...currentParams,
      enabled_mcp_ids: mcpIds,
    },
  };

  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings);
  ElMessage.success(`联网搜索已${mcpIds[SEARCH_TOOL_ID] ? '启用' : '禁用'}`);
}

/**
 * 处理通用 MCP 工具的启用/停用切换。
 */
async function handleToggleMcpTool(mcpId: string) {
  if (!currentChat.value) return;

  const currentParams = currentChat.value.modelParameters || {};
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids);

  if (mcpIds[mcpId]) {
    delete mcpIds[mcpId];
  } else {
    mcpIds[mcpId] = {};
  }

  const updatedSettings: ChatUpdate = {
    modelParameters: {
      ...currentParams,
      enabled_mcp_ids: mcpIds,
    },
  };

  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings);
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

// --- Watchers ---

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
