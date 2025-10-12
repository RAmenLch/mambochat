<template>
  <div class="code-block-container">
    <div class="code-block-header">
      <span class="language-name">{{ language || 'text' }}</span>
      <div class="actions">
        <span class="line-count">{{ totalLines }} lines</span>
        <el-tooltip content="编辑" placement="top" :show-after="500">
          <el-button
            :icon="Edit"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="emitEdit"
          />
        </el-tooltip>
        <el-tooltip content="复制" placement="top" :show-after="500">
          <el-button
            :icon="CopyDocument"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="copyCode"
          />
        </el-tooltip>
        <el-tooltip
          :content="isCollapsed ? '展开' : '折叠'"
          placement="top"
          :show-after="500"
        >
          <el-button
            :icon="isCollapsed ? ArrowDownBold : ArrowUpBold"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="toggleCollapse"
          />
        </el-tooltip>
      </div>
    </div>
    <div
      class="code-block-content"
      :class="{ collapsed: isCollapsed }"
      ref="contentRef"
    >
      <pre class="hljs"><code v-html="highlightedCode"></code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import {
  Edit,
  CopyDocument,
  ArrowUpBold,
  ArrowDownBold,
} from '@element-plus/icons-vue';
import hljs from 'highlight.js';
import 'highlight.js/styles/github-dark.css';

// --- 常量定义 ---
const DEFAULT_COLLAPSE_THRESHOLD = 20; // 超过20行的代码默认折叠

const props = defineProps<{
  code: string;
  language: string;
  isGenerating?: boolean;
}>();

const emit = defineEmits(['edit']);

// --- 状态计算 ---
const totalLines = computed(() => props.code.split('\n').length);
const isCollapsed = ref(totalLines.value > DEFAULT_COLLAPSE_THRESHOLD);

const highlightedCode = computed(() => {
  const lang = props.language || 'plaintext';
  if (lang && hljs.getLanguage(lang)) {
    try {
      return hljs.highlight(props.code, {
        language: lang,
        ignoreIllegals: true,
      }).value;
    } catch (e) {
      console.error(e);
    }
  }
  return hljs.escapeHTML(props.code);
});

// --- 事件处理 ---
const copyCode = () => {
  navigator.clipboard
    .writeText(props.code)
    .then(() => {
      ElMessage.success('已复制到剪贴板');
    })
    .catch((err) => {
      ElMessage.error('复制失败');
      console.error('Could not copy text: ', err);
    });
};

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value;
};

const emitEdit = () => {
  emit('edit', props.code);
};
</script>

<style scoped>
.code-block-container {
  background-color: var(--hljs-background, #2d2d2d);
  color: var(--hljs-color, #ccc);
  border-radius: 6px;
  margin: 1em 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light);
}

.code-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  background-color: rgba(255, 255, 255, 0.05);
  height: 32px;
}

.language-name {
  font-size: 12px;
  color: #ccc;
  font-family: 'Courier New', Courier, monospace;
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.line-count {
  font-size: 12px;
  color: #999;
  margin-right: 8px;
  user-select: none;
}

.actions .el-button {
  color: #ccc;
}

.actions .el-button:hover {
  color: #fff;
  background-color: rgba(255, 255, 255, 0.1);
}

.code-block-content {
  position: relative; /* 为 ::after 伪元素定位 */
  max-height: 800px; /* 默认最大高度 */
  overflow: auto;
  transition: max-height 0.3s ease-in-out;
}

.code-block-content.collapsed {
  /* 设定一个大约3行代码+padding的高度作为预览高度 */
  max-height: 6.5em;
  overflow: hidden;
}

/* 折叠时添加底部渐变遮罩，提示有更多内容 */
.code-block-content.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(
    to bottom,
    transparent,
    var(--hljs-background, #2d2d2d)
  );
  pointer-events: none; /* 确保遮罩不影响文本选择 */
}

.code-block-content pre,
.code-block-content code {
  color: inherit;
  font-family: 'Courier New', Courier, monospace;
}

.code-block-content pre {
  margin: 0;
}

.hljs {
  padding: 1em !important;
  font-size: 14px;
  line-height: 1.5;
  background-color: transparent !important;
}
</style>
