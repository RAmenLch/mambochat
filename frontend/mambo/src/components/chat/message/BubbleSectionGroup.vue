<template>
  <div
    class="bubble-section-group"
    :class="{ 'is-inactive': isInactive, 'is-reasoning': isReasoning }"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="effectiveTextSubMessage">
      <!-- 悬浮操作栏 -->
      <div class="group-floating-actions" :class="{ 'is-visible': isHovered && !isGenerating }">
        <el-tooltip v-if="showEdit" :content="$t('common.action.edit')" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEdit" />
        </el-tooltip>
        <el-tooltip v-if="showCopy" :content="$t('common.action.copy')" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>
        <el-tooltip v-if="showCollapse" :content="isTextCollapsed ? $t('common.action.expand') : $t('common.action.collapse')" placement="top" :show-after="500">
          <el-button :icon="isTextCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleCollapse" />
        </el-tooltip>
      </div>

      <SubMessageItem
        :sub-message="effectiveTextSubMessage"
        :parent-message="parentMessage"
        :show-header="false"
        :is-inline="true"
        @edit="(payload) => $emit('edit', group.textSubMessage!, payload)"
        @copy="$emit('copy', group.textSubMessage!)"
      />
    </div>

    <!-- 工具调用小气泡 -->
    <div class="group-tools-wrapper" v-if="group.toolSubMessages.length > 0">
      <div
        v-for="tool in group.toolSubMessages"
        :key="tool.id"
        class="minimized-item"
        :class="{ 'has-review': tool.type === 'ReviewTool', 'has-ask-user': tool.type === 'AskUser' }"
        @click="$emit('open-tool-dialog', tool.id)"
      >
        <el-icon>
          <Warning v-if="tool.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
          <QuestionFilled v-else-if="tool.type === 'AskUser'" style="color: var(--el-color-primary)" />
          <Loading v-else-if="tool.status === 'generating'" class="is-loading" />
          <CircleClose v-else-if="isToolError(tool)" style="color: var(--el-color-error)" />
          <CircleCheck v-else style="color: var(--el-color-success)" />
        </el-icon>
        <span class="minimized-item-title">
          {{ getToolName(tool) }}
        </span>
      </div>
    </div>

    <!-- Zip History 覆盖指示器 -->
    <div v-if="showZipCoverage" class="zip-coverage-indicator">
      <el-tooltip :content="$t('chat.message.zipCoverageTip')" placement="top" :show-after="300">
        <div class="zip-coverage-arrow">
          <svg width="16" height="10" viewBox="0 0 16 10" fill="none">
            <path d="M8 1L14 9H2L8 1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
          </svg>
        </div>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { Message, SubMessage, McpToolContent, ReviewToolContent, AskUserContent } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import SubMessageItem from '../SubMessageItem.vue';
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Warning, Loading, CircleClose, CircleCheck, QuestionFilled } from '@element-plus/icons-vue';

const { t } = useI18n();

const props = withDefaults(defineProps<{
  group: BubbleSectionGroup;
  parentMessage: Message;
  isGenerating: boolean;
  isInactive: boolean;
  isReasoning?: boolean;
  showZipCoverage?: boolean;
  showEdit?: boolean;
  showCopy?: boolean;
  showCollapse?: boolean;
  externalCollapsed?: boolean;
}>(), {
  isReasoning: false,
  showZipCoverage: false,
  showEdit: true,
  showCopy: true,
  showCollapse: true,
});

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void;
  (e: 'copy', subMessage: SubMessage): void;
  (e: 'open-tool-dialog', subMessageId: string): void;
  (e: 'toggle-collapse', subMessageId: string): void;
}>();

const interactionStore = useChatInteractionStore();
const isHovered = ref(false);

/** 外部传入折叠状态时优先使用外部状态，否则从 store 中读取 */
const isTextCollapsed = computed(() => {
  if (props.externalCollapsed !== undefined) {
    return props.externalCollapsed;
  }
  return props.group.textSubMessage?.config?.is_collapsed || false;
});

/** 当外部控制折叠时，将折叠状态注入到 subMessage.config 中一并传给 SubMessageItem */
const effectiveTextSubMessage = computed(() => {
  if (!props.group.textSubMessage) return undefined;
  if (props.externalCollapsed !== undefined) {
    return {
      ...props.group.textSubMessage,
      config: {
        ...props.group.textSubMessage.config,
        is_collapsed: props.externalCollapsed,
      },
    };
  }
  return props.group.textSubMessage;
});

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
    if (props.externalCollapsed !== undefined) {
      emit('toggle-collapse', props.group.textSubMessage.id);
    } else {
      interactionStore.updateSubMessage({
        subMessageId: props.group.textSubMessage.id,
        data: { config: { ...props.group.textSubMessage.config, is_collapsed: !isTextCollapsed.value } }
      });
    }
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
  if (tool.type === 'AskUser') {
    return t('chat.askUser.toolName');
  }
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
.minimized-item.has-ask-user {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}
.minimized-item.has-ask-user:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.minimized-item-title {
  white-space: nowrap;
}

/* ========== Zip History 覆盖指示器 ========== */
.zip-coverage-indicator {
  display: flex;
  justify-content: flex-start;
  padding-top: 6px;
  margin-top: 4px;
  padding-left: 4px;
}

.zip-coverage-arrow {
  color: var(--el-color-success-light-3);
  cursor: help;
  transition: color 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.zip-coverage-arrow:hover {
  color: var(--el-color-success);
  transform: translateY(-1px);
}
</style>
