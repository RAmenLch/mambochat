<!-- frontend/mambo/src/components/chat/SubMessageItem.vue -->
<template>
  <div
    :id="id"
    ref="rootRef"
    class="sub-message-item"
    :class="{
      'is-user': parentMessage.role === 'user',
      'is-file': subMessage.type === 'File' && !(isEditableFile && !isImageFile),
      'is-inactive': isInactive,
      'is-inline': isInline,
      'show-mode-mini-avatar': showToolMode === 'Mini_Avatar',
      'show-mode-gal-avatar': showToolMode === 'Gal_Avatar',
      'show-mode-group': showToolMode === 'Group',
    }"
  >
    <div v-if="subMessage.type === 'File' && subMessage.file_info && showToolMode !== 'Mini_Avatar' && showToolMode !== 'Gal_Avatar'" class="file-display-container">
      <el-image
        v-if="subMessage.file_info.mime_type.startsWith('image/')"
        :src="subMessage.file_info.url"
        :preview-src-list="previewSrcList"
        :initial-index="previewIndex"
        fit="contain"
        class="file-image-thumbnail"
        hide-on-click-modal
      >
        <template #error>
          <div class="file-placeholder">
            <el-icon><Picture /></el-icon>
            <span>{{ t('chat.attachment.imageLoadFailed') }}</span>
          </div>
        </template>
      </el-image>

      <audio
        v-else-if="subMessage.file_info.mime_type.startsWith('audio/')"
        :src="subMessage.file_info.url"
        controls
        preload="metadata"
        class="file-audio-player"
      ></audio>

      <video
        v-else-if="subMessage.file_info.mime_type.startsWith('video/')"
        :src="subMessage.file_info.url"
        controls
        preload="metadata"
        class="file-video-player"
      ></video>

      <div v-else-if="isEditableFile && !isImageFile" class="editable-file-view">
        <div class="file-content-header">
          <div class="file-content-header-left">
            <el-icon :size="16"><component :is="fileIcon" /></el-icon>
            <span class="file-content-filename" :title="subMessage.file_info.filename">
              {{ subMessage.file_info.filename }}
            </span>
            <el-tag v-if="!isMarkdownFile" size="small" class="file-content-language-tag">
              {{ fileLanguage }}
            </el-tag>
          </div>
          <div class="file-content-header-actions">
            <el-tooltip
              :content="isFileContentCollapsed ? t('common.action.expand') : t('common.action.collapse')"
              placement="top"
              :show-after="500"
            >
              <el-button
                :icon="isFileContentCollapsed ? ArrowDownBold : ArrowUpBold"
                circle
                text
                size="small"
                @click="isFileContentCollapsed = !isFileContentCollapsed"
              />
            </el-tooltip>
            <el-tooltip
              :content="isFileCodeWrapEnabled ? t('chat.codeBlock.noWrap') : t('chat.codeBlock.wrap')"
              placement="top"
              :show-after="500"
            >
              <el-button
                :icon="Sort"
                circle
                text
                size="small"
                :class="{ 'wrap-active': isFileCodeWrapEnabled }"
                @click="isFileCodeWrapEnabled = !isFileCodeWrapEnabled"
              />
            </el-tooltip>
            <el-tooltip :content="t('common.action.edit')" placement="top" :show-after="500">
              <el-button :icon="Edit" circle text size="small" @click="handleFileEdit" />
            </el-tooltip>
            <el-tooltip :content="t('common.action.copy')" placement="top" :show-after="500">
              <el-button :icon="CopyDocument" circle text size="small" @click="handleCopyFileContent" />
            </el-tooltip>
            <a :href="subMessage.file_info.url" download class="file-content-download-link">
              <el-button :icon="Download" circle text size="small" />
            </a>
          </div>
        </div>

        <div v-if="fileContentLoading" class="file-content-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ t('common.status.loading') }}</span>
        </div>
        <div v-else-if="fileContentError" class="file-content-error">
          <span>{{ t('chat.attachment.fileLoadFailed') }}</span>
        </div>

        <div v-else-if="isMarkdownFile" class="message-content file-message-content" :class="{ collapsed: isFileContentCollapsed }">
          <div v-for="(block, idx) in fileContentBlocks" :key="idx" class="content-block">
            <CodeBlock
              v-if="block.type === 'code'"
              :code="block.content"
              :language="block.language || 'Text'"
              :is-generating="false"
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
            <div v-else class="markdown-content" v-html="block.content"></div>
          </div>
        </div>

        <div v-else class="file-code-wrapper" :class="{ collapsed: isFileContentCollapsed, 'wrap-enabled': isFileCodeWrapEnabled }">
          <CodeBlock
            :code="fileContent || ''"
            :language="fileLanguage"
            :is-generating="false"
            :range="{ start: 0, end: (fileContent || '').length }"
            :closed="true"
            :show-header="false"
            @edit="handleFileEditFromCodeBlock"
            @copy="handleBlockCopy"
          />
        </div>
      </div>

      <div v-else class="file-card">
        <div class="file-card-icon">
          <el-icon :size="32">
            <component :is="fileIcon" />
          </el-icon>
        </div>
        <div class="file-card-info">
          <div class="file-card-name" :title="subMessage.file_info.filename">
            {{ subMessage.file_info.filename }}
          </div>
          <div class="file-card-size">{{ formattedFileSize }}</div>
        </div>

        <el-button
          v-if="subMessage.file_info.editable"
          :icon="Edit"
          circle
          class="file-card-action"
          @click="handleFileEdit"
        />

        <a :href="subMessage.file_info.url" download class="file-card-download">
          <el-button :icon="Download" circle />
        </a>
      </div>
    </div>

    <div v-else-if="isPendingFile && showToolMode !== 'Mini_Avatar' && showToolMode !== 'Gal_Avatar'" class="file-pending-container">
      <div class="file-pending-card">
        <div class="file-pending-icon">
          <el-icon :size="28" class="is-loading"><Loading /></el-icon>
        </div>
        <div class="file-pending-info">
          <div class="file-pending-name">
            {{ pendingFileName }}
          </div>
          <div class="file-pending-status">
            {{ pendingStatusText }}
          </div>
        </div>
      </div>
    </div>

    <template v-else>
      <div v-if="showHeader || subMessage.type === 'McpTool'" class="sub-message-header">
        <div v-if="subMessage.type === 'McpTool' && isCollapsed" class="mcp-collapsed-summary">
          <div class="mcp-tool-status-icon">
            <el-icon v-if="isGenerating" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="mcpContent && mcpContent.is_error" color="var(--el-color-error)"
              ><CircleClose
            /></el-icon>
            <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
          </div>
          <span class="mcp-collapsed-text" :title="mcpSummaryText">{{ mcpSummaryText }}</span>
        </div>
        <span v-else class="partition-title">{{ partitionTitle }}</span>

        <div class="actions">
          <template v-if="subMessage.type !== 'McpTool'">
            <el-tooltip :content="t('common.action.edit')" placement="top" :show-after="500">
              <el-button
                :icon="Edit"
                circle
                text
                size="small"
                @click="handleHeaderEditClick"
                :disabled="isGenerating"
              />
            </el-tooltip>
            <el-tooltip :content="t('common.action.copy')" placement="top" :show-after="500">
              <el-button
                :icon="CopyDocument"
                circle
                text
                size="small"
                @click="emit('copy')"
                :disabled="isGenerating"
              />
            </el-tooltip>
          </template>

          <el-tooltip
            v-if="!(parentMessage.role === 'assistant' && subMessage.type === 'Normal')"
            :content="t('chat.message.minimize')"
            placement="top"
            :show-after="500"
          >
            <el-button
              :icon="Minus"
              circle
              text
              size="small"
              @click="toggleMinimize"
              :disabled="isGenerating || isMinimizeDisabled"
            />
          </el-tooltip>

          <el-tooltip
            :content="isCollapsed ? t('chat.message.expand') : t('chat.message.collapse')"
            placement="top"
            :show-after="500"
          >
            <el-button
              :icon="isCollapsed ? ArrowDownBold : ArrowUpBold"
              circle
              text
              size="small"
              @click="toggleCollapse"
              :disabled="isGenerating"
            />
          </el-tooltip>
        </div>
      </div>

      <div
        v-if="subMessage.type === 'McpTool' && !isCollapsed"
        class="message-content mcp-tool-content"
      >
        <div v-if="mcpContent" class="mcp-tool-body">
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon v-if="isGenerating" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="mcpContent.is_error" color="var(--el-color-error)"
                ><CircleClose
              /></el-icon>
              <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
            </div>
            <span>{{ mcpSummaryText }}</span>
          </div>
          <div
            v-if="!isGenerating && mcpContent.result && !mcpContent.is_error"
            class="mcp-tool-result"
          >
            <template v-if="mcpContent.media?.length">
              <div
                v-for="m in mcpContent.media"
                :key="m.file_id"
                class="mcp-tool-media"
              >
                <img
                  v-if="m.file_type === 'image'"
                  :src="mediaUrl(m)"
                  alt=""
                  class="mcp-tool-media-img"
                />
                <audio
                  v-else-if="m.file_type === 'audio'"
                  :src="mediaUrl(m)"
                  controls
                  preload="metadata"
                  class="mcp-tool-media-audio"
                ></audio>
                <video
                  v-else-if="m.file_type === 'video'"
                  :src="mediaUrl(m)"
                  controls
                  preload="metadata"
                  class="mcp-tool-media-video"
                ></video>
                <a
                  v-else-if="m.file_type === 'file'"
                  :href="mediaUrl(m)"
                  target="_blank"
                  rel="noopener"
                  class="mcp-tool-media-file"
                >
                  {{ m.filename || m.file_type }}
                </a>
              </div>
            </template>
            <template v-else>{{ mcpContent.result }}</template>
          </div>
          <div v-if="!isGenerating && mcpContent.is_error" class="mcp-tool-error-message">
            {{ t('chat.message.mcp.executionError') }}
          </div>
        </div>
        <div v-else class="mcp-tool-body">
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon color="var(--el-color-error)"><CircleClose /></el-icon>
            </div>
            <span>{{ t('chat.message.mcp.parseError') }}</span>
          </div>
        </div>
      </div>

      <div
        v-else-if="subMessage.type !== 'McpTool'"
        class="message-content"
        :class="{ collapsed: isCollapsed }"
        ref="contentRef"
      >
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
            <div v-else class="markdown-content" v-html="block.content"></div>
          </div>

          <div
            v-if="!isCollapsed && !isGenerating && showBackToTop"
            class="back-to-top-btn"
            @click.stop="scrollToTop"
            :title="t('chat.message.backToTop')"
          >
            <el-icon size="10"><Top /></el-icon>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SubMessage, Message, SubMessageConfig, McpToolContent, MultimodalMedia, FileResponse } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { usePendingFileStore } from '@/stores/pendingFileStore'
import { getFileContent } from '@/api/fileService'
import { resolveFileUrl } from '@/services/electronUrl'
import { unpackMcpToolCall } from '@/utils/mcpToolUnpack'
import { ElMessage } from 'element-plus'
import {
  Edit,
  CopyDocument,
  ArrowUpBold,
  ArrowDownBold,
  Download,
  Picture,
  Minus,
  Loading,
  CircleClose,
  CircleCheck,
  Top,
  Document,
  Sort,
} from '@element-plus/icons-vue'
import CodeBlock from './CodeBlock.vue'
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
    isMinimizeDisabled?: boolean
    isInactive?: boolean
    isInline?: boolean
    /** 预览图片列表，用于 el-image 的 preview-src-list（聚合同组所有图片 URL 以支持键盘导航） */
    previewSrcList?: string[]
    /** 当前图片在 previewSrcList 中的索引 */
    previewIndex?: number
  }>(),
  {
    id: '',
    showHeader: false,
    index: 1,
    isMinimizeDisabled: false,
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
  (e: 'edit-file', file: FileResponse): void
}>()

const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const pendingFileStore = usePendingFileStore()
const isCollapsed = ref(props.subMessage.config.is_collapsed || false)
const isGenerating = computed(() => props.subMessage.status === 'generating')
const rootRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)
const pendingFailed = ref(false)

const fileContent = ref<string | null>(null)
const fileContentLoading = ref(false)
const fileContentError = ref(false)
const isFileContentCollapsed = ref(false)

const isFileCodeWrapEnabled = ref(false)

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (contentRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        showBackToTop.value = entry.target.scrollHeight > 600
      }
    })
    resizeObserver.observe(contentRef.value)
  }

  if (isPendingFile.value) {
    pendingFileStore.register(props.subMessage.id, {
      onReady() {
        // 子消息数据已由 pendingFileStore 在 store 层更新，组件自动重渲染
      },
      onTimeout() {
        pendingFailed.value = true
      },
    })
  }

  if (isEditableFile.value && !isImageFile.value && props.subMessage.file_info) {
    fileContentLoading.value = true
    getFileContent(props.subMessage.file_info.id)
      .then((res) => { fileContent.value = res.content })
      .catch(() => { fileContentError.value = true })
      .finally(() => { fileContentLoading.value = false })
  }
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
  pendingFileStore.unregister(props.subMessage.id)
})

const mcpContent = computed((): McpToolContent | null => {
  if (props.subMessage.type !== 'McpTool') return null
  try {
    return JSON.parse(props.subMessage.content)
  } catch (error) {
    console.error('Failed to parse McpTool content:', props.subMessage.content, error)
    return null
  }
})

const mcpArguments = computed((): { query?: string } | null => {
  if (!mcpContent.value?.arguments) return null
  try {
    return JSON.parse(mcpContent.value.arguments)
  } catch (error) {
    console.error('Failed to parse McpTool arguments:', mcpContent.value.arguments, error)
    return null
  }
})

const mcpSummaryText = computed((): string => {
  if (!mcpContent.value) return t('chat.message.mcp.invalidCall')
  const unpacked = unpackMcpToolCall(mcpContent.value)
  const toolName = unpacked.displayName
  const query = mcpArguments.value?.query || '...'

  if (isGenerating.value) {
    return t('chat.message.mcp.searching', { tool: toolName, query })
  }
  if (mcpContent.value.is_error) {
    return t('chat.message.mcp.searchFailed', { tool: toolName, query })
  }
  return t('chat.message.mcp.searched', { tool: toolName, query })
})

/** 多模态媒体展示 url（后端已在 media.url 填充下载路径） */
function mediaUrl(m: MultimodalMedia | null | undefined): string {
  if (!m?.url) return ''
  return resolveFileUrl(m.url) || ''
}

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
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
})

const isPendingFile = computed(() =>
  props.subMessage.type === 'File' &&
  props.subMessage.status === 'waiting' &&
  !!props.subMessage.config.pending_file_path
)

const isEditableFile = computed(() =>
  props.subMessage.type === 'File' &&
  !!props.subMessage.file_info?.editable
)

const isImageFile = computed(() =>
  props.subMessage.type === 'File' &&
  !!props.subMessage.file_info?.mime_type?.startsWith('image/')
)

const isMarkdownFile = computed(() => {
  if (!isEditableFile.value || !props.subMessage.file_info) return false
  const filename = props.subMessage.file_info.filename.toLowerCase()
  return filename.endsWith('.md') || filename.endsWith('.markdown')
})

const showToolMode = computed(() =>
  props.subMessage.config.show_tool_mode || 'Normal'
)

function getLanguageFromFilename(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'jsx': 'javascript',
    'tsx': 'typescript', 'json': 'json', 'html': 'html', 'css': 'css',
    'scss': 'scss', 'less': 'less', 'xml': 'xml', 'yaml': 'yaml', 'yml': 'yaml',
    'toml': 'toml', 'ini': 'ini', 'cfg': 'ini', 'sh': 'bash', 'bash': 'bash',
    'ps1': 'powershell', 'bat': 'batch', 'sql': 'sql',
    'java': 'java', 'c': 'c', 'cpp': 'cpp', 'h': 'c',
    'cs': 'csharp', 'go': 'go', 'rs': 'rust', 'rb': 'ruby', 'php': 'php',
    'swift': 'swift', 'kt': 'kotlin', 'scala': 'scala', 'r': 'r',
    'vue': 'html', 'svelte': 'html', 'dockerfile': 'dockerfile',
    'gitignore': 'plaintext', 'env': 'plaintext', 'log': 'plaintext',
    'txt': 'plaintext', 'md': 'markdown', 'markdown': 'markdown',
  }
  return map[ext] || ext || 'plaintext'
}

const fileLanguage = computed(() => {
  if (!isEditableFile.value || !props.subMessage.file_info) return ''
  return getLanguageFromFilename(props.subMessage.file_info.filename)
})

const fileContentBlocks = computed(() => {
  if (!isMarkdownFile.value || !fileContent.value) return []
  return parseMarkdown(fileContent.value)
})

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
  if (props.subMessage.type !== 'File' && props.subMessage.type !== 'McpTool') {
    return parseMarkdown(props.subMessage.content)
  }
  return []
})

const partitionTitle = computed(() => {
  if (props.subMessage.type === 'McpTool') {
    const content = mcpContent.value
    const name = content ? unpackMcpToolCall(content).displayName : t('chat.message.mcp.unknownTool')
    return t('chat.message.mcp.toolCallTitle', { name })
  }
  if (props.subMessage.type === 'Reasoning') return t('chat.message.reasoning')
  if (props.subMessage.type === 'Normal') {
    const normalSubMessages = props.parentMessage.sub_messages.filter((sm) => sm.type === 'Normal')
    if (normalSubMessages.length <= 1) return t('chat.message.content')
    const normalIndex = normalSubMessages.findIndex((sm) => sm.id === props.subMessage.id)
    if (normalIndex !== -1) return t('chat.message.contentIndex', { index: normalIndex + 1 })
  }
  return t('chat.message.partitionIndex', { index: props.index })
})

watch(
  () => props.subMessage.config.is_collapsed,
  (newValue) => {
    isCollapsed.value = newValue || false
  },
)

watch(
  () => props.subMessage.file_info,
  (newInfo, oldInfo) => {
    if (newInfo && newInfo !== oldInfo && isEditableFile.value && !isImageFile.value) {
      fileContentLoading.value = true
      fileContentError.value = false
      getFileContent(newInfo.id)
        .then((res) => { fileContent.value = res.content })
        .catch(() => { fileContentError.value = true })
        .finally(() => { fileContentLoading.value = false })
    }
  },
)

function handleHeaderEditClick() {
  const payload = { content: props.subMessage.content }
  emit('edit', payload)
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

function handleFileEdit() {
  if (props.subMessage.file_info) {
    emit('edit-file', props.subMessage.file_info)
  }
}

function handleFileEditFromCodeBlock() {
  handleFileEdit()
}

async function handleCopyFileContent() {
  try {
    await copyToClipboard(fileContent.value || '')
    ElMessage.success(t('chat.message.codeCopied'))
  } catch (err) {
    ElMessage.error(t('chat.message.copyFailed'))
    console.error('Could not copy text: ', err)
  }
}

function toggleCollapse() {
  const newCollapsedState = !isCollapsed.value
  isCollapsed.value = newCollapsedState
  const newConfig: SubMessageConfig = {
    ...props.subMessage.config,
    is_collapsed: newCollapsedState,
  }
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: newConfig },
  })
}

function toggleMinimize() {
  const newConfig: SubMessageConfig = { ...props.subMessage.config, is_minimal: true }
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: newConfig },
  })
}

async function handleBlockCopy(contentToCopy: string) {
  try {
    await copyToClipboard(contentToCopy)
    ElMessage.success(t('chat.message.codeCopied'))
  } catch (err) {
    ElMessage.error(t('chat.message.copyFailed'))
    console.error('Could not copy text: ', err)
  }
}

function scrollToTop() {
  if (rootRef.value) {
    rootRef.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<style scoped>
.sub-message-item {
  display: flex;
  flex-direction: column;
  max-width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background-color: var(--el-bg-color);           /* ← 改为白色 */
  overflow: hidden;
  --sub-message-bg: var(--el-bg-color);            /* ← 同步 */
  position: relative;
  transition: all 0.3s ease;
}

/* 仅用于内联文本的无边框模式 */
.sub-message-item.is-inline {
  border: none;
  background-color: transparent;
  box-shadow: none;
  --sub-message-bg: transparent;
}

.sub-message-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  border-color: var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  --sub-message-bg: var(--el-fill-color-lighter);
}

.sub-message-item.is-inactive:hover {
  border-style: solid;
  border-color: var(--el-text-color-placeholder);
}

.is-user .sub-message-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
  --sub-message-bg: var(--el-color-primary-light-9);
}

.is-user .sub-message-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.is-user .sub-message-item.is-inactive:hover {
  border-style: solid;
  border-color: var(--el-color-primary-light-5);
}

.sub-message-item.is-file {
  display: inline-flex;
  border: none;
  background-color: transparent;
  padding: 0;
  max-width: 240px;
  overflow: visible;
}
/* 音频/视频文件需要更宽的容器以正确渲染控件 */
.sub-message-item.is-file:has(.file-audio-player),
.sub-message-item.is-file:has(.file-video-player) {
  max-width: 100%;
}
.file-display-container {
  overflow: visible;
  min-width: 0;
}
/* 音频/视频容器需要明确宽度，避免inline-flex收缩为0 */
.file-display-container:has(.file-audio-player),
.file-display-container:has(.file-video-player) {
  width: 100%;
  min-width: 300px;
}
/* el-image 固定展示框，fit="contain" 等比缩放完整显示图片 */
.file-image-thumbnail {
  width: 230px;
  height: 240px;
  display: block;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  background-color: var(--color-background);
  cursor: pointer;
}
.file-placeholder {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.file-placeholder .el-icon {
  font-size: 32px;
  margin-bottom: 8px;
}
.file-audio-player {
  display: block;
  width: 100%;
  max-width: 420px;
}
.file-video-player {
  display: block;
  width: 100%;
  max-width: 480px;
  border-radius: 6px;
  background-color: #000;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
}
.is-user .file-card {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}
.file-card-icon {
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
}
.file-card-info {
  flex-grow: 1;
  min-width: 0;
}
.file-card-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-card-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.file-card-action {
  flex-shrink: 0;
  margin-right: 8px;
}
.file-card-download {
  flex-shrink: 0;
}

.editable-file-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
  background-color: var(--el-bg-color);
}
.is-user .editable-file-view {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}

.file-content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  background-color: rgba(0, 0, 0, 0.03);
  height: 32px;
  flex-shrink: 0;
  gap: 8px;
}
.is-user .file-content-header {
  background-color: rgba(64, 158, 255, 0.1);
}

.file-content-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-grow: 1;
  min-width: 0;
  color: var(--el-text-color-secondary);
}

.file-content-filename {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-content-language-tag {
  flex-shrink: 0;
  font-size: 11px;
}

.file-content-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.file-content-header-actions .el-button {
  color: var(--el-text-color-secondary);
}
.file-content-header-actions .el-button:hover {
  color: var(--el-text-color-primary);
  background-color: rgba(0, 0, 0, 0.05);
}
.file-content-header-actions .el-button.wrap-active {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}
.file-content-download-link {
  display: inline-flex;
  text-decoration: none;
  color: inherit;
}

.file-content-loading,
.file-content-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 16px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.file-message-content {
  padding: 10px 15px;
}

.file-code-wrapper {
  overflow: hidden;
}
.file-code-wrapper.collapsed {
  max-height: 6.5em;
}
.file-code-wrapper.wrap-enabled :deep(pre),
.file-code-wrapper.wrap-enabled :deep(code) {
  white-space: pre-wrap !important;
  word-break: break-word;
  overflow-wrap: break-word;
}
.file-code-wrapper :deep(.code-block-container) {
  margin: 0;
  border-radius: 0;
  border: none;
}

.file-pending-container {
  overflow: visible;
}
.file-pending-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  background-color: var(--color-background-soft);
  border: 1px dashed var(--el-border-color);
}
.is-user .file-pending-card {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
.file-pending-icon {
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
}
.file-pending-info {
  flex-grow: 1;
  min-width: 0;
}
.file-pending-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-pending-status {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.mcp-tool-content {
  padding: 10px 15px;
}
.mcp-tool-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mcp-tool-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
.mcp-tool-status-icon .el-icon {
  font-size: 16px;
}
.mcp-tool-status-icon .is-loading {
  animation: rotating 2s linear infinite;
}
.mcp-tool-result {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
  background-color: var(--el-fill-color-light);
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.6;
}
.mcp-tool-error-message {
  color: var(--el-color-error);
  font-size: 14px;
}
.mcp-tool-media {
  margin-top: 6px;
}
.mcp-tool-media-img {
  display: block;
  max-width: 100%;
  max-height: 320px;
  border-radius: 6px;
}
.mcp-tool-media-audio,
.mcp-tool-media-video {
  display: block;
  width: 100%;
  max-width: 480px;
  margin-top: 4px;
}
.mcp-tool-media-file {
  color: var(--el-color-primary);
  text-decoration: underline;
}

.sub-message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 12px;
  background-color: rgba(0, 0, 0, 0.03);
  height: 32px;
  flex-shrink: 0;
  gap: 8px;
}
.is-user .sub-message-header {
  background-color: rgba(64, 158, 255, 0.1);
}
.partition-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: bold;
  flex-grow: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.actions .el-button {
  color: var(--el-text-color-secondary);
}
.actions .el-button:hover {
  color: var(--el-text-color-primary);
  background-color: rgba(0, 0, 0, 0.05);
}

.mcp-collapsed-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-grow: 1;
  min-width: 0;
}
.mcp-collapsed-summary .mcp-tool-status-icon {
  flex-shrink: 0;
}
.mcp-collapsed-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.message-content {
  position: relative;
  word-break: break-word;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  min-height: 20px;
  transition: max-height 0.25s ease-out;
  max-height: none;
  overflow: hidden;
}
.message-content:not(.mcp-tool-content) {
  padding: 10px 15px;
}
.sub-message-item.is-inline .message-content {
  padding: 0;
}
.is-user .message-content {
  color: var(--el-color-primary-dark-2);
}
.message-content.collapsed {
  max-height: 5em;
}
.message-content::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(to bottom, transparent, var(--sub-message-bg));
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.25s ease-out;
}
.message-content.collapsed::after {
  opacity: 1;
}

.rendered-image {
  max-width: 100%;
  border-radius: 6px;
  margin: 0.5em 0;
}
.content-block :deep(p) {
  margin: 0 0 0.5em;
}
.content-block :deep(p:last-child) {
  margin-bottom: 0;
}
.content-block :deep(strong),
.content-block :deep(b) {
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.content-block :deep(ul),
.content-block :deep(ol) {
  padding-inline-start: 25px;
}
.content-block :deep(pre) {
  margin: 1em 0;
}
.content-block :deep(code) {
  font-family: 'Courier New', Courier, monospace;
}
.content-block :deep(pre > code) {
  padding: 0;
  background-color: transparent;
}
.content-block :deep(:not(pre) > code) {
  background-color: rgba(0, 0, 0, 0.08);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}
.content-block :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  display: block;
  overflow-x: auto;
  border-spacing: 0;
}
.content-block :deep(th),
.content-block :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--el-border-color);
  text-align: left;
}
.content-block :deep(th) {
  background-color: var(--el-fill-color-light);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.content-block :deep(blockquote) {
  margin: 1em 0;
  padding: 8px 16px;
  border-left: 4px solid var(--el-border-color-darker);
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  border-radius: 0 4px 4px 0;
}

.content-block :deep(blockquote > p:last-child) {
  margin-bottom: 0;
}

.content-block :deep(blockquote blockquote) {
  margin: 8px 0;
  background-color: transparent;
  border-left-color: var(--el-border-color);
}

.is-user .content-block :deep(blockquote) {
  border-left-color: var(--el-color-primary);
  background-color: rgba(255, 255, 255, 0.2);
  color: var(--el-color-primary-dark-2);
}
.is-user .content-block :deep(strong),
.is-user .content-block :deep(b) {
  color: var(--el-color-primary-dark-2);
}

.content-block :deep(svg) {
  max-width: 100%;
  height: auto;
}

.typing-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
}
.typing-indicator span {
  height: 8px;
  width: 8px;
  border-radius: 50%;
  background-color: #909399;
  margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.typing-indicator span:nth-of-type(1) {
  animation-delay: -0.32s;
}
.typing-indicator span:nth-of-type(2) {
  animation-delay: -0.16s;
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

.back-to-top-btn {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  background-color: var(--color-background);
  border: 1px solid var(--el-border-color-light);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.5;
  transition: all 0.2s;
  z-index: 10;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  color: var(--el-text-color-regular);
}
.back-to-top-btn:hover {
  opacity: 1;
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
.is-user .back-to-top-btn {
  background-color: rgba(255, 255, 255, 0.8);
}
</style>
