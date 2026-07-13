<!-- frontend/mambo/src/mobile/components/chat/SubMessageItem.vue -->
<template>
  <div
    :id="id"
    ref="rootRef"
    class="sub-message-item"
    :class="{
      'is-user': parentMessage.role === 'user',
      'is-file': subMessage.type === 'File',
      'is-inactive': isInactive,
      'is-inline': isInline,
      'is-review-pending': subMessage.type === 'ReviewTool' && !isReviewDecided
    }"
  >
    <!-- 文件类型消息 -->
    <div v-if="subMessage.type === 'File' && subMessage.file_info" class="file-display-container">
      <el-image
        v-if="subMessage.file_info.mime_type.startsWith('image/')"
        :src="subMessage.file_info.url"
        fit="contain"
        class="file-image-thumbnail"
      />
      <div v-else class="file-card">
        <div class="file-card-icon">
          <el-icon :size="24"><component :is="fileIcon" /></el-icon>
        </div>
        <div class="file-card-info">
          <div class="file-card-name">{{ subMessage.file_info.filename }}</div>
          <div class="file-card-size">{{ formattedFileSize }}</div>
        </div>
        <a :href="subMessage.file_info.url" download class="file-card-download">
          <el-icon><Download /></el-icon>
        </a>
      </div>
    </div>

    <div v-else-if="isPendingFile" class="file-pending-container">
      <div class="file-pending-card">
        <div class="file-pending-icon">
          <el-icon :size="22" class="is-loading"><Loading /></el-icon>
        </div>
        <div class="file-pending-info">
          <div class="file-pending-name">{{ pendingFileName }}</div>
          <div class="file-pending-status">{{ pendingStatusText }}</div>
        </div>
      </div>
    </div>

    <!-- MCP 工具 / Review 工具 或 普通文本 -->
    <template v-else>
      <div v-if="showHeader || isToolType" class="sub-message-header">
        <span class="partition-title">{{ partitionTitle }}</span>

        <div class="actions">
          <template v-if="!isToolType && !isGenerating">
            <el-icon class="action-icon" @click="handleHeaderEditClick"><Edit /></el-icon>
            <el-icon class="action-icon" @click="emit('copy')"><CopyDocument /></el-icon>
          </template>

          <el-icon class="action-icon" @click="toggleMinimize" v-if="!isGenerating"
            ><Minus
          /></el-icon>

          <el-icon class="action-icon" @click="toggleCollapse">
            <component :is="isCollapsed ? ArrowDownBold : ArrowUpBold" />
          </el-icon>
        </div>
      </div>

      <div
        class="message-content"
        :class="{ collapsed: isCollapsed, 'mcp-tool-content': isToolType }"
        ref="contentRef"
      >
        <!-- 工具内容渲染 -->
        <div v-if="isToolType" class="mcp-tool-body">
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon v-if="subMessage.type === 'ReviewTool' && !isReviewDecided" color="var(--el-color-warning)"><Warning /></el-icon>
              <el-icon v-else-if="isGenerating" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="mcpToolContent && mcpToolContent.is_error" color="var(--el-color-error)"><CircleClose /></el-icon>
              <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
            </div>
            <span :class="{'text-warning': subMessage.type === 'ReviewTool' && !isReviewDecided}">{{ toolSummaryText }}</span>
          </div>
            <div
              v-if="!isGenerating && mcpToolContent?.result && !mcpToolContent.is_error && subMessage.type === 'McpTool'"
              class="mcp-tool-result"
            >
              {{ mcpToolContent.result }}
          </div>
        </div>

        <!-- 普通文本渲染 -->
        <template v-else>
          <div v-if="isGenerating && subMessage.content === ''" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <template v-else>
            <div v-for="(block, idx) in contentBlocks" :key="idx" class="content-block">
              <CodeBlock
                v-if="block.type === 'code'"
                :code="block.content"
                :language="block.language || 'Text'"
                :is-generating="isGenerating"
                :range="block.range"
                :markup="block.markup"
                :closed="block.closed !== false"
                @edit="handleCodeBlockEdit"
                @copy="handleBlockCopy"
              />
              <img
                v-else-if="block.type === 'base64_image'"
                :src="block.content"
                :alt="block.alt"
                class="rendered-image"
              />
              <div v-else v-html="block.content"></div>
            </div>
          </template>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SubMessage, Message, McpToolContent, ReviewToolContent, FileResponse } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { subscribeToPendingFile } from '@/services/sseService'
import { ElMessage } from 'element-plus'
import {
  Edit,
  CopyDocument,
  ArrowUpBold,
  ArrowDownBold,
  Download,
  Minus,
  Loading,
  CircleClose,
  CircleCheck,
  Document,
  Warning
} from '@element-plus/icons-vue'
import CodeBlock from '@/components/chat/CodeBlock.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { parseMarkdown, type ParsedBlock } from '@/utils/markdownParser'
import { getIconForMimeType } from '@/utils/fileIcons'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    id?: string
    subMessage: SubMessage
    parentMessage: Message
    showHeader?: boolean
    index?: number
    isInactive?: boolean
    isInline?: boolean
    previewSrcList?: string[]
    previewIndex?: number
  }>(),
  {
    id: '',
    showHeader: false,
    index: 1,
    isInactive: false,
    isInline: false,
    previewSrcList: () => [],
    previewIndex: 0,
  },
)

const emit = defineEmits<{
  (
    e: 'edit',
    payload: { content: string; range?: ParsedBlock['range']; language?: string; markup?: string },
  ): void
  (e: 'copy'): void
}>()

const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const isCollapsed = ref(props.subMessage.config.is_collapsed || false)
const isGenerating = computed(() => props.subMessage.status === 'generating')
const rootRef = ref<HTMLElement | null>(null)
const pendingFileController = ref<AbortController | null>(null)
const pendingFailed = ref(false)

const effectivePreviewSrcList = computed(() => {
  if (props.previewSrcList && props.previewSrcList.length > 0) {
    return props.previewSrcList
  }
  return props.subMessage.file_info?.url ? [props.subMessage.file_info.url] : []
})

const isToolType = computed(() => props.subMessage.type === 'McpTool' || props.subMessage.type === 'ReviewTool')

const toolContent = computed((): McpToolContent | ReviewToolContent | null => {
  if (!isToolType.value) return null
  try {
    return JSON.parse(props.subMessage.content)
  } catch {
    return null
  }
})

const mcpToolContent = computed((): McpToolContent | null => {
  if (props.subMessage.type === 'McpTool' && toolContent.value) {
    return toolContent.value as McpToolContent
  }
  return null
})

const isReviewDecided = computed(() => {
  if (props.subMessage.type !== 'ReviewTool') return false
  const content = toolContent.value as ReviewToolContent | null
  return !!content?.decision
})

const toolSummaryText = computed((): string => {
  if (!toolContent.value) return t('chat.message.mcp.invalidCall')
  const toolName = toolContent.value.name || t('chat.message.mcp.unknownTool')

  if (props.subMessage.type === 'ReviewTool') {
    if (!isReviewDecided.value) return t('chat.message.pendingReview')
    return t('chat.message.toolCallReviewed')
  }

  const mcpContent = toolContent.value as McpToolContent
  const query = typeof mcpContent.arguments === 'string' ? '...' : '...'

  if (isGenerating.value) return t('chat.message.mcp.searching', { tool: toolName, query })
  if (mcpContent.is_error) return t('chat.message.mcp.searchFailed', { tool: toolName, query })
  return t('chat.message.mcp.searched', { tool: toolName, query })
})

const fileIcon = computed(() => {
  if (props.subMessage.type === 'File' && props.subMessage.file_info) {
    return getIconForMimeType(props.subMessage.file_info.mime_type)
  }
  return Document
})

const formattedFileSize = computed(() => {
  if (props.subMessage.type !== 'File' || !props.subMessage.file_info) return ''
  const size = props.subMessage.file_info.size
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
})

const isPendingFile = computed(() =>
  props.subMessage.type === 'File' &&
  props.subMessage.status === 'waiting' &&
  !!props.subMessage.config.pending_file_path
)

const pendingFileName = computed(() => {
  if (!isPendingFile.value) return ''
  const path = props.subMessage.config.pending_file_path || ''
  return path.split('/').pop() || path
})

const pendingStatusText = computed(() => {
  if (pendingFailed.value) return t('chat.attachment.fileTimeout')
  return t('chat.attachment.waitingForFile')
})

const contentBlocks = computed(() => {
  if (props.subMessage.type !== 'File' && !isToolType.value) {
    return parseMarkdown(props.subMessage.content)
  }
  return []
})

const partitionTitle = computed(() => {
  if (isToolType.value) return t('chat.message.mcp.toolCallTitle', { name: toolContent.value?.name || 'Tool' })
  if (props.subMessage.type === 'Reasoning') return t('chat.message.reasoning')
  if (props.subMessage.type === 'Normal') return t('chat.message.content')
  return `Part ${props.index}`
})

watch(
  () => props.subMessage.config.is_collapsed,
  (val) => (isCollapsed.value = val || false),
)

function handleHeaderEditClick() {
  emit('edit', { content: props.subMessage.content })
}

function handleCodeBlockEdit(payload: {
  code: string
  range: ParsedBlock['range']
  language: string
  markup: string
}) {
  emit('edit', {
    content: payload.code,
    range: payload.range,
    language: payload.language,
    markup: payload.markup,
  })
}

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: { ...props.subMessage.config, is_collapsed: isCollapsed.value } },
  })
}

function toggleMinimize() {
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: { ...props.subMessage.config, is_minimal: true } },
  })
}

async function handleBlockCopy(content: string) {
  try {
    await copyToClipboard(content)
    ElMessage.success(t('chat.message.codeCopied'))
  } catch {
    ElMessage.error(t('chat.message.copyFailed'))
  }
}

onMounted(() => {
  if (isPendingFile.value) {
    pendingFileController.value = subscribeToPendingFile(props.subMessage.id, {
      onReady(fileId, fileInfo) {
        for (const msg of sessionStore.currentChatMessages) {
          const sm = msg.sub_messages.find(s => s.id === props.subMessage.id)
          if (sm) {
            sm.content = fileId
            sm.status = 'completed'
            sm.config = {
              ...sm.config,
              pending_file_path: undefined,
              pending_file_timeout: undefined,
            }
            sm.file_info = fileInfo as unknown as FileResponse
            break
          }
        }
      },
      onTimeout(_path) {
        pendingFailed.value = true
        for (const msg of sessionStore.currentChatMessages) {
          const sm = msg.sub_messages.find(s => s.id === props.subMessage.id)
          if (sm) {
            sm.status = 'failed'
            break
          }
        }
      },
      onError(_err) {
        // SSE connection error - keep showing pending state
      },
    })
  }
})

onBeforeUnmount(() => {
  if (pendingFileController.value) {
    pendingFileController.value.abort()
    pendingFileController.value = null
  }
})
</script>

<style scoped>
.sub-message-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  overflow: hidden;
}

.sub-message-item.is-inline {
  background: transparent;
}

.sub-message-item.is-inactive {
  opacity: 0.6;
}

.sub-message-item.is-review-pending {
  border-left: 3px solid var(--el-color-warning);
  padding-left: 8px;
}

.sub-message-item.is-file {
  overflow: visible;
}

/* File display */
.file-image-thumbnail {
  width: 100%;
  height: 300px;
  border-radius: 14px;
  display: block;
}

.file-display-container {
  width: 100%;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  max-width: 260px;
}

.is-user .file-card {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.35);
}

.file-card-info {
  flex: 1;
  min-width: 0;
}

.file-card-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: inherit;
}

.file-card-size {
  font-size: 11px;
  opacity: 0.7;
}

.file-pending-container {
  width: 100%;
}
.file-pending-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px dashed rgba(255, 255, 255, 0.4);
  max-width: 260px;
}
.is-user .file-pending-card {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.45);
}
.file-pending-icon {
  flex-shrink: 0;
  opacity: 0.7;
}
.file-pending-info {
  flex: 1;
  min-width: 0;
}
.file-pending-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: inherit;
}
.file-pending-status {
  font-size: 11px;
  opacity: 0.7;
  margin-top: 2px;
}

.sub-message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0 8px;
}

.partition-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.is-user .partition-title {
  color: rgba(255, 255, 255, 0.7);
}

.actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.action-icon {
  font-size: 15px;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  padding: 4px;
}

.is-user .action-icon {
  color: rgba(255, 255, 255, 0.6);
}

.message-content {
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text);
  overflow-x: auto;
}

.is-user .message-content {
  color: rgba(255, 255, 255, 0.95);
}

.message-content.collapsed {
  display: none;
}

.content-block :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}

.content-block :deep(pre) {
  margin: 6px 0;
  overflow-x: auto;
  font-size: 13px;
  border-radius: 8px;
}

.content-block :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  display: block;
  overflow-x: auto;
  font-size: 13px;
}

.content-block :deep(th),
.content-block :deep(td) {
  padding: 4px 8px;
  border: 1px solid var(--el-border-color);
  text-align: left;
}

.content-block :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.content-block :deep(blockquote) {
  margin: 6px 0;
  padding-left: 10px;
  border-left: 3px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.mcp-tool-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mcp-tool-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.mcp-tool-result {
  background: var(--el-fill-color-light);
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  max-height: 120px;
  overflow-y: auto;
}

.text-warning {
  color: var(--el-color-warning-dark-2);
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 5px;
  height: 5px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>

