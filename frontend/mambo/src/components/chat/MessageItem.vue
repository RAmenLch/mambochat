<template>
  <div class="message-item-container" :class="roleClass">
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

      <!-- 操作按钮区域 -->
      <div class="message-actions">
        <el-button
          v-if="
            message.role === 'assistant' && isLastMessage && !isGenerating
          "
          :icon="Refresh"
          circle
          size="small"
          title="重新生成"
          @click="chatStore.regenerateLastResponse()"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Message } from '@/api/types';
import { User, Cpu, Refresh } from '@element-plus/icons-vue';
import { useChatStore } from '@/stores/chatStore';

// 引入 markdown-it 和 highlight.js
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';

// -- Props 定义 --
const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
  isGenerating: boolean;
}>();

const chatStore = useChatStore();

// -- Markdown 渲染逻辑 --
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
  // 当内容为空或只有占位符时，显示一个加载动画或特定样式，以改善体验
  if (props.isGenerating && props.isLastMessage && props.message.content === '...') {
    return '<div class="typing-indicator"><span></span><span></span><span></span></div>';
  }
  return md.render(props.message.content);
});

// -- 动态样式 --
const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));
</script>

<style>
/* 确保 highlight.js 的样式能正确应用 */
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
  /* --- 核心修复: 顶部对齐头像和消息内容 --- */
  align-items: flex-start;
  margin-bottom: 20px;
  max-width: 90%;
}

.message-avatar {
  flex-shrink: 0;
  margin-right: 12px;
  /* 稍微将头像向下移动一点，使其与文本的第一行更对齐 */
  margin-top: 2px;
}

.message-body {
  display: flex;
  align-items: center; /* 垂直居中内容和按钮 */
  gap: 8px; /* 内容和按钮之间的间距 */
}

.message-content {
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  word-break: break-word;
  line-height: 1.7;
  color: var(--color-text);
}

.message-actions {
  flex-shrink: 0;
  opacity: 0; /* 默认隐藏 */
  transition: opacity 0.2s ease;
}

/* 鼠标悬停在整个消息体上时显示操作按钮 */
.message-body:hover .message-actions {
  opacity: 1;
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
.is-user .message-body {
  flex-direction: row-reverse;
}
.is-user .message-content {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary-dark-2);
}

/* -- 深度选择器样式，用于渲染 v-html 中的内容 -- */
.message-content :deep(p) {
  margin: 0 0 0.5em;
}
.message-content :deep(p:last-child) {
  margin-bottom: 0;
}
.message-content :deep(ul),
.message-content :deep(ol) {
  padding-inline-start: 25px;
}
.message-content :deep(pre) {
  margin: 1em 0;
}
.message-content :deep(code) {
  font-family: 'Courier New', Courier, monospace;
}
.message-content :deep(pre > code) {
  padding: 0;
  background-color: transparent;
}
.message-content :deep(:not(pre) > code) {
  background-color: rgba(0, 0, 0, 0.08);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}

/* AI 正在输入时的打字动画 */
.message-content :deep(.typing-indicator) {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px; /* 与单行文本高度接近 */
}
.message-content :deep(.typing-indicator span) {
  height: 8px;
  width: 8px;
  border-radius: 50%;
  background-color: #909399;
  margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.message-content :deep(.typing-indicator span:nth-of-type(1)) {
  animation-delay: -0.32s;
}
.message-content :deep(.typing-indicator span:nth-of-type(2)) {
  animation-delay: -0.16s;
}
@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>
