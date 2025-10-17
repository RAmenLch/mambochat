<template>
  <div
    class="sub-message-item"
    :class="{ 'is-user': parentMessage.role === 'user' }"
  >
    <!-- 分区头部 (仅在 showHeader 为 true 时显示) -->
    <div v-if="showHeader" class="sub-message-header">
      <span class="partition-title">分区 {{ index }}</span>
      <div class="actions">
        <!-- 编辑 -->
        <el-tooltip content="编辑" placement="top" :show-after="500">
          <el-button :icon="Edit" circle text size="small" @click="$emit('edit', subMessage.content)" :disabled="isGenerating" />
        </el-tooltip>
        <!-- 复制 -->
        <el-tooltip content="复制" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle text size="small" @click="$emit('copy')" :disabled="isGenerating" />
        </el-tooltip>
        <!-- 折叠/展开 -->
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

    <!-- 消息内容 -->
    <div class="message-content" :class="{ collapsed: isCollapsed }">
      <!-- 加载中指示器 (仅对内容为空的生成中分区显示) -->
      <div
        v-if="isGenerating && subMessage.content === ''"
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
            :language="block.language || 'Text'"
            :is-generating="isGenerating"
            @edit="(code) => $emit('edit', code)"
            @copy="handleBlockCopy"
          />
          <div v-else v-html="block.content"></div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { SubMessage, Message } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessage } from 'element-plus';
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold } from '@element-plus/icons-vue';
import * as MarkdownIt from 'markdown-it';
import * as markdownItLinkAttributes from 'markdown-it-link-attributes';
import DOMPurify from 'dompurify';
import CodeBlock from './CodeBlock.vue';
import { copyToClipboard } from '@/utils/clipboard';

interface ParsedBlock {
  type: 'html' | 'code';
  content: string;
  language?: string;
}

// 定义 Props 的接口
interface Props {
  subMessage: SubMessage;
  parentMessage: Message;
  showHeader?: boolean;
  index?: number;
}

// 使用 withDefaults 来为 props 提供默认值
const props = withDefaults(defineProps<Props>(), {
  showHeader: false,
  index: 1,
});

// 声明组件可触发的事件
defineEmits(['edit', 'copy']);

const chatStore = useChatStore();

const isCollapsed = ref(props.subMessage.config.is_collapsed || false);
const isGenerating = computed(
  () => props.subMessage.status === 'generating'
);

// 监听来自store/prop的变动, 确保UI同步
watch(() => props.subMessage.config.is_collapsed, (newValue) => {
  isCollapsed.value = newValue || false;
});

const toggleCollapse = () => {
  const newCollapsedState = !isCollapsed.value;
  isCollapsed.value = newCollapsedState; // 乐观更新UI
  chatStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: {
      config: { ...props.subMessage.config, is_collapsed: newCollapsedState },
    },
  });
};

const handleBlockCopy = (contentToCopy: string) => {
  copyToClipboard(contentToCopy)
    .then(() => {
      ElMessage.success('代码已复制到剪贴板');
    })
    .catch((err) => {
      ElMessage.error('复制失败');
      console.error('Could not copy text: ', err);
    });
};

// 初始化 Markdown-it, 启用 breaks 选项以支持单回车换行
const md = new MarkdownIt.default({
  html: false,
  breaks: true,
  linkify: true,
}).use(markdownItLinkAttributes.default, {
  attrs: {
    target: '_blank',
    rel: 'noopener noreferrer',
  },
});

const parsedContent = computed((): ParsedBlock[] => {
  if (!props.subMessage.content) return [];

  const tokens = md.parse(props.subMessage.content, {});
  const blocks: ParsedBlock[] = [];
  type MarkdownItToken = ReturnType<typeof md.parse>[number];
  let currentHtmlTokens: MarkdownItToken[] = [];

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
      renderHtml();
      blocks.push({
        type: 'code',
        content: token.content,
        language: token.info.split(/\s+/g)[0],
      });
    } else {
      currentHtmlTokens.push(token);
    }
  }
  renderHtml();
  return blocks;
});
</script>

<style scoped>
.sub-message-item {
  display: flex;
  flex-direction: column;
  max-width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background-color: var(--color-background-soft);
  overflow: hidden;

  --sub-message-bg: var(--color-background-soft);
}

.is-user .sub-message-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
  --sub-message-bg: var(--el-color-primary-light-9);
}

.sub-message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 12px;
  background-color: rgba(0, 0, 0, 0.03);
  height: 32px;
  flex-shrink: 0;
}

.is-user .sub-message-header {
  background-color: rgba(64, 158, 255, 0.1);
}

.partition-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: bold;
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.actions .el-button {
  color: var(--el-text-color-secondary);
}

.actions .el-button:hover {
  color: var(--el-text-color-primary);
  background-color: rgba(0, 0, 0, 0.05);
}

.message-content {
  position: relative;
  padding: 10px 15px;
  word-break: break-word;
  line-height: 1.7;
  color: var(--color-text);
  min-height: 20px;
  transition: max-height 0.25s ease-out;
  /* 设定一个足够大的值以容纳非常长的消息,同时保持动画效果 */
  max-height: 10000px;
  overflow: hidden;
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
