<template>
  <div v-if="minimizedSubMessages.length > 0" class="minimized-sub-messages-container" :class="{ 'is-user': isUser }">
    <el-tooltip
      v-for="subMessage in minimizedSubMessages"
      :key="subMessage.id"
      placement="top"
      :show-after="300"
    >
      <template #content>
        <div style="max-width: 300px; white-space: pre-wrap">
          {{ getMinimizedTooltipContent(subMessage) }}
        </div>
      </template>
      <div
        class="minimized-item"
        :class="{
          'is-inactive': isSubMessageInactive(subMessage),
          'has-review': hasReview(subMessage),
          'has-ask-user': subMessage.type === 'AskUser'
        }"
        @click="$emit('restore', subMessage.id)"
      >
        <template v-if="subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool' || subMessage.type === 'AskUser'">
          <el-icon>
            <Warning v-if="subMessage.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
            <QuestionFilled v-else-if="subMessage.type === 'AskUser'" style="color: var(--el-color-primary)" />
            <Loading
              v-else-if="getMinimizedMcpInfo(subMessage).status === 'generating'"
              class="is-loading"
            />
            <CircleCheck
              v-else-if="getMinimizedMcpInfo(subMessage).status === 'success'"
              style="color: var(--el-color-success)"
            />
            <CircleClose v-else style="color: var(--el-color-error)" />
          </el-icon>
          <span class="minimized-item-title">
            {{
              subMessage.type === 'ReviewTool'
              ? $t('chat.message.pendingReview')
              : subMessage.type === 'AskUser'
              ? $t('chat.askUser.pendingAnswer')
              : (hasReview(subMessage) ? $t('chat.message.toolCallReviewed') : $t('chat.message.toolCall'))
            }}
          </span>
        </template>
        <template v-else>
          <el-icon><Document /></el-icon>
          <span class="minimized-item-title">{{ getPartitionTitleForMinimized(subMessage) }}</span>
        </template>
      </div>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SubMessage, McpToolContent, ReviewToolContent, AskUserContent } from '@/api/types'
import { Warning, Loading, CircleCheck, CircleClose, Document, QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  displayableSubMessages: SubMessage[]
  currentMessageRank: number
  isGenerating: boolean
  isUser: boolean
}>()

const emit = defineEmits<{
  (e: 'restore', subMessageId: string): void
}>()

const { t } = useI18n()

function isSubMessageInactive(subMessage: SubMessage): boolean {
  if (props.isGenerating) return false
  const cpl = subMessage.config?.context_participation_length
  if (cpl === undefined || cpl === null) return false
  if (cpl === 0) return true
  if (cpl > 0) return props.currentMessageRank > cpl
  return false
}

const reviewedToolCallIds = computed(() => {
  const ids = new Set<string>()
  props.displayableSubMessages.forEach(sm => {
    if (sm.type === 'ReviewTool') {
      try {
        const content = JSON.parse(sm.content) as ReviewToolContent
        ids.add(content.tool_call_id)
      } catch {}
    }
  })
  return ids
})

function hasReview(subMessage: SubMessage): boolean {
  if (subMessage.type !== 'McpTool') return false
  try {
    const content = JSON.parse(subMessage.content) as McpToolContent
    return reviewedToolCallIds.value.has(content.tool_call_id)
  } catch { return false }
}

const minimizedSubMessages = computed(() => {
  const allSubMessages = props.displayableSubMessages
  const tools = allSubMessages.filter(sm => sm.type === 'McpTool' || sm.type === 'ReviewTool' || sm.type === 'AskUser')

  const mcpToolCallIds = new Set(
    tools.filter(sm => sm.type === 'McpTool')
         .map(sm => {
           try {
             const content = JSON.parse(sm.content) as McpToolContent
             return content.tool_call_id
           } catch { return null }
         })
         .filter(Boolean)
  )

  const deduplicatedTools = tools.filter(sm => {
    if (sm.type === 'ReviewTool') {
      try {
        const content = JSON.parse(sm.content) as ReviewToolContent
        if (content.decision) return false
        return !mcpToolCallIds.has(content.tool_call_id)
      } catch { return true }
    }
    if (sm.type === 'AskUser') {
      try {
        const content = JSON.parse(sm.content) as AskUserContent
        if (content.answers !== null && content.answers !== undefined) return false
        return !mcpToolCallIds.has(content.tool_call_id)
      } catch { return true }
    }
    return true
  })

  const normalMinimized = allSubMessages.filter(sm =>
    sm.config?.is_minimal === true && sm.type !== 'McpTool' && sm.type !== 'ReviewTool' && sm.type !== 'AskUser'
  )

  return [...normalMinimized, ...deduplicatedTools].sort((a, b) => a.sortOrder - b.sortOrder)
})

function getPartitionTitleForMinimized(subMessage: SubMessage): string {
  if (subMessage.type === 'Reasoning') return t('chat.message.reasoning')
  if (subMessage.type === 'File') return t('chat.message.file')
  if (subMessage.type === 'Normal') {
    const normalSubMessages = props.displayableSubMessages.filter((sm) => sm.type === 'Normal')
    if (normalSubMessages.length <= 1) return t('chat.message.content')
    const normalIndex = normalSubMessages.findIndex((sm) => sm.id === subMessage.id)
    if (normalIndex !== -1) {
      return `${t('chat.message.content')}(${normalIndex + 1})`
    }
  }
  return t('chat.message.partition')
}

function getMinimizedMcpInfo(subMessage: SubMessage) {
  if (subMessage.status === 'generating') return { status: 'generating' }
  try {
    const content = JSON.parse(subMessage.content)
    return { status: content.is_error ? 'error' : 'success' }
  } catch (e) {
    return { status: 'error' }
  }
}

function getMinimizedTooltipContent(subMessage: SubMessage): string {
  if (subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool') {
    try {
      const content = JSON.parse(subMessage.content)
      let argsStr = ''
      if (typeof content.arguments === 'string') {
        argsStr = content.arguments
      } else if (typeof content.arguments === 'object') {
        argsStr = JSON.stringify(content.arguments)
      }
      const args = argsStr ? `Args: ${argsStr}` : ''
      return `${t('chat.message.toolCall')}: ${content.name || t('common.status.unknown')}\n${args}`.trim()
    } catch {
      return t('chat.message.toolCall')
    }
  }
  return subMessage.content.substring(0, 100) + (subMessage.content.length > 100 ? '...' : '')
}
</script>

<style scoped>
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

.minimized-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  background-color: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
}
.minimized-item.is-inactive:hover {
  border-color: var(--el-text-color-placeholder);
  color: var(--el-text-color-regular);
}

.is-user.minimized-sub-messages-container {
  justify-content: flex-end;
}
.is-user .minimized-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}
.is-user .minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.is-user .minimized-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}
.is-user .minimized-item.is-inactive:hover {
  border-color: var(--el-color-primary-light-3);
  color: var(--el-color-primary-dark-2);
}

.minimized-item.has-review {
  border-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}
.minimized-item.has-review:hover {
  border-color: var(--el-color-warning-dark-2);
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
.is-user .minimized-item.has-review {
  border-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-8);
}

.minimized-item-title {
  white-space: nowrap;
}
</style>
