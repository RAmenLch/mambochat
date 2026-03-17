<template>
  <div
    class="bubble-section-group"
    :class="{ 'is-inactive': isInactive, 'is-reasoning': isReasoning }"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="group.textSubMessage">
      <!-- 悬浮操作栏 -->
      <div class="group-floating-actions" :class="{ 'is-visible': isHovered && !isGenerating }">
        <el-tooltip :content="$t('common.action.edit')" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEdit" />
        </el-tooltip>
        <el-tooltip :content="$t('common.action.copy')" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>
        <el-tooltip :content="isTextCollapsed ? $t('common.action.expand') : $t('common.action.collapse')" placement="top" :show-after="500">
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

    <!-- 工具调用小气泡 -->
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
          {{ getToolName(tool) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { Message, SubMessage, McpToolContent, ReviewToolContent } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import SubMessageItem from '../SubMessageItem.vue';
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Warning, Loading, CircleClose, CircleCheck } from '@element-plus/icons-vue';

const { t } = useI18n();

const props = withDefaults(defineProps<{
  group: BubbleSectionGroup;
  parentMessage: Message;
  isGenerating: boolean;
  isInactive: boolean;
  isReasoning?: boolean;
}>(), {
  isReasoning: false,
});

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
  return content?.name || t('chat.message.mcp.unknownTool');
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
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  transition: opacity 0.3s;
}
.bubble-section-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.bubble-section-group.is-inactive {
  opacity: 1;
  padding-left: 8px;
}

/* 思考区域内的分隔线 */
.bubble-section-group.is-reasoning {
  border-bottom-color: var(--el-border-color-extra-light);
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
  background-color: var(--el-bg-color);
  padding: 2px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
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

/* 【关键修改】工具小气泡设为较浅的灰色 */
.minimized-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--el-fill-color-light); /* 较浅的灰色 */
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
  background-color: var(--el-fill-color); /* hover 时稍深 */
}
.minimized-item.has-review {
  border-color: var(--el-color-warning-light-3);
  background-color: var(--el-color-warning-light-9);
}
.minimized-item.has-review:hover {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning-dark-2);
}

.minimized-item-title {
  white-space: nowrap;
}
</style>
