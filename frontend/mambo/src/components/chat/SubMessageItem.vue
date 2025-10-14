<template>
  <div
    class="sub-message-item"
    :class="{ 'is-user': parentMessage.role === 'user' }"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <!-- 消息内容 -->
    <div class="message-content">
      <!-- 加载中指示器 (仅对AI消息的第一个分区显示) -->
      <div
        v-if="isGenerating && subMessage.content === '' && subMessage.sortOrder === 0"
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
          />
          <div v-else v-html="block.content"></div>
        </div>
      </template>
    </div>

    <!-- 悬浮操作菜单 -->
    <div
      class="sub-message-actions"
      :class="{ 'is-visible': showActions && !isGenerating }"
    >
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
    </div>
  </div>

  <!-- 编辑消息弹窗 -->
  <el-dialog v-model="editDialogVisible" title="编辑分区内容" width="650px">
    <el-input
      v-model="editingContent"
      type="textarea"
      :rows="12"
      resize="none"
      placeholder="内容不能为空"
    />
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit">仅保存</el-button>
        <el-button
          v-if="parentMessage.role === 'user'"
          type="success"
          @click="handleSaveAndResend"
        >
          保存并重新生成
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { SubMessage, Message } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessage } from 'element-plus';
import { Edit, CopyDocument } from '@element-plus/icons-vue';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import CodeBlock from './CodeBlock.vue';

interface ParsedBlock {
  type: 'html' | 'code';
  content: string;
  language?: string;
}

const props = defineProps<{
  subMessage: SubMessage;
  parentMessage: Message;
}>();

const chatStore = useChatStore();
const showActions = ref(false);
const editDialogVisible = ref(false);
const editingContent = ref('');

const isGenerating = computed(
  () => props.parentMessage.role === 'assistant' && props.parentMessage.status === 'generating'
);

const openEditDialog = () => {
  editingContent.value = props.subMessage.content;
  editDialogVisible.value = true;
};

const handleSaveEdit = () => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }
  chatStore.updateSubMessage({
    subMessageId: props.subMessage.id,
    data: { content: editingContent.value },
  });
  editDialogVisible.value = false;
};

const handleSaveAndResend = () => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }

  // 构建新的 sub_messages 列表
  const newSubMessages = props.parentMessage.sub_messages.map(sm => ({
    content: sm.id === props.subMessage.id ? editingContent.value : sm.content,
    sortOrder: sm.sortOrder,
    type: sm.type,
    config: sm.config,
  }));

  chatStore.editMessageAndRegenerate({
    messageId: props.parentMessage.id,
    sub_messages: newSubMessages,
    resend: true,
  });
  editDialogVisible.value = false;
};

const handleCopy = () => {
  navigator.clipboard
    .writeText(props.subMessage.content)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'));
};

const md = new MarkdownIt({ html: false });

const parsedContent = computed((): ParsedBlock[] => {
  if (!props.subMessage.content) return [];

  const tokens = md.parse(props.subMessage.content, {});
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
}
.is-user .sub-message-item {
  align-items: flex-end;
}
.sub-message-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  opacity: 0;
  visibility: hidden;
  height: 24px;
  transition: opacity 0.2s, visibility 0.2s;
}
.sub-message-actions.is-visible {
  opacity: 1;
  visibility: visible;
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
.is-user .message-content {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary-dark-2);
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
