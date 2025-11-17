<!-- frontend/mambo/src/components/chat/MessageItem.vue -->
<template>
  <div
    class="message-item-container"
    :class="roleClass"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <div class="message-avatar">
      <el-avatar :src="avatarUrl || ''">
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <div class="message-body">
      <div
        class="sub-messages-container"
        :class="{
          'is-single': useSinglePartitionView,
          'is-single-collapsed': useSinglePartitionView && isSingleViewCollapsed
        }"
      >
        <!-- Display a loading indicator when the message is generating but has no sub-messages yet -->
        <div v-if="message.status === 'generating' && displayableSubMessages.length === 0" class="initial-loading-placeholder">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>

        <template v-for="(group, groupIndex) in groupedSubMessages" :key="groupIndex">
          <!-- Render a group of files with a flex layout -->
          <div v-if="group.type === 'file'" class="file-group-container">
            <SubMessageItem
              v-for="(subMessage, index) in group.sub_messages"
              :key="subMessage.id"
              :sub-message="subMessage"
              :parent-message="message"
              :index="index + 1"
              @edit="(payload) => handleEditRequest(subMessage, payload)"
              @copy="handleCopySingle(subMessage)"
            />
          </div>
          <!-- Render a single non-file sub-message -->
          <SubMessageItem
            v-else
            :key="group.sub_messages[0].id"
            :sub-message="group.sub_messages[0]"
            :parent-message="message"
            :show-header="!useSinglePartitionView"
            :index="group.sub_messages[0].sortOrder + 1"
            @edit="(payload) => handleEditRequest(group.sub_messages[0], payload)"
            @copy="handleCopySingle(group.sub_messages[0])"
          />
        </template>
      </div>

      <!-- Zip History Bookmark and Card -->
      <div v-if="zipHistorySubMessage" class="zip-history-section">
        <div class="zip-history-bookmark" @click="isZipCardVisible = !isZipCardVisible">
          <el-icon><Clock /></el-icon>
          <span>历史摘要</span>
        </div>
        <ZipHistoryCard
          v-if="isZipCardVisible"
          :sub-message="zipHistorySubMessage"
          class="zip-history-card"
        />
      </div>

      <div class="message-actions" :class="{ 'is-visible': showActions && message.status !== 'generating' }">
        <el-tooltip :content="message.role === 'user' ? '在下方重新回答' : '重新回答'" placement="top" :show-after="500">
          <el-button :icon="message.role === 'user' ? RefreshLeft : Refresh" circle size="small" @click="handleRegenerate" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" :content="isSingleViewCollapsed ? '展开' : '折叠'" placement="top" :show-after="500">
          <el-button :icon="isSingleViewCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleSingleViewCollapse" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" content="编辑" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEditRequest(firstSubMessage, { content: firstSubMessage.content })" />
        </el-tooltip>

        <el-tooltip :content="isSingleSubMessage ? '复制' : '全部复制'" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>

        <el-tooltip v-if="message.role === 'assistant'" content="压缩以上历史" placement="top" :show-after="500">
          <el-button :icon="Clock" circle size="small" @click="handleCompressHistory" />
        </el-tooltip>

        <el-tooltip content="删除" placement="top" :show-after="500">
          <el-button :icon="Delete" circle size="small" type="danger" plain @click="handleDelete" />
        </el-tooltip>

        <UsageInfo
          v-if="usageSubMessage"
          :usage-sub-message="usageSubMessage"
          class="usage-info-component"
        />
      </div>
    </div>
  </div>

  <MessageEditDialog
    v-show="editDialogVisible"
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :is-user-message="message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import type { Message, SubMessage, SubMessageCreate, MessageStatus } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, Cpu, Refresh, RefreshLeft, Delete, Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Clock } from '@element-plus/icons-vue';
import SubMessageItem from './SubMessageItem.vue';
import MessageEditDialog from './dialogs/MessageEditDialog.vue';
import UsageInfo from './UsageInfo.vue';
import ZipHistoryCard from './ZipHistoryCard.vue';
import { copyToClipboard } from '@/utils/clipboard';
import { parseMarkdown } from '@/utils/markdownParser';

interface SubMessageGroup {
  type: 'file' | 'normal';
  sub_messages: SubMessage[];
}

const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
}>();

const interactionStore = useChatInteractionStore();
const settingsStore = useSettingsStore();
const { globalSettings } = storeToRefs(settingsStore);

const showActions = ref(false);
const isZipCardVisible = ref(false);

/**
 * 过滤出所有用于在消息气泡中显示的子消息 (排除 'Usage' 和 'ZipHistory' 类型)。
 */
const displayableSubMessages = computed(() =>
  props.message.sub_messages.filter(sm => sm.type !== 'Usage' && sm.type !== 'ZipHistory')
);

/**
 * 提取出 'Usage' 类型的子消息，用于在工具栏中显示。
 */
const usageSubMessage = computed(() =>
  props.message.sub_messages.find(sm => sm.type === 'Usage')
);

/**
 * 提取出 'ZipHistory' 类型的子消息，用于显示历史摘要卡片。
 */
const zipHistorySubMessage = computed(() =>
  props.message.sub_messages.find(sm => sm.type === 'ZipHistory')
);

const isSingleSubMessage = computed(() => displayableSubMessages.value.length === 1);
const firstSubMessage = computed(() => displayableSubMessages.value[0]);

// Groups consecutive file sub-messages for grid layout, while keeping others separate.
const groupedSubMessages = computed((): SubMessageGroup[] => {
  if (!displayableSubMessages.value || displayableSubMessages.value.length === 0) {
    return [];
  }

  const result: SubMessageGroup[] = [];
  let lastGroup: SubMessageGroup | null = null;

  for (const subMessage of displayableSubMessages.value) {
    if (subMessage.type === 'File') {
      if (lastGroup && lastGroup.type === 'file') {
        lastGroup.sub_messages.push(subMessage);
      } else {
        const newGroup: SubMessageGroup = { type: 'file', sub_messages: [subMessage] };
        result.push(newGroup);
        lastGroup = newGroup;
      }
    } else {
      const newGroup: SubMessageGroup = { type: 'normal', sub_messages: [subMessage] };
      result.push(newGroup);
      lastGroup = newGroup;
    }
  }
  return result;
});

// 决定是否使用简化的单分区视图（无头部，有特殊背景和折叠效果）
const useSinglePartitionView = computed(() => {
  return displayableSubMessages.value.length === 1 && firstSubMessage.value?.type === 'Normal';
});

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));

const avatarUrl = computed(() => {
  if (props.message.role === 'user') {
    return globalSettings.value.user_avatar_url;
  }
  if (props.message.role === 'assistant') {
    return globalSettings.value.ai_avatar_url;
  }
  return null;
});

const isSingleViewCollapsed = ref(firstSubMessage.value?.config?.is_collapsed || false);
watch(() => firstSubMessage.value?.config?.is_collapsed, (newValue) => {
  isSingleViewCollapsed.value = newValue || false;
});

function toggleSingleViewCollapse() {
  if (!firstSubMessage.value) return;
  const newCollapsedState = !isSingleViewCollapsed.value;
  isSingleViewCollapsed.value = newCollapsedState;
  interactionStore.updateSubMessage({
    subMessageId: firstSubMessage.value.id,
    data: { config: { ...firstSubMessage.value.config, is_collapsed: newCollapsedState } },
  });
}

const editDialogVisible = ref(false);
const editingSubMessage = ref<SubMessage | null>(null);
const originalEditingContent = ref('');
const editingBlockIndex = ref<number | null>(null);

watch(editDialogVisible, (newValue) => {
  if (!newValue) {
    editingSubMessage.value = null;
    originalEditingContent.value = '';
    editingBlockIndex.value = null;
  }
});

function handleEditRequest(subMessage: SubMessage, payload: { content: string; blockIndex?: number }) {
  if (!subMessage || !payload) {
    console.error("handleEditRequest called with invalid arguments", { subMessage, payload });
    return;
  }

  editingSubMessage.value = subMessage;
  originalEditingContent.value = payload.content;
  editingBlockIndex.value = payload.blockIndex ?? null;
  editDialogVisible.value = true;
}

function replaceNthOccurrence(str: string, find: string, replace: string, n: number): string {
  let i = -1;
  while (n-- > 0) {
    i = str.indexOf(find, i + 1);
    if (i < 0) return str;
  }
  return str.substring(0, i) + replace + str.substring(i + find.length);
}

function getUpdatedFullContent(newPartialContent: string): string {
  if (!editingSubMessage.value) return '';

  const fullOriginalContent = editingSubMessage.value.content;
  const partialOriginalContent = originalEditingContent.value;
  const blockIndex = editingBlockIndex.value;

  if (blockIndex === null || partialOriginalContent === fullOriginalContent) {
    return newPartialContent;
  }

  const originalBlocks = parseMarkdown(fullOriginalContent);
  let occurrence = 0;
  if (blockIndex < originalBlocks.length && originalBlocks[blockIndex].content === partialOriginalContent) {
    for (let i = 0; i < blockIndex; i++) {
      if (originalBlocks[i].content === partialOriginalContent) {
        occurrence++;
      }
    }
  } else {
    // Fallback if blockIndex doesn't match or partialOriginalContent isn't found in blocks
    return fullOriginalContent.replace(partialOriginalContent, newPartialContent);
  }

  return replaceNthOccurrence(fullOriginalContent, partialOriginalContent, newPartialContent, occurrence + 1);
}

function handleSaveEdit(newContent: string) {
  if (!editingSubMessage.value) return;
  const updatedContent = getUpdatedFullContent(newContent);
  interactionStore.updateSubMessage({
    subMessageId: editingSubMessage.value.id,
    data: { content: updatedContent },
  });
}

function handleSaveAndResend(newContent: string) {
  if (!editingSubMessage.value) return;

  const updatedContent = getUpdatedFullContent(newContent);

  const newSubMessages: SubMessageCreate[] = props.message.sub_messages.map(sm => {
    // Note: We resend ALL sub-messages, including the unmodified original Usage sub-message if it exists.
    // The edit only applies to a displayable sub-message.
    return {
      content: sm.id === editingSubMessage.value!.id ? updatedContent : sm.content,
      sortOrder: sm.sortOrder,
      type: sm.type,
      config: sm.config,
      status: 'completed' as MessageStatus,
    };
  });

  interactionStore.editMessageAndRegenerate({
    messageId: props.message.id,
    sub_messages: newSubMessages,
    resend: true,
  });
}

function handleRegenerate() {
  interactionStore.regenerateFrom(props.message.id);
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除这条消息吗？（包含所有分区）', '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    });
    await interactionStore.deleteMessage(props.message.id);
  } catch { /* User canceled */ }
}

async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content);
    ElMessage.success('已复制到剪贴板');
  } catch { ElMessage.error('复制失败'); }
}

async function handleCopy() {
  const contentToCopy = displayableSubMessages.value.map(sm => {
    // For file types, we might want to copy a link or filename instead of just the ID.
    // For now, we'll stick to the content, which is the file ID.
    return sm.content;
  }).join('\n--------------------------\n');

  try {
    await copyToClipboard(contentToCopy);
    ElMessage.success('已复制到剪贴板');
  } catch { ElMessage.error('复制失败'); }
}

function handleCompressHistory() {
  interactionStore.initiateHistoryCompression(props.message.id);
  ElMessage.info('已开始在后台压缩历史对话，您可以继续聊天。');
}
</script>

<style scoped>
.message-item-container { display: flex; align-items: flex-start; margin-bottom: 20px; max-width: 90%; }
.message-avatar { flex-shrink: 0; margin-right: 12px; margin-top: 2px; }
.message-body { display: flex; flex-direction: column; min-width: 80px; width: 100%; }

.sub-messages-container {
  display: flex;
  flex-direction: column;
  gap: 8px; /* Spacing between groups */
  width: 100%;
  position: relative;
  transition: max-height 0.25s ease-out;
  overflow: hidden;
}

.file-group-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px; /* Spacing between files in a group */
}

.sub-messages-container.is-single {
  gap: 0;
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  min-height: 40px;
}
.is-user .sub-messages-container.is-single {
  background-color: var(--el-color-primary-light-9);
}

.sub-messages-container.is-single :deep(.sub-message-item) {
  border: none;
  background-color: transparent;
  overflow: visible;
}
.sub-messages-container.is-single :deep(.message-content) {
  padding: 0;
  max-height: none;
}
.sub-messages-container.is-single :deep(.message-content)::after {
  display: none;
}

.sub-messages-container.is-single-collapsed {
  max-height: 5em;
}
.sub-messages-container.is-single-collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(to bottom, transparent, var(--color-background-soft));
  pointer-events: none;
}
.is-user .sub-messages-container.is-single-collapsed::after {
  background: linear-gradient(to bottom, transparent, var(--el-color-primary-light-9));
}

.zip-history-section {
  margin-top: 8px;
}
.zip-history-bookmark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--el-color-info-light-9);
  border: 1px solid var(--el-color-info-light-7);
  color: var(--el-color-info-dark-2);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.2s;
}
.zip-history-bookmark:hover {
  background-color: var(--el-color-info-light-8);
}
.zip-history-card {
  margin-top: 8px;
}

.message-actions { display: flex; gap: 4px; margin-top: 8px; opacity: 0; visibility: hidden; min-height: 24px; transition: opacity 0.2s, visibility 0.2s; align-items: center; }
.message-actions.is-visible { opacity: 1; visibility: visible; }
.message-item-container.is-user { flex-direction: row-reverse; margin-left: auto; }
.is-user .message-avatar { margin-right: 0; margin-left: 12px; }
.is-user .sub-messages-container { align-items: flex-end; }
.is-user .file-group-container { justify-content: flex-end; }
.is-user .message-actions { justify-content: flex-end; }

.usage-info-component {
  margin-left: 8px;
}

.initial-loading-placeholder {
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
}

.typing-indicator { display: flex; align-items: center; justify-content: flex-start; height: 24px; }
.typing-indicator span { height: 8px; width: 8px; border-radius: 50%; background-color: #909399; margin: 0 3px; animation: bounce 1.4s infinite ease-in-out both; }
.typing-indicator span:nth-of-type(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-of-type(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
</style>
