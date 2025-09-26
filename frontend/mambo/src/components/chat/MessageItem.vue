<template>
  <div class="message-item-container" :class="roleClass">
    <!-- 头像 -->
    <div class="message-avatar">
      <el-avatar>
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <!-- 消息内容 -->
    <div class="message-content" v-html="renderedContent"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Message } from '@/api/types';
import { User, Cpu } from '@element-plus/icons-vue';

// 引入 markdown-it 和 highlight.js
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';

// -- Props 定义 --
const props = defineProps<{
  message: Message;
}>();

// -- Markdown 渲染逻辑 --
// 初始化 markdown-it 实例
const md = new MarkdownIt({
  // 核心：配置 highlight.js 作为语法高亮器
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return '<pre class="hljs"><code>' +
               hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
               '</code></pre>';
      } catch (__) {}
    }
    // 如果没有指定语言或高亮失败，则进行普通转义
    return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>';
  }
});

// 使用 computed 属性来缓存渲染结果
// 只有当 message.content 变化时，才会重新渲染
const renderedContent = computed(() => {
  return md.render(props.message.content);
});

// -- 动态样式 --
// 根据消息角色返回不同的 class
const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));
</script>

<!--
  注意: 这里我们使用两个 <style> 块。
  第一个不带 scoped，用于引入 highlight.js 的全局主题样式。
  第二个带 scoped，用于定义组件自身的局部样式。
-->
<style>
/* 引入 highlight.js 的代码高亮主题 (这里使用 GitHub Dark) */
@import 'highlight.js/styles/github-dark.css';

/* 对 highlight.js 的样式进行微调，使其更适合我们的UI */
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
  margin-bottom: 20px;
  max-width: 90%; /* 避免消息过长撑满整个屏幕 */
}

.message-avatar {
  flex-shrink: 0;
  margin-right: 12px;
}

.message-content {
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  word-break: break-word; /* 确保长单词或链接能正常换行 */
  line-height: 1.7;
}

/* -- 用户消息样式 -- */
.is-user {
  flex-direction: row-reverse; /* 核心：头像和内容反向排列 */
  margin-left: auto; /* 核心：整个容器靠右对齐 */
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}
.is-user .message-content {
  background-color: var(--el-color-primary-light-9);
}

/*
  使用 :deep() 选择器来穿透 scoped 样式，
  为 v-html 渲染出的 Markdown 内容设置样式。
*/
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
</style>
