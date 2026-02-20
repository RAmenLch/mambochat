<!-- frontend/mambo/src/components/chat/MessageItem.vue -->
<template>
  <div
    :id="id"
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
      <!-- Minimized SubMessages Area -->
      <div v-if="minimizedSubMessages.length > 0" class="minimized-sub-messages-container">
        <el-tooltip
          v-for="subMessage in minimizedSubMessages"
          :key="subMessage.id"
          placement="top"
          :show-after="300"
        >
          <template #content>
            <div style="max-width: 300px; white-space: pre-wrap;">{{ getMinimizedTooltipContent(subMessage) }}</div>
          </template>
          <div class="minimized-item" @click="restoreSubMessage(subMessage.id)">
            <!-- MCP Tool Specific Minimized View -->
            <template v-if="subMessage.type === 'McpTool'">
              <el-icon>
                <Loading v-if="getMinimizedMcpInfo(subMessage).status === 'generating'" class="is-loading" />
                <CircleCheck v-else-if="getMinimizedMcpInfo(subMessage).status === 'success'" style="color: var(--el-color-success);" />
                <CircleClose v-else style="color: var(--el-color-error);" />
              </el-icon>
              <span class="minimized-item-title">{{ $t('chat.message.toolCall') }}</span>
            </template>
            <!-- Generic Minimized View -->
            <template v-else>
              <el-icon><Document /></el-icon>
              <span class="minimized-item-title">{{ getPartitionTitleForMinimized(subMessage) }}</span>
            </template>
          </div>
        </el-tooltip>
      </div>

      <div
        class="sub-messages-container"
        :class="{
          'is-single': useSinglePartitionView,
          'is-single-collapsed': useSinglePartitionView && isSingleViewCollapsed
        }"
      >
        <!-- Display a loading indicator when the message is generating but has no sub-messages yet -->
        <div v-if="message.status === 'generating' && normalSubMessages.length === 0" class="initial-loading-placeholder">
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
              :id="`sub-msg-${subMessage.id}`"
              :sub-message="subMessage"
              :parent-message="message"
              :index="index + 1"
              :is-minimize-disabled="isLastVisibleSubMessage"
              @edit="(payload) => handleEditRequest(subMessage, payload)"
              @copy="handleCopySingle(subMessage)"
            />
          </div>
          <!-- Render a single non-file sub-message -->
          <SubMessageItem
            v-else
            :key="group.sub_messages[0].id"
            :id="`sub-msg-${group.sub_messages[0].id}`"
            :sub-message="group.sub_messages[0]"
            :parent-message="message"
            :show-header="!useSinglePartitionView"
            :index="group.sub_messages[0].sortOrder + 1"
            :is-minimize-disabled="isLastVisibleSubMessage"
            @edit="(payload) => handleEditRequest(group.sub_messages[0], payload)"
            @copy="handleCopySingle(group.sub_messages[0])"
          />
        </template>
      </div>

      <!-- Zip History Bookmark and Card -->
      <div v-if="zipHistorySubMessage" class="zip-history-section">
        <div
          class="zip-history-bookmark"
          :class="zipBookmarkClass"
          @click="handleZipBookmarkClick"
        >
          <el-icon :class="{ 'is-loading': zipStatus === 'generating' }">
            <component :is="zipBookmarkIcon" />
          </el-icon>
          <span>{{ zipBookmarkText }}</span>
        </div>
        <ZipHistoryCard
          v-if="isZipCardVisible && zipStatus !== 'generating'"
          :sub-message="zipHistorySubMessage"
          class="zip-history-card"
        />
      </div>

      <!-- Suggestion Chips -->
      <div v-if="isLastMessage && suggestionList.length > 0" class="suggestion-chips">
        <el-tag
          v-for="(suggestion, idx) in suggestionList"
          :key="idx"
          class="suggestion-item"
          type="info"
          effect="plain"
          round
          @click="$emit('suggestion-click', suggestion)"
        >
          {{ suggestion }}
        </el-tag>
      </div>

      <div class="message-actions" :class="{ 'is-visible': showActions && message.status !== 'generating' }">
        <el-tooltip :content="$t('chat.message.regenerate')" placement="top" :show-after="500">
          <el-button :icon="message.role === 'user' ? RefreshLeft : Refresh" circle size="small" @click="handleRegenerate" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" :content="isSingleViewCollapsed ? $t('chat.message.expand') : $t('chat.message.collapse')" placement="top" :show-after="500">
          <el-button :icon="isSingleViewCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleSingleViewCollapse" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" :content="$t('common.action.edit')" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEditRequest(firstSubMessage, { content: firstSubMessage.content })" />
        </el-tooltip>

        <el-tooltip :content="isSingleSubMessage ? $t('common.action.copy') : $t('chat.message.copyAll')" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>

        <el-tooltip v-if="message.role === 'assistant'" :content="$t('chat.message.compressHistory')" placement="top" :show-after="500">
          <el-button :icon="Clock" circle size="small" @click="handleCompressHistory" />
        </el-tooltip>

        <el-tooltip :content="$t('common.action.delete')" placement="top" :show-after="500">
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
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :is-user-message="message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import type { Message, SubMessage, SubMessageCreate, MessageStatus, McpToolContent } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  User, Cpu, Refresh, RefreshLeft, Delete, Edit, CopyDocument,
  ArrowUpBold, ArrowDownBold, Clock, Document, Loading, CircleCheck, CircleClose
} from '@element-plus/icons-vue';
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

interface MinimizedMcpInfo {
  status: 'generating' | 'success' | 'error';
}

const props = defineProps<{
  id: string;
  message: Message;
  isLastMessage: boolean;
}>();

const emit = defineEmits<{
  (e: 'suggestion-click', text: string): void;
}>();

const { t } = useI18n();
const interactionStore = useChatInteractionStore();
const settingsStore = useSettingsStore();
const { globalSettings } = storeToRefs(settingsStore);

const showActions = ref(false);
const isZipCardVisible = ref(false);

/**
 * 过滤出所有用于在消息气泡中显示的子消息 (排除 'Usage', 'ZipHistory' 和 'Suggest' 类型)。
 */
const displayableSubMessages = computed(() =>
  props.message.sub_messages.filter(sm =>
    sm.type !== 'Usage' &&
    sm.type !== 'ZipHistory' &&
    sm.type !== 'Suggest'
  )
);

/**
 * 筛选出被最小化的子消息
 */
const minimizedSubMessages = computed(() =>
  displayableSubMessages.value.filter(sm => sm.config?.is_minimal === true)
);

/**
 * 筛选出正常显示的子消息 (排除最小化)
 */
const normalSubMessages = computed(() =>
  displayableSubMessages.value.filter(sm => !sm.config?.is_minimal)
);

/**
 * 判断当前是否只剩下一个可见的子消息
 */
const isLastVisibleSubMessage = computed(() => normalSubMessages.value.length === 1);

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

/**
 * 提取出 'Suggest' 类型的子消息，用于显示建议气泡。
 */
const suggestSubMessage = computed(() =>
  props.message.sub_messages.find(sm => sm.type === 'Suggest')
);

/**
 * 解析建议内容列表
 */
const suggestionList = computed((): string[] => {
  if (!suggestSubMessage.value || !suggestSubMessage.value.content) return [];
  try {
    const list = JSON.parse(suggestSubMessage.value.content);
    return Array.isArray(list) ? list : [];
  } catch (e) {
    return [];
  }
});

/**
 * 计算历史摘要的当前状态
 */
const zipStatus = computed(() => {
  if (!zipHistorySubMessage.value) return null;
  if (zipHistorySubMessage.value.status === 'generating') return 'generating';
  if (zipHistorySubMessage.value.config.zip_enable) return 'enabled';
  return 'disabled';
});

/**
 * 根据状态返回对应的图标组件
 */
const zipBookmarkIcon = computed(() => {
  switch (zipStatus.value) {
    case 'generating': return Loading;
    case 'enabled': return CircleCheck;
    case 'disabled': return Clock;
    default: return Clock;
  }
});

/**
 * 根据状态返回显示的文本
 */
const zipBookmarkText = computed(() => {
  switch (zipStatus.value) {
    case 'generating': return t('chat.message.zipGenerating');
    case 'enabled': return t('chat.message.zipHistory');
    case 'disabled': return t('chat.message.zipHistory');
    default: return t('chat.message.zipHistory');
  }
});

/**
 * 根据状态返回 CSS 类名
 */
const zipBookmarkClass = computed(() => ({
  'is-generating': zipStatus.value === 'generating',
  'is-enabled': zipStatus.value === 'enabled',
  'is-disabled': zipStatus.value === 'disabled',
}));

const isSingleSubMessage = computed(() => normalSubMessages.value.length === 1);
const firstSubMessage = computed(() => normalSubMessages.value[0]);

// Groups consecutive file sub-messages for grid layout, while keeping others separate.
const groupedSubMessages = computed((): SubMessageGroup[] => {
  if (!normalSubMessages.value || normalSubMessages.value.length === 0) {
    return [];
  }

  const result: SubMessageGroup[] = [];
  let lastGroup: SubMessageGroup | null = null;

  for (const subMessage of normalSubMessages.value) {
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
  return normalSubMessages.value.length === 1 && firstSubMessage.value?.type === 'Normal';
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

function getUpdatedFullContent(newPartialContent: string): string {
  if (!editingSubMessage.value) return '';

  const fullOriginalContent = editingSubMessage.value.content;
  const blockIndex = editingBlockIndex.value;

  // 1. 全量编辑（编辑普通消息）：直接返回新内容
  if (blockIndex === null || blockIndex === undefined) {
    return newPartialContent;
  }

  // 2. 局部编辑（代码块）：解析并定位
  const originalBlocks = parseMarkdown(fullOriginalContent);

  if (blockIndex >= originalBlocks.length) {
    console.warn('Block index out of bounds, falling back to full replacement');
    return fullOriginalContent;
  }

  const targetBlock = originalBlocks[blockIndex];

  if (targetBlock && targetBlock.type === 'code') {
    // 计算代码块的相对序号
    let targetCodeIdx = 0;
    for (let i = 0; i < blockIndex; i++) {
      if (originalBlocks[i].type === 'code') targetCodeIdx++;
    }

    /**
     * 正则优化说明：
     * Group 1 (p1): 前导字符
     * Group 2 (p2): 开始围栏 (``` 或 ~~~)
     * Group 3 (p3): 语言标识
     * Group 4 (p4): 围栏后的换行
     * Group 5 (p5): 内容
     * Group 6 (p6): **关键修改** -> (\n?) 尾部换行改为可选，以匹配空代码块 ` ```\n``` `
     * Group 7 (p7): 结束围栏
     */
    const fenceRegex = /(^|\n)(`{3,}|~{3,})([^\n]*)(\n)([\s\S]*?)(\n?)(\2)(?=\n|$)/g;

    let matchCount = 0;
    return fullOriginalContent.replace(fenceRegex, (match, p1, p2, p3, p4, p5, p6, p7) => {
      if (matchCount === targetCodeIdx) {
        matchCount++;
        // 重组内容：显式添加 \n (替代 p6)，确保结构总是规范的 (围栏+内容+换行+围栏)
        // 这样即使原代码块是空的 ` ```\n``` `，编辑后也会变成 ` ```\n新内容\n``` `
        return `${p1}${p2}${p3}${p4}${newPartialContent}\n${p7}`;
      }
      matchCount++;
      return match;
    });
  }

  return newPartialContent;
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
    await ElMessageBox.confirm(
      t('chat.message.deleteConfirm'),
      t('common.action.delete'),
      {
        confirmButtonText: t('common.action.delete'),
        cancelButtonText: t('common.action.cancel'),
        type: 'warning'
      }
    );
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
  // 使用 normalSubMessages 确保只复制非最小化状态的子消息
  const contentToCopy = normalSubMessages.value.map(sm => {
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

function handleZipBookmarkClick() {
  if (zipStatus.value === 'generating') return;
  isZipCardVisible.value = !isZipCardVisible.value;
}

/**
 * 恢复一个最小化的子消息
 */
function restoreSubMessage(subMessageId: string) {
  const subMessage = props.message.sub_messages.find(sm => sm.id === subMessageId);
  if (!subMessage) return;

  interactionStore.updateSubMessage({
    subMessageId: subMessageId,
    data: { config: { ...subMessage.config, is_minimal: false } },
  });
}

/**
 * 为最小化按钮获取一个简短的标题
 */
function getPartitionTitleForMinimized(subMessage: SubMessage): string {
  if (subMessage.type === 'Reasoning') return t('chat.message.reasoning');
  if (subMessage.type === 'File') return '文件';
  if (subMessage.type === 'Normal') {
      const normalSubMessages = displayableSubMessages.value.filter(sm => sm.type === 'Normal');
      if (normalSubMessages.length <= 1) return t('chat.message.content');
      const normalIndex = normalSubMessages.findIndex(sm => sm.id === subMessage.id);
      if (normalIndex !== -1) {
        return `${t('chat.message.content')}(${normalIndex + 1})`;
      }
  }
  return '分区';
}

/**
 * 解析最小化的 McpTool 子消息以获取其状态。
 */
function getMinimizedMcpInfo(subMessage: SubMessage): MinimizedMcpInfo {
  if (subMessage.status === 'generating') {
    return { status: 'generating' };
  }
  try {
    const content: McpToolContent = JSON.parse(subMessage.content);
    return {
      status: content.is_error ? 'error' : 'success',
    };
  } catch (e) {
    return { status: 'error' };
  }
}

/**
 * 为最小化的子消息生成工具提示内容。
 */
function getMinimizedTooltipContent(subMessage: SubMessage): string {
  if (subMessage.type === 'McpTool') {
      const content: McpToolContent = JSON.parse(subMessage.content);
      const args = content.arguments ? `Args: ${content.arguments}` : '';
      return `${t('chat.message.toolCall')}: ${content.name || 'Unknown'}\n${args}`.trim();
  }
  return subMessage.content.substring(0, 100) + (subMessage.content.length > 100 ? '...' : '');
}

</script>

<style scoped>
.message-item-container { display: flex; align-items: flex-start; margin-bottom: 20px; max-width: 90%; }
.message-avatar { flex-shrink: 0; margin-right: 12px; margin-top: 2px; }
.message-body { display: flex; flex-direction: column; min-width: 80px; }

.minimized-sub-messages-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.minimized-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.minimized-item .el-icon.is-loading {
  animation: rotating 2s linear infinite;
}
.minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.is-user .minimized-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}
.is-user .minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.minimized-item-title {
  white-space: nowrap;
}

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
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

/* Enabled State (Green) */
.zip-history-bookmark.is-enabled {
  background-color: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}
.zip-history-bookmark.is-enabled:hover {
  background-color: var(--el-color-success-light-8);
}

/* Disabled State (Gray/Info) */
.zip-history-bookmark.is-disabled {
  background-color: var(--el-color-info-light-9);
  border-color: var(--el-color-info-light-7);
  color: var(--el-color-info);
}
.zip-history-bookmark.is-disabled:hover {
  background-color: var(--el-color-info-light-8);
}

/* Generating State (Blue/Primary) */
.zip-history-bookmark.is-generating {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
  cursor: default;
}

/* Loading Icon Animation */
.zip-history-bookmark .el-icon.is-loading {
  animation: rotating 2s linear infinite;
}

.zip-history-card {
  margin-top: 8px;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.suggestion-item {
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  border-color: var(--el-border-color);
  background-color: var(--color-background);
}
.suggestion-item:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.message-actions { display: flex; gap: 4px; margin-top: 8px; opacity: 0; visibility: hidden; min-height: 24px; transition: opacity 0.2s, visibility 0.2s; align-items: center; }
.message-actions.is-visible { opacity: 1; visibility: visible; }
.message-item-container.is-user { flex-direction: row-reverse; margin-left: auto; }
.is-user .message-avatar { margin-right: 0; margin-left: 12px; }
.is-user .sub-messages-container { align-items: flex-end; }
.is-user .minimized-sub-messages-container { justify-content: flex-end; }
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
