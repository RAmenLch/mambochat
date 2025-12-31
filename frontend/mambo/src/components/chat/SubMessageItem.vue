<!-- frontend/mambo/src/components/chat/SubMessageItem.vue -->
<template>
  <div
    :id="id"
    class="sub-message-item"
    :class="{
      'is-user': parentMessage.role === 'user',
      'is-file': subMessage.type === 'File'
    }"
  >
    <!-- 文件类型消息的专属渲染 -->
    <div v-if="subMessage.type === 'File' && subMessage.file_info" class="file-display-container">
      <el-image
        v-if="subMessage.file_info.mime_type.startsWith('image/')"
        :src="subMessage.file_info.url"
        :preview-src-list="[subMessage.file_info.url]"
        :initial-index="0"
        fit="cover"
        class="file-image-thumbnail"
        hide-on-click-modal
      >
        <template #error>
          <div class="file-placeholder">
            <el-icon><Picture /></el-icon>
            <span>图片加载失败</span>
          </div>
        </template>
      </el-image>

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
        <a :href="subMessage.file_info.url" download class="file-card-download">
          <el-button :icon="Download" circle />
        </a>
      </div>
    </div>

    <!-- MCP 工具调用类型 或 其他带头部的类型 -->
    <template v-else>
      <div v-if="showHeader || subMessage.type === 'McpTool'" class="sub-message-header">
        <!-- MCP Tool Collapsed Header View -->
        <div v-if="subMessage.type === 'McpTool' && isCollapsed" class="mcp-collapsed-summary">
          <div class="mcp-tool-status-icon">
            <el-icon v-if="isGenerating" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="mcpContent && mcpContent.is_error" color="var(--el-color-error)"><CircleClose /></el-icon>
            <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
          </div>
          <span class="mcp-collapsed-text" :title="mcpSummaryText">{{ mcpSummaryText }}</span>
        </div>
        <!-- Default Header View -->
        <span v-else class="partition-title">{{ partitionTitle }}</span>

        <div class="actions">
          <!-- 编辑和复制按钮不适用于 McpTool -->
          <template v-if="subMessage.type !== 'McpTool'">
            <el-tooltip content="编辑" placement="top" :show-after="500">
              <el-button :icon="Edit" circle text size="small" @click="handleHeaderEditClick" :disabled="isGenerating" />
            </el-tooltip>
            <el-tooltip content="复制" placement="top" :show-after="500">
              <el-button :icon="CopyDocument" circle text size="small" @click="emit('copy')" :disabled="isGenerating" />
            </el-tooltip>
          </template>
          <el-tooltip content="最小化" placement="top" :show-after="500">
            <el-button
              :icon="Minus"
              circle
              text
              size="small"
              @click="toggleMinimize"
              :disabled="isGenerating || isMinimizeDisabled"
            />
          </el-tooltip>
          <el-tooltip :content="isCollapsed ? '展开' : '折叠'" placement="top" :show-after="500">
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

      <!-- MCP 工具调用内容 -->
      <div v-if="subMessage.type === 'McpTool' && !isCollapsed" class="message-content mcp-tool-content">
        <div v-if="mcpContent" class="mcp-tool-body">
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon v-if="isGenerating" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="mcpContent.is_error" color="var(--el-color-error)"><CircleClose /></el-icon>
              <el-icon v-else color="var(--el-color-success)"><CircleCheck /></el-icon>
            </div>
            <span>{{ mcpSummaryText }}</span>
          </div>
          <div v-if="!isGenerating && mcpContent.result && !mcpContent.is_error" class="mcp-tool-result">
            {{ mcpContent.result }}
          </div>
          <div v-if="!isGenerating && mcpContent.is_error" class="mcp-tool-error-message">
            工具执行出错。
          </div>
        </div>
        <div v-else class="mcp-tool-body">
          <!-- Fallback for parsing error -->
          <div class="mcp-tool-summary">
            <div class="mcp-tool-status-icon">
              <el-icon color="var(--el-color-error)"><CircleClose /></el-icon>
            </div>
            <span>无法解析工具调用内容</span>
          </div>
        </div>
      </div>

      <!-- 普通文本内容 -->
      <div v-else-if="subMessage.type !== 'McpTool'" class="message-content" :class="{ collapsed: isCollapsed }">
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
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { SubMessage, Message, SubMessageConfig, McpToolContent } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { ElMessage } from 'element-plus';
import {
  Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Download, Picture, Minus,
  Loading, CircleClose, CircleCheck
} from '@element-plus/icons-vue';
import CodeBlock from './CodeBlock.vue';
import { copyToClipboard } from '@/utils/clipboard';
import { parseMarkdown } from '@/utils/markdownParser';
import { getIconForMimeType } from '@/utils/fileIcons';

const props = withDefaults(defineProps<{
  id?: string;
  subMessage: SubMessage;
  parentMessage: Message;
  showHeader?: boolean;
  index?: number;
  isMinimizeDisabled?: boolean;
}>(), {
  id: '',
  showHeader: false,
  index: 1,
  isMinimizeDisabled: false,
});

const emit = defineEmits<{
  (e: 'edit', payload: { content: string, blockIndex?: number }): void;
  (e: 'copy'): void;
}>();

const interactionStore = useChatInteractionStore();
const isCollapsed = ref(props.subMessage.config.is_collapsed || false);
const isGenerating = computed(() => props.subMessage.status === 'generating');

// --- Computed properties for McpTool type ---
const mcpContent = computed((): McpToolContent | null => {
  if (props.subMessage.type !== 'McpTool') return null;
  try {
    return JSON.parse(props.subMessage.content);
  } catch (error) {
    console.error('Failed to parse McpTool content:', props.subMessage.content, error);
    return null;
  }
});

const mcpArguments = computed((): { query?: string } | null => {
  if (!mcpContent.value?.arguments) return null;
  try {
    return JSON.parse(mcpContent.value.arguments);
  } catch (error) {
    console.error('Failed to parse McpTool arguments:', mcpContent.value.arguments, error);
    return null;
  }
});

/**
 * 生成工具调用的摘要文本，用于在各种状态下显示。
 */
const mcpSummaryText = computed((): string => {
  if (!mcpContent.value) return '无效的工具调用';
  const toolName = mcpContent.value.name || '未知工具';
  const query = mcpArguments.value?.query || '...';

  if (isGenerating.value) {
    return `正在使用 ${toolName} 搜索: "${query}"`;
  }
  if (mcpContent.value.is_error) {
    return `使用 ${toolName} 搜索: "${query}" 时失败`;
  }
  return `使用 ${toolName} 搜索: "${query}"`;
});

// --- Computed properties for File type ---
const fileIcon = computed(() => {
  if (props.subMessage.type === 'File' && props.subMessage.file_info) {
    return getIconForMimeType(props.subMessage.file_info.mime_type);
  }
  return Document; // Fallback
});

const formattedFileSize = computed(() => {
  if (props.subMessage.type !== 'File' || !props.subMessage.file_info) return '';
  const size = props.subMessage.file_info.size;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
});

// --- Computed properties for Normal type ---
const contentBlocks = computed(() => {
  if (props.subMessage.type !== 'File' && props.subMessage.type !== 'McpTool') {
    return parseMarkdown(props.subMessage.content);
  }
  return [];
});

const partitionTitle = computed(() => {
  if (props.subMessage.type === 'McpTool') {
    return `工具调用: ${mcpContent.value?.name || '未知工具'}`;
  }
  if (props.subMessage.type === 'Reasoning') return '深度思考';
  if (props.subMessage.type === 'Normal') {
    const normalSubMessages = props.parentMessage.sub_messages.filter(sm => sm.type === 'Normal');
    if (normalSubMessages.length <= 1) return '正文';
    const normalIndex = normalSubMessages.findIndex(sm => sm.id === props.subMessage.id);
    if (normalIndex !== -1) return `正文(${normalIndex + 1})`;
  }
  return `分区 ${props.index}`;
});

watch(() => props.subMessage.config.is_collapsed, (newValue) => {
  isCollapsed.value = newValue || false;
});

function handleHeaderEditClick() {
  const payload = { content: props.subMessage.content };
  emit('edit', payload);
}

function handleCodeBlockEdit(code: string, blockIndex: number) {
  const payload = { content: code, blockIndex };
  emit('edit', payload);
}

function toggleCollapse() {
  const newCollapsedState = !isCollapsed.value;
  isCollapsed.value = newCollapsedState;
  const newConfig: SubMessageConfig = { ...props.subMessage.config, is_collapsed: newCollapsedState };
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: newConfig },
  });
}

function toggleMinimize() {
  const newConfig: SubMessageConfig = { ...props.subMessage.config, is_minimal: true };
  interactionStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { config: newConfig },
  });
}

async function handleBlockCopy(contentToCopy: string) {
  try {
    await copyToClipboard(contentToCopy);
    ElMessage.success('代码已复制到剪贴板');
  } catch (err) {
    ElMessage.error('复制失败');
    console.error('Could not copy text: ', err);
  }
}
</script>


<style scoped>
.sub-message-item { display: flex; flex-direction: column; max-width: 100%; border: 1px solid var(--el-border-color-light); border-radius: 6px; background-color: var(--color-background-soft); overflow: hidden; --sub-message-bg: var(--color-background-soft); }
.is-user .sub-message-item { background-color: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-8); --sub-message-bg: var(--el-color-primary-light-9); }

/* File type specific styles */
.sub-message-item.is-file { border: none; background-color: transparent; padding: 0; max-width: 260px; }
.file-display-container { width: 100%; }
.file-image-thumbnail { width: 100%; height: 160px; border-radius: 6px; border: 1px solid var(--el-border-color-lighter); background-color: var(--color-background); cursor: pointer; }
.file-placeholder { display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; height: 100%; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); font-size: 14px; }
.file-placeholder .el-icon { font-size: 32px; margin-bottom: 8px; }
.file-card { display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 6px; background-color: var(--color-background-soft); border: 1px solid var(--el-border-color-light); }
.is-user .file-card { background-color: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-8); }
.file-card-icon { flex-shrink: 0; color: var(--el-text-color-secondary); }
.file-card-info { flex-grow: 1; min-width: 0; }
.file-card-name { font-size: 14px; font-weight: 500; color: var(--el-text-color-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-card-size { font-size: 12px; color: var(--el-text-color-secondary); }
.file-card-download { flex-shrink: 0; }

/* MCP Tool type specific styles */
.mcp-tool-content { padding: 10px 15px; }
.mcp-tool-body { display: flex; flex-direction: column; gap: 8px; }
.mcp-tool-summary { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--el-text-color-secondary); }
.mcp-tool-status-icon .el-icon { font-size: 16px; }
.mcp-tool-status-icon .is-loading { animation: rotating 2s linear infinite; }
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
.mcp-tool-error-message { color: var(--el-color-error); font-size: 14px; }

/* Styles for text-based and MCP sub-messages */
.sub-message-header { display: flex; justify-content: space-between; align-items: center; padding: 2px 12px; background-color: rgba(0, 0, 0, 0.03); height: 32px; flex-shrink: 0; gap: 8px; }
.is-user .sub-message-header { background-color: rgba(64, 158, 255, 0.1); }
.partition-title { font-size: 12px; color: var(--el-text-color-secondary); font-weight: bold; flex-grow: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.actions .el-button { color: var(--el-text-color-secondary); }
.actions .el-button:hover { color: var(--el-text-color-primary); background-color: rgba(0, 0, 0, 0.05); }

.mcp-collapsed-summary { display: flex; align-items: center; gap: 8px; flex-grow: 1; min-width: 0; }
.mcp-collapsed-summary .mcp-tool-status-icon { flex-shrink: 0; }
.mcp-collapsed-text { font-size: 13px; color: var(--el-text-color-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.message-content { position: relative; word-break: break-word; line-height: 1.7; color: var(--color-text); min-height: 20px; transition: max-height 0.25s ease-out; max-height: 10000px; overflow: hidden; }
.message-content:not(.mcp-tool-content) { padding: 10px 15px; }
.is-user .message-content { color: var(--el-color-primary-dark-2); }
.message-content.collapsed { max-height: 5em; }
.message-content::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3em; background: linear-gradient(to bottom, transparent, var(--sub-message-bg)); pointer-events: none; opacity: 0; transition: opacity 0.25s ease-out; }
.message-content.collapsed::after { opacity: 1; }

.rendered-image { max-width: 100%; border-radius: 6px; margin: 0.5em 0; }
.content-block :deep(p) { margin: 0 0 0.5em; }
.content-block :deep(p:last-child) { margin-bottom: 0; }
.content-block :deep(ul), .content-block :deep(ol) { padding-inline-start: 25px; }
.content-block :deep(pre) { margin: 1em 0; }
.content-block :deep(code) { font-family: 'Courier New', Courier, monospace; }
.content-block :deep(pre > code) { padding: 0; background-color: transparent; }
.content-block :deep(:not(pre) > code) { background-color: rgba(0, 0, 0, 0.08); padding: 0.2em 0.4em; border-radius: 4px; font-size: 0.9em; }
.typing-indicator { display: flex; align-items: center; justify-content: center; height: 24px; }
.typing-indicator span { height: 8px; width: 8px; border-radius: 50%; background-color: #909399; margin: 0 3px; animation: bounce 1.4s infinite ease-in-out both; }
.typing-indicator span:nth-of-type(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-of-type(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
</style>
