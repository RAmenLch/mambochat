<!-- frontend/mambo/src/components/chat/ChatHeader.vue -->
<template>
  <div class="chat-header-container" :class="[`mode-${mode}`]">
    <!-- 竖向模式特有的顶部展开按钮 -->
    <div v-if="mode === 'vertical'" class="header-top-actions">
      <el-tooltip content="展开侧边栏" placement="right">
        <el-button link class="expand-btn" @click="$emit('expand')">
          <el-icon :size="18"><Expand /></el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <!-- 标题区域 -->
    <div class="title-section">
      <!-- 竖向编辑模式：使用 Popover -->
      <template v-if="mode === 'vertical'">
        <div class="vertical-title-wrapper">
          <h3 class="chat-title">{{ currentChat?.name || '未选择会话' }}</h3>
        </div>
      </template>

      <!-- 横向编辑模式：行内 Input 切换 -->
      <template v-else>
        <div v-if="!isEditingTitle && currentChat" class="horizontal-title-display">
          <h3 class="chat-title">{{ currentChat.name }}</h3>
          <div class="title-actions">
            <!-- 编辑和刷新保留在标题旁边 -->
            <el-tooltip content="编辑标题" placement="bottom" :show-after="500">
              <el-button :icon="Edit" circle text @click="startHorizontalEdit" />
            </el-tooltip>
            <el-tooltip content="刷新标题" placement="bottom" :show-after="500">
              <el-button
                :icon="Refresh"
                circle
                text
                @click="handleRefreshTitle"
                :loading="isTitleRefreshing"
              />
            </el-tooltip>
          </div>
        </div>
        <div v-else-if="isEditingTitle" class="title-edit-area">
          <el-input
            ref="titleInputRef"
            v-model="titleInput"
            @blur="saveTitle"
            @keydown.enter.prevent="saveTitle"
            class="title-input"
          />
        </div>
      </template>
    </div>

    <!-- [修改] 横向模式：右侧操作区 (导出按钮) -->
    <div v-if="mode === 'horizontal'" class="header-right-actions">
      <el-dropdown trigger="click" @command="handleExport">
        <el-button :icon="Download" circle text title="导出对话" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="json">导出 JSON</el-dropdown-item>
            <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
            <el-dropdown-item command="html">导出 HTML</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 竖向模式底部的操作按钮组 -->
    <div v-if="mode === 'vertical' && currentChat" class="header-bottom-actions">

      <!-- 编辑按钮 (Popover) -->
      <el-popover
        v-model:visible="isPopoverVisible"
        placement="right"
        :width="250"
        trigger="click"
        @show="initPopoverInput"
      >
        <template #reference>
          <el-button :icon="Edit" circle text class="action-btn" title="编辑标题" />
        </template>
        <div class="popover-edit-content">
          <el-input
            ref="popoverInputRef"
            v-model="titleInput"
            placeholder="输入新标题"
            @keydown.enter.prevent="saveTitle"
          />
          <el-button type="primary" size="small" @click="saveTitle">保存</el-button>
        </div>
      </el-popover>

      <!-- 刷新按钮 -->
      <el-tooltip content="刷新标题" placement="right">
        <el-button
          :icon="Refresh"
          circle
          text
          class="action-btn"
          @click="handleRefreshTitle"
          :loading="isTitleRefreshing"
        />
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue';
import type { ElInput } from 'element-plus';
import { ElMessage } from 'element-plus';
import { Edit, Refresh, Expand, Download } from '@element-plus/icons-vue';
import type { Chat, Message } from '@/api/types';
import { getResourceDetails } from '@/api/resourceService';

// [修改] 将 messages 设为可选属性，解决 ChatList 调用报错问题
const props = withDefaults(defineProps<{
  currentChat: Chat | null;
  isTitleRefreshing: boolean;
  mode?: 'horizontal' | 'vertical';
  messages?: Message[];
}>(), {
  mode: 'horizontal',
  messages: () => []
});

const emit = defineEmits<{
  (e: 'save-title', newTitle: string): void;
  (e: 'refresh-title'): void;
  (e: 'expand'): void;
}>();

// --- State ---
const isEditingTitle = ref(false);
const isPopoverVisible = ref(false);
const titleInput = ref('');
const isExporting = ref(false);

// Refs
const titleInputRef = ref<InstanceType<typeof ElInput>>();
const popoverInputRef = ref<InstanceType<typeof ElInput>>();

// --- Actions ---

function startHorizontalEdit() {
  if (!props.currentChat) return;
  isEditingTitle.value = true;
  titleInput.value = props.currentChat.name;
  nextTick(() => titleInputRef.value?.focus());
}

function initPopoverInput() {
  if (!props.currentChat) return;
  titleInput.value = props.currentChat.name;
  nextTick(() => popoverInputRef.value?.focus());
}

function saveTitle() {
  if (!props.currentChat) return;

  const newName = titleInput.value.trim();
  if (newName && newName !== props.currentChat.name) {
    emit('save-title', newName);
  }

  isEditingTitle.value = false;
  isPopoverVisible.value = false;
}

function handleRefreshTitle() {
  emit('refresh-title');
}

// --- Export Logic ---

async function getFullSystemPrompt(): Promise<string> {
  if (!props.currentChat) return '';

  const basePrompt = props.currentChat.systemPrompt || '';
  const resourceIds = props.currentChat.resource_prompt_list || [];

  if (resourceIds.length === 0) return basePrompt;

  try {
    const resources = await Promise.all(
      resourceIds.map(id => getResourceDetails(id).catch(() => null))
    );

    // [修改] 修复 TS2677 和 TS18047 错误
    // 不使用复杂的类型谓词，直接检查对象和属性是否存在
    const resourceContents = resources
      .filter(r => r && r.latest_version && r.latest_version.content)
      .map(r => r!.latest_version!.content!);

    return [basePrompt, ...resourceContents].join('\n\n').trim();
  } catch (error) {
    console.error('Failed to fetch resources for export:', error);
    ElMessage.warning('导出时获取挂载资源失败，仅导出基础 System Prompt');
    return basePrompt;
  }
}

function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function handleExport(format: 'json' | 'markdown' | 'html') {
  if (!props.currentChat) return;
  if (isExporting.value) return;

  isExporting.value = true;
  try {
    const fullPrompt = await getFullSystemPrompt();
    const chatName = props.currentChat.name || 'chat';
    const timestamp = new Date().toISOString().slice(0, 10);
    // 确保 messages 存在
    const msgs = props.messages || [];

    if (format === 'json') {
      const data = {
        system_prompt: fullPrompt,
        messages: msgs.map(msg => ({
          role: msg.role,
          content: msg.sub_messages
            .filter(sm => sm.type === 'Normal' || sm.type === 'File')
            .map(sm => sm.content)
            .join('\n'),
          created_at: msg.createdAt
        }))
      };
      triggerDownload(JSON.stringify(data, null, 2), `${chatName}_${timestamp}.json`, 'application/json');
    }
    else if (format === 'markdown') {
      let md = `# System Prompt\n\n${fullPrompt}\n\n---\n\n# Chat History\n\n`;

      msgs.forEach(msg => {
        const roleTitle = msg.role === 'user' ? 'User' : 'Assistant';
        const content = msg.sub_messages
          .filter(sm => sm.type === 'Normal' || sm.type === 'File')
          .map(sm => sm.content)
          .join('\n');

        md += `## ${roleTitle}\n\n${content}\n\n`;
      });

      triggerDownload(md, `${chatName}_${timestamp}.md`, 'text/markdown');
    }
    else if (format === 'html') {
      const messagesHtml = msgs.map(msg => {
        const roleClass = msg.role === 'user' ? 'user-message' : 'assistant-message';
        const roleLabel = msg.role === 'user' ? 'User' : 'Assistant';
        const content = msg.sub_messages
          .filter(sm => sm.type === 'Normal' || sm.type === 'File')
          .map(sm => `<div class="message-content">${escapeHtml(sm.content).replace(/\n/g, '<br>')}</div>`)
          .join('');

        return `
          <div class="message ${roleClass}">
            <div class="message-role">${roleLabel}</div>
            ${content}
          </div>
        `;
      }).join('');

      const html = `
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="UTF-8">
          <title>${escapeHtml(chatName)}</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f9f9; }
            .container { background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
            h1 { border-bottom: 2px solid #eee; padding-bottom: 10px; }
            .system-prompt { background: #f0f7ff; padding: 15px; border-radius: 6px; border-left: 4px solid #409eff; margin-bottom: 30px; white-space: pre-wrap; }
            .message { margin-bottom: 20px; padding: 15px; border-radius: 6px; }
            .message-role { font-weight: bold; margin-bottom: 8px; font-size: 0.9em; opacity: 0.8; }
            .user-message { background: #e6f7ff; border: 1px solid #bae7ff; }
            .assistant-message { background: #f6ffed; border: 1px solid #b7eb8f; }
            .message-content { white-space: pre-wrap; }
          </style>
        </head>
        <body>
          <div class="container">
            <h1>${escapeHtml(chatName)}</h1>
            <div class="system-prompt"><strong>System Prompt:</strong><br/>${escapeHtml(fullPrompt).replace(/\n/g, '<br/>')}</div>
            <div class="chat-history">${messagesHtml}</div>
          </div>
        </body>
        </html>
      `;
      triggerDownload(html, `${chatName}_${timestamp}.html`, 'text/html');
    }
  } catch (error) {
    console.error('Export failed:', error);
    ElMessage.error('导出失败');
  } finally {
    isExporting.value = false;
  }
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

watch(() => props.currentChat?.id, () => {
  isEditingTitle.value = false;
  isPopoverVisible.value = false;
});
</script>

<style scoped>
.chat-header-container {
  box-sizing: border-box;
  background-color: var(--color-background);
}

/* --- Horizontal Mode Styles --- */
.mode-horizontal {
  flex-shrink: 0;
  padding: 0 20px;
  height: 60px;
  display: flex;
  justify-content: space-between; /* 确保左右分布 */
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  width: 100%;
}

.horizontal-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  width: 100%;
}

.title-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.title-edit-area {
  width: 100%;
}

/* [新增] 右侧操作区样式 */
.header-right-actions {
  flex-shrink: 0;
  margin-left: 16px;
}

/* --- Vertical Mode Styles --- */
.mode-vertical {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
  overflow: hidden;
}

.header-top-actions {
  flex-shrink: 0;
  margin-bottom: 15px;
}

.expand-btn {
  color: var(--el-text-color-regular);
}

.expand-btn:hover {
  color: var(--el-color-primary);
}

.title-section {
  flex-grow: 1;
  display: flex;
  justify-content: center; /* 竖向模式居中 */
  overflow: hidden;
  /* [修改] 横向模式下，让 title-section 占据剩余空间，但不强制 100% 导致挤压右侧 */
  min-width: 0;
}

/* 针对横向模式的特殊调整 */
.mode-horizontal .title-section {
  justify-content: flex-start;
  width: auto; /* 允许 flex-grow 生效 */
}

.vertical-title-wrapper {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 2px;
  display: flex;
  align-items: center;
  padding: 10px 0;
}

.header-bottom-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 15px;
}

.action-btn {
  margin-left: 0 !important;
}

/* Common Text Styles */
.chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-heading);
}

.mode-horizontal .chat-title {
  font-size: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Popover Content */
.popover-edit-content {
  display: flex;
  gap: 8px;
}
</style>
