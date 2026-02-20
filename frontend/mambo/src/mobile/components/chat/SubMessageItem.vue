<!-- frontend/mambo/src/mobile/components/chat/SubMessageItem.vue -->
<template>
  <div
    :id="id"
    ref="rootRef"
    class="sub-message-item"
    :class="{
      'is-user': parentMessage.role === 'user',
      'is-file': subMessage.type === 'File',
    }"
  >
    <!-- 文件类型消息 -->
    <div v-if="subMessage.type === 'File' && subMessage.file_info" class="file-display-container">
      <el-image
        v-if="subMessage.file_info.mime_type.startsWith('image/')"
        :src="subMessage.file_info.url"
        :preview-src-list="[subMessage.file_info.url]"
        :initial-index="0"
        fit="cover"
        class="file-image-thumbnail"
        hide-on-click-modal
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

    <!-- MCP 工具 或 普通文本 -->
    <template v-else>
      <div v-if="showHeader || subMessage.type === 'McpTool'" class="sub-message-header">
        <!-- 标题区域 -->
        <span class="partition-title">{{ partitionTitle }}</span>

        <!-- 操作区域 -->
        <div class="actions">
          <template v-if="subMessage.type !== 'McpTool' && !isGenerating">
            <el-icon class="action-icon" @click="handleHeaderEditClick"><Edit /></el-icon>
            <el-icon class="action-icon" @click="emit('copy')"><CopyDocument /></el-icon>
          </template>

          <!-- 最小化按钮 -->
          <el-icon class="action-icon" @click="toggleMinimize" v-if="!isGenerating"
            ><Minus
          /></el-icon>

          <!-- 折叠按钮 -->
          <el-icon class="action-icon" @click="toggleCollapse">
            <component :is="isCollapsed ? ArrowDownBold : ArrowUpBold" />
          </el-icon>
        </div>
      </div>

      <!-- 内容区域 -->
      <div
        class="message-content"
        :class="{ collapsed: isCollapsed, 'mcp-tool-content': subMessage.type === 'McpTool' }"
        ref="contentRef"
      >
        <!-- MCP 内容渲染 -->
        <div v-if="subMessage.type === 'McpTool'" class="mcp-tool-body">
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon v-if="isGenerating" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="mcpContent && mcpContent.is_error" color="var(--el-color-error)"
                ><CircleClose
              /></el-icon>
              <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
            </div>
            <span>{{ mcpSummaryText }}</span>
          </div>
          <div
            v-if="!isGenerating && mcpContent?.result && !mcpContent.is_error"
            class="mcp-tool-result"
          >
            {{ mcpContent.result }}
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
                @edit="(code) => handleCodeBlockEdit(code, idx)"
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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SubMessage, Message, SubMessageConfig, McpToolContent } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
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
} from '@element-plus/icons-vue'
import CodeBlock from '@/components/chat/CodeBlock.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { parseMarkdown } from '@/utils/markdownParser'
import { getIconForMimeType } from '@/utils/fileIcons'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    id?: string
    subMessage: SubMessage
    parentMessage: Message
    showHeader?: boolean
    index?: number
  }>(),
  {
    id: '',
    showHeader: false,
    index: 1,
  },
)

const emit = defineEmits<{
  (e: 'edit', payload: { content: string; blockIndex?: number }): void
  (e: 'copy'): void
}>()

const interactionStore = useChatInteractionStore()
const isCollapsed = ref(props.subMessage.config.is_collapsed || false)
const isGenerating = computed(() => props.subMessage.status === 'generating')
const rootRef = ref<HTMLElement | null>(null)

// --- MCP Logic ---
const mcpContent = computed((): McpToolContent | null => {
  if (props.subMessage.type !== 'McpTool') return null
  try {
    return JSON.parse(props.subMessage.content)
  } catch {
    return null
  }
})
const mcpArguments = computed(() => {
  if (!mcpContent.value?.arguments) return null
  try {
    return JSON.parse(mcpContent.value.arguments)
  } catch {
    return null
  }
})
const mcpSummaryText = computed((): string => {
  if (!mcpContent.value) return t('chat.message.mcp.invalidCall')
  const toolName = mcpContent.value.name || t('chat.message.mcp.unknownTool')
  const query = mcpArguments.value?.query || '...'
  if (isGenerating.value) return t('chat.message.mcp.searching', { tool: toolName, query })
  if (mcpContent.value.is_error)
    return t('chat.message.mcp.searchFailed', { tool: toolName, query })
  return t('chat.message.mcp.searched', { tool: toolName, query })
})

// --- File Logic ---
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

// --- Content Logic ---
const contentBlocks = computed(() => {
  if (props.subMessage.type !== 'File' && props.subMessage.type !== 'McpTool') {
    return parseMarkdown(props.subMessage.content)
  }
  return []
})

const partitionTitle = computed(() => {
  if (props.subMessage.type === 'McpTool')
    return t('chat.message.mcp.toolCallTitle', { name: mcpContent.value?.name || 'Tool' })
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
function handleCodeBlockEdit(code: string, blockIndex: number) {
  emit('edit', { content: code, blockIndex })
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
</script>

<style scoped>
.sub-message-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background-color: var(--color-background-soft);
  overflow: hidden;
  margin-bottom: 4px;
}
.is-user .sub-message-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}

/* File Styles */
.sub-message-item.is-file {
  background: transparent;
  border: none;
  padding: 0;
}
.file-image-thumbnail {
  width: 100%;
  border-radius: 8px;
  max-height: 200px;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
}
.file-card-info {
  flex-grow: 1;
  min-width: 0;
}
.file-card-name {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-card-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* Header Styles */
.sub-message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background-color: rgba(0, 0, 0, 0.03);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}
.partition-title {
  font-size: 12px;
  font-weight: bold;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  gap: 16px;
  align-items: center;
}
.action-icon {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

/* Content Styles */
.message-content {
  padding: 10px;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text);
  overflow-x: auto;
}
.message-content.collapsed {
  display: none;
}

/* Markdown Styles Adaptation */
.content-block :deep(img) {
  max-width: 100%;
  border-radius: 4px;
}
.content-block :deep(pre) {
  margin: 10px 0;
  overflow-x: auto;
}
.content-block :deep(table) {
  display: block;
  overflow-x: auto;
  width: 100%;
}
.content-block :deep(blockquote) {
  margin: 10px 0;
  padding-left: 10px;
  border-left: 3px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
}

/* MCP Styles */
.mcp-tool-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mcp-tool-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.mcp-tool-result {
  background-color: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
  font-size: 13px;
  max-height: 150px;
  overflow-y: auto;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 5px;
}
.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #999;
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
