<template>
  <div
    class="message-item-container"
    :class="roleClass"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <!-- 头像 -->
    <div class="message-avatar">
      <el-avatar>
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <!-- 消息主体 -->
    <div class="message-body">
      <!-- 消息内容 -->
      <div class="message-content" v-html="renderedContent"></div>

      <!-- 悬浮操作菜单 -->
      <div
        class="message-actions"
        :class="{ 'is-visible': showActions && !isGenerating }"
      >
        <!-- AI消息: 重新回答 -->
        <el-tooltip content="重新回答" placement="top" :show-after="500">
          <el-button
            v-if="message.role === 'assistant'"
            :icon="Refresh"
            circle
            size="small"
            @click="handleRegenerate"
          />
        </el-tooltip>
        <!-- 用户消息: 在下方重新回答 -->
        <el-tooltip content="在下方重新回答" placement="top" :show-after="500">
          <el-button
            v-if="message.role === 'user'"
            :icon="RefreshLeft"
            circle
            size="small"
            @click="handleRegenerate"
          />
        </el-tooltip>

        <!-- 编辑 -->
        <el-tooltip content="编辑" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="openEditDialog" />
        </el-tooltip>

        <!-- 复制 -->
        <el-tooltip content="复制" placement="top" :show-after="500">
          <el-button
            :icon="CopyDocument"
            circle
            size="small"
            @click="handleCopy"
          />
        </el-tooltip>

        <!-- 删除 -->
        <el-tooltip content="删除" placement="top" :show-after="500">
          <el-button
            :icon="Delete"
            circle
            size="small"
            type="danger"
            plain
            @click="handleDelete"
          />
        </el-tooltip>
      </div>
    </div>
  </div>

  <!-- 编辑消息弹窗 -->
  <el-dialog v-model="editDialogVisible" title="编辑消息" width="650px">
    <el-input
      v-model="editingContent"
      type="textarea"
      :rows="12"
      resize="none"
      placeholder="消息内容不能为空"
    />
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit">保存</el-button>
        <el-button
          v-if="editingMessage?.role === 'user'"
          type="success"
          @click="handleSaveAndSend"
        >
          保存并发送
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue';
import type { Message } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  User,
  Cpu,
  Refresh,
  RefreshLeft,
  Edit,
  CopyDocument,
  Delete,
} from '@element-plus/icons-vue';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import DOMPurify from 'dompurify';

// -- Props 定义 --
const props = defineProps<{
  message: Message;
  isLastMessage: boolean; // 仍然保留，可能用于其他UI逻辑
}>();

const chatStore = useChatStore();
const showActions = ref(false);

// --- 编辑弹窗状态 ---
const editDialogVisible = ref(false);
const editingContent = ref('');
const editingMessage = shallowRef<Message | null>(null);

// --- 业务逻辑 ---
const isGenerating = computed(
  () => props.message.role === 'assistant' && props.message.status === 'generating'
);

const handleRegenerate = () => {
  chatStore.regenerateFrom(props.message.id);
};

const openEditDialog = () => {
  editingMessage.value = props.message;
  editingContent.value = props.message.content;
  editDialogVisible.value = true;
};

const handleSaveEdit = () => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }
  chatStore.editMessage({
    messageId: editingMessage.value!.id,
    content: editingContent.value,
    resend: false,
  });
  editDialogVisible.value = false;
};

const handleSaveAndSend = () => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }
  chatStore.editMessage({
    messageId: editingMessage.value!.id,
    content: editingContent.value,
    resend: true,
  });
  editDialogVisible.value = false;
};

const handleCopy = () => {
  navigator.clipboard
    .writeText(props.message.content)
    .then(() => {
      ElMessage.success('已复制到剪贴板');
    })
    .catch((err) => {
      ElMessage.error('复制失败');
      console.error('Could not copy text: ', err);
    });
};

const handleDelete = () => {
  ElMessageBox.confirm('确定要删除这条消息吗？', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => {
      chatStore.deleteMessage(props.message.id);
    })
    .catch(() => {});
};

// --- 渲染逻辑 ---
const md = new MarkdownIt({
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return (
          '<pre class="hljs"><code>' +
          hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
          '</code></pre>'
        );
      } catch (__) {}
    }
    return (
      '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'
    );
  },
});

const renderedContent = computed(() => {
  if (isGenerating.value && props.message.content === '') {
    return '<div class="typing-indicator"><span></span><span></span><span></span></div>';
  }
  const rawHtml = md.render(props.message.content);
  // 在渲染前清理HTML，防止XSS攻击
  return DOMPurify.sanitize(rawHtml);
});

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));
</script>

<style>
@import 'highlight.js/styles/github-dark.css';

.hljs {
  border-radius: 6px;
  padding: 1em !important;
  font-size: 14px;
  line-height: 1.5;
}
</style>

<style scoped>
.message-item-container {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
  max-width: 90%;
}

.message-avatar {
  flex-shrink: 0;
  margin-right: 12px;
  margin-top: 2px;
}

.message-body {
  display: flex;
  flex-direction: column;
  min-width: 80px;
}

.message-content {
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  word-break: break-word;
  line-height: 1.7;
  color: var(--color-text);
  min-height: 40px;
}

.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  opacity: 0;
  visibility: hidden;
  height: 24px;
  transition: opacity 0.2s, visibility 0.2s;
}
.message-actions.is-visible {
  opacity: 1;
  visibility: visible;
}


/* -- 用户消息样式 -- */
.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}
.is-user .message-content {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary-dark-2);
}

.is-user .message-body {
  align-items: flex-end;
}
.is-assistant .message-body {
  align-items: flex-start;
}


/* -- v-html 内容样式 -- */
.message-content :deep(p) { margin: 0 0 0.5em; }
.message-content :deep(p:last-child) { margin-bottom: 0; }
.message-content :deep(ul), .message-content :deep(ol) { padding-inline-start: 25px; }
.message-content :deep(pre) { margin: 1em 0; }
.message-content :deep(code) { font-family: 'Courier New', Courier, monospace; }
.message-content :deep(pre > code) { padding: 0; background-color: transparent; }
.message-content :deep(:not(pre) > code) {
  background-color: rgba(0, 0, 0, 0.08);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}

/* -- 打字动画 -- */
.message-content :deep(.typing-indicator) { display: flex; align-items: center; justify-content: center; height: 24px; }
.message-content :deep(.typing-indicator span) {
  height: 8px; width: 8px; border-radius: 50%; background-color: #909399; margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.message-content :deep(.typing-indicator span:nth-of-type(1)) { animation-delay: -0.32s; }
.message-content :deep(.typing-indicator span:nth-of-type(2)) { animation-delay: -0.16s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
</style>
