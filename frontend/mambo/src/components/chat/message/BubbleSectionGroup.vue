<!-- frontend/mambo/src/components/chat/message/BubbleSectionGroup.vue -->
<template>
  <div
    class="bubble-section-group"
    :class="{ 'is-inactive': isInactive }"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="group.textSubMessage">
      <!-- 悬浮操作栏 (已改为圆角矩形) -->
      <div class="group-floating-actions" :class="{ 'is-visible': isHovered && !isGenerating }">
        <el-tooltip :content="$t('common.action.edit', '编辑')" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEdit" />
        </el-tooltip>
        <el-tooltip :content="$t('common.action.copy', '复制')" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>
        <el-tooltip :content="isTextCollapsed ? $t('common.action.expand', '展开') : $t('common.action.collapse', '折叠')" placement="top" :show-after="500">
          <el-button :icon="isTextCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleCollapse" />
        </el-tooltip>
      </div>

      <SubMessageItem
        :sub-message="group.textSubMessage"
        :parent-message="parentMessage"
        :show-header="false"
        :is-inline="true"
        @edit="(payload) => $emit('edit', group.textSubMessage, payload)"
        @copy="$emit('copy', group.textSubMessage)"
      />
    </div>

    <!-- 工具调用小气泡 (完全回滚至原版 minimized-item 样式，仅外显名称) -->
    <div class="group-tools-wrapper" v-if="group.toolSubMessages.length > 0">
      <div
        v-for="tool in group.toolSubMessages"
        :key="tool.id"
        class="minimized-item"
        :class="{ 'has-review': tool.type === 'ReviewTool' }"
        @click="$emit('open-tool-dialog', tool.id)"
      >
        <el-icon>
          <Warning v-if="tool.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
          <Loading v-else-if="tool.status === 'generating'" class="is-loading" />
          <CircleClose v-else-if="isToolError(tool)" style="color: var(--el-color-error)" />
          <CircleCheck v-else style="color: var(--el-color-success)" />
        </el-icon>
        <span class="minimized-item-title">
          <!-- 仅外显工具名称 -->
          {{ getToolName(tool) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { Message, SubMessage, McpToolContent, ReviewToolContent } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import SubMessageItem from '../SubMessageItem.vue';
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Warning, Loading, CircleClose, CircleCheck } from '@element-plus/icons-vue';

const props = defineProps<{
  group: BubbleSectionGroup;
  parentMessage: Message;
  isGenerating: boolean;
  isInactive: boolean;
}>();

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void;
  (e: 'copy', subMessage: SubMessage): void;
  (e: 'open-tool-dialog', subMessageId: string): void;
}>();

const interactionStore = useChatInteractionStore();
const isHovered = ref(false);

const isTextCollapsed = computed(() => props.group.textSubMessage?.config?.is_collapsed || false);

function handleEdit() {
  if (props.group.textSubMessage) {
    emit('edit', props.group.textSubMessage, { content: props.group.textSubMessage.content });
  }
}

function handleCopy() {
  if (props.group.textSubMessage) {
    emit('copy', props.group.textSubMessage);
  }
}

function toggleCollapse() {
  if (props.group.textSubMessage) {
    interactionStore.updateSubMessage({
      subMessageId: props.group.textSubMessage.id,
      data: { config: { ...props.group.textSubMessage.config, is_collapsed: !isTextCollapsed.value } }
    });
  }
}

function getParsedContent(tool: SubMessage): McpToolContent | ReviewToolContent | null {
  try {
    return JSON.parse(tool.content);
  } catch {
    return null;
  }
}

function getToolName(tool: SubMessage): string {
  const content = getParsedContent(tool);
  return content?.name || 'Unknown Tool';
}

function isToolError(tool: SubMessage): boolean {
  if (tool.type !== 'McpTool') return false;
  const content = getParsedContent(tool) as McpToolContent | null;
  return content?.is_error || false;
}
</script>

<style scoped>
.bubble-section-group {
  position: relative;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  transition: opacity 0.3s;
}
.bubble-section-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.bubble-section-group.is-inactive {
  opacity: 0.6;
}

.group-text-wrapper {
  position: relative;
}

.group-floating-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: 4px;
  background-color: var(--color-background-soft);
  padding: 2px;
  border-radius: 6px; /* 已修正为圆角矩形 */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  z-index: 10;
}
.group-floating-actions.is-visible {
  opacity: 1;
  visibility: visible;
}

.group-tools-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding-left: 4px;
}

/* 完全复用原版 minimized-item 的样式 */
.minimized-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px; /* 原版就是圆角矩形 */
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.minimized-item .is-loading {
  animation: rotating 2s linear infinite;
}
.minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.minimized-item.has-review {
  border-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}
.minimized-item.has-review:hover {
  border-color: var(--el-color-warning-dark-2);
  color: var(--el-color-warning-dark-2);
}
.minimized-item-title {
  white-space: nowrap;
}
</style>
