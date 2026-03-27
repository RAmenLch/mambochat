<!-- frontend/mambo/src/mobile/components/chat/message/MobileBubbleSectionGroup.vue -->
<template>
  <div
    class="mobile-bubble-section-group"
    :class="{ 'is-inactive': isInactive, 'is-reasoning': isReasoning }"
    @click.stop="$emit('toggle-actions', group.textSubMessage?.id || group.id)"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="group.textSubMessage">
      <SubMessageItem
        :sub-message="group.textSubMessage"
        :parent-message="parentMessage"
        :show-header="false"
        :is-inline="true"
        @edit="(payload) => $emit('edit', group.textSubMessage!, payload)"
        @copy="$emit('copy', group.textSubMessage)"
      />
    </div>

    <!-- 工具调用内联标签区域 -->
    <div class="group-tools-wrapper" v-if="group.toolSubMessages.length > 0">
      <div
        v-for="tool in group.toolSubMessages"
        :key="tool.id"
        class="tool-chip"
        :class="{ 'has-review': tool.type === 'ReviewTool' }"
        @click.stop="$emit('open-tool-dialog', tool.id)"
      >
        <el-icon>
          <Warning v-if="tool.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
          <Loading v-else-if="tool.status === 'generating'" class="is-loading" />
          <CircleClose v-else-if="isToolError(tool)" style="color: var(--el-color-error)" />
          <CircleCheck v-else style="color: var(--el-color-success)" />
        </el-icon>
        <span class="tool-chip-title">
          {{ getToolName(tool) }}
        </span>
      </div>
    </div>

    <!-- 操作菜单插槽 (跟随当前 Group 浮现) -->
    <div class="group-actions-container" v-if="$slots.actions">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { Message, SubMessage, McpToolContent, ReviewToolContent } from '@/api/types'
import SubMessageItem from '../SubMessageItem.vue'
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline'
import { Warning, Loading, CircleClose, CircleCheck } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  group: BubbleSectionGroup
  parentMessage: Message
  isGenerating: boolean
  isInactive: boolean
  isReasoning?: boolean
}>(), {
  isReasoning: false,
})

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void
  (e: 'copy', subMessage: SubMessage): void
  (e: 'open-tool-dialog', subMessageId: string): void
  (e: 'toggle-actions', subMessageId: string): void
}>()

function getParsedContent(tool: SubMessage): McpToolContent | ReviewToolContent | null {
  try {
    return JSON.parse(tool.content)
  } catch {
    return null
  }
}

function getToolName(tool: SubMessage): string {
  const content = getParsedContent(tool)
  return content?.name || t('chat.message.mcp.unknownTool')
}

function isToolError(tool: SubMessage): boolean {
  if (tool.type !== 'McpTool') return false
  const content = getParsedContent(tool) as McpToolContent | null
  return content?.is_error || false
}
</script>

<style scoped>
.mobile-bubble-section-group {
  position: relative;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.mobile-bubble-section-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.mobile-bubble-section-group.is-inactive {
  opacity: 0.7;
}

.mobile-bubble-section-group.is-reasoning {
  border-bottom-color: var(--el-border-color-lighter);
}

.group-text-wrapper {
  position: relative;
}

.group-tools-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.tool-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 12px;
  cursor: pointer;
}

.tool-chip .is-loading {
  animation: rotating 2s linear infinite;
}

.tool-chip.has-review {
  border-color: var(--el-color-warning-light-3);
  background-color: var(--el-color-warning-light-9);
}

.tool-chip-title {
  white-space: nowrap;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-actions-container {
  margin-top: 4px;
  align-self: flex-end; /* 菜单靠右对齐 */
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
