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
      <div class="message-content">
        <!-- 加载中指示器 -->
        <div
          v-if="isGenerating && message.content === ''"
          class="typing-indicator"
        >
          <span></span><span></span><span></span>
        </div>
        <!-- 解析后的内容块 -->
        <template v-else>
          <div
            v-for="(block, index) in parsedContent"
            :key="index"
            class="content-block"
          >
            <CodeBlock
              v-if="block.type === 'code'"
              :code="block.content"
              :language="block.language"
              :is-generating="isGenerating"
              @edit="handleEditCodeBlock"
            />
            <div v-else v-html="block.content"></div>
          </div>
        </template>
      </div>

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
import DOMPurify from 'dompurify';
import CodeBlock from './CodeBlock.vue'; // 引入新组件

interface ParsedBlock {
  type: 'html' | 'code';
  content: string;
  language?: string;
}

// -- Props 定义 --
const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
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

// 新增：处理代码块的编辑请求
const handleEditCodeBlock = (code: string) => {
  editingMessage.value = props.message;
  editingContent.value = code;
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
const md = new MarkdownIt({ html: false });

// 重构渲染逻辑，将Markdown解析为块数组
const parsedContent = computed((): ParsedBlock[] => {
  if (!props.message.content) return [];

  const tokens = md.parse(props.message.content, {});
  const blocks: ParsedBlock[] = [];
  let currentHtmlTokens: any[] = [];

  const renderHtml = () => {
    if (currentHtmlTokens.length > 0) {
      const rawHtml = md.renderer.render(currentHtmlTokens, md.options, {});
      blocks.push({
        type: 'html',
        content: DOMPurify.sanitize(rawHtml),
      });
      currentHtmlTokens = [];
    }
  };

  for (const token of tokens) {
    if (token.type === 'fence') {
      renderHtml(); // 渲染之前积累的HTML
      blocks.push({
        type: 'code',
        content: token.content,
        language: token.info.split(/\s+/g)[0], // 获取语言名称
      });
    } else {
      currentHtmlTokens.push(token);
    }
  }

  renderHtml(); // 渲染剩余的HTML

  return blocks;
});

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));
</script>

<style>
/* 移除全局的 highlight.js 样式导入，因为它现在由 CodeBlock.vue 局部管理 */
/* @import 'highlight.js/styles/github-dark.css'; */

/* .hljs { ... } 样式也移至 CodeBlock.vue */
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
.content-block :deep(p) { margin: 0 0 0.5em; }
.content-block :deep(p:last-child) { margin-bottom: 0; }
.content-block :deep(ul), .content-block :deep(ol) { padding-inline-start: 25px; }
.content-block :deep(pre) { margin: 1em 0; }
.content-block :deep(code) { font-family: 'Courier New', Courier, monospace; }
.content-block :deep(pre > code) { padding: 0; background-color: transparent; }
.content-block :deep(:not(pre) > code) {
  background-color: rgba(0, 0, 0, 0.08);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}

/* -- 打字动画 -- */
.typing-indicator { display: flex; align-items: center; justify-content: center; height: 24px; }
.typing-indicator span {
  height: 8px; width: 8px; border-radius: 50%; background-color: #909399; margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.typing-indicator span:nth-of-type(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-of-type(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
</style>
