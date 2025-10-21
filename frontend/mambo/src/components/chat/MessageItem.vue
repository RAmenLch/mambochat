<!-- frontend/mambo/src/components/chat/MessageItem.vue -->
<template>
  <div
    class="message-item-container"
    :class="roleClass"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <div class="message-avatar">
      <el-avatar>
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <div class="message-body">
      <template v-if="isSingleSubMessage">
        <div class="single-sub-message-wrapper" :class="{ collapsed: isSingleViewCollapsed }">
          <SubMessageItem
            :sub-message="firstSubMessage"
            :parent-message="message"
            @edit="(payload) => handleEditRequest(firstSubMessage, payload)"
            @copy="handleCopy"
          />
        </div>
      </template>

      <template v-else>
        <div class="multi-part-container">
          <SubMessageItem
            v-for="(subMessage, index) in message.sub_messages"
            :key="subMessage.id"
            :sub-message="subMessage"
            :parent-message="message"
            :show-header="true"
            :index="index + 1"
            @edit="(payload) => handleEditRequest(subMessage, payload)"
            @copy="handleCopySingle(subMessage)"
          />
        </div>
      </template>

      <div class="message-actions" :class="{ 'is-visible': showActions && !isAnySubMessageGenerating }">
        <el-tooltip :content="message.role === 'user' ? '在下方重新回答' : '重新回答'" placement="top" :show-after="500">
          <el-button :icon="message.role === 'user' ? RefreshLeft : Refresh" circle size="small" @click="handleRegenerate" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" :content="isSingleViewCollapsed ? '展开' : '折叠'" placement="top" :show-after="500">
          <el-button :icon="isSingleViewCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleSingleViewCollapse" />
        </el-tooltip>

        <el-tooltip v-if="isSingleSubMessage" content="编辑" placement="top" :show-after="500">
          <!-- 这里也统一调用 handleEditRequest -->
          <el-button :icon="Edit" circle size="small" @click="handleEditRequest(firstSubMessage, { content: firstSubMessage.content })" />
        </el-tooltip>

        <el-tooltip :content="isSingleSubMessage ? '复制' : '全部复制'" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>

        <el-tooltip content="删除" placement="top" :show-after="500">
          <el-button :icon="Delete" circle size="small" type="danger" plain @click="handleDelete" />
        </el-tooltip>
      </div>
    </div>
  </div>

  <MessageEditDialog
    v-show="editDialogVisible"
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :is-user-message="message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { Message, SubMessage, SubMessageCreate, MessageStatus } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, Cpu, Refresh, RefreshLeft, Delete, Edit, CopyDocument, ArrowUpBold, ArrowDownBold } from '@element-plus/icons-vue';
import SubMessageItem from './SubMessageItem.vue';
import MessageEditDialog from './dialogs/MessageEditDialog.vue';
import { copyToClipboard } from '@/utils/clipboard';
import { parseMarkdown } from '@/utils/markdownParser';

const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
}>();

const chatStore = useChatStore();
const showActions = ref(false);

const isSingleSubMessage = computed(() => props.message.sub_messages.length <= 1);
const firstSubMessage = computed(() => props.message.sub_messages[0]);
const isAnySubMessageGenerating = computed(() => props.message.sub_messages.some(sm => sm.status === 'generating'));
const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));

const isSingleViewCollapsed = ref(firstSubMessage.value?.config?.is_collapsed || false);
watch(() => firstSubMessage.value?.config?.is_collapsed, (newValue) => {
  isSingleViewCollapsed.value = newValue || false;
});

function toggleSingleViewCollapse() {
  if (!firstSubMessage.value) return;
  const newCollapsedState = !isSingleViewCollapsed.value;
  isSingleViewCollapsed.value = newCollapsedState;
  chatStore.updateSubMessage({
    subMessageId: firstSubMessage.value.id,
    data: { config: { ...firstSubMessage.value.config, is_collapsed: newCollapsedState } },
  });
}

const editDialogVisible = ref(false);
const editingSubMessage = ref<SubMessage | null>(null);
const originalEditingContent = ref('');
const editingBlockIndex = ref<number | null>(null);

// 【关键修复】添加 watch 来处理对话框关闭后的清理工作
watch(editDialogVisible, (newValue) => {
  if (!newValue) {
    // 当对话框关闭时，重置状态，以便下次正确打开
    editingSubMessage.value = null;
    originalEditingContent.value = '';
    editingBlockIndex.value = null;
  }
});

function handleEditRequest(subMessage: SubMessage, payload: { content: string; blockIndex?: number }) {
  // 如果没有 subMessage 或者 payload，则不执行任何操作
  if (!subMessage || !payload) {
    console.error("handleEditRequest called with invalid arguments", { subMessage, payload });
    return;
  }

  editingSubMessage.value = subMessage;
  originalEditingContent.value = payload.content;
  editingBlockIndex.value = payload.blockIndex ?? null;
  editDialogVisible.value = true;
}

function replaceNthOccurrence(str: string, find: string, replace: string, n: number): string {
  let i = -1;
  while (n-- > 0) {
    i = str.indexOf(find, i + 1);
    if (i < 0) return str;
  }
  return str.substring(0, i) + replace + str.substring(i + find.length);
}

function getUpdatedFullContent(newPartialContent: string): string {
  if (!editingSubMessage.value) return '';

  const fullOriginalContent = editingSubMessage.value.content;
  const partialOriginalContent = originalEditingContent.value;
  const blockIndex = editingBlockIndex.value;

  if (blockIndex === null || partialOriginalContent === fullOriginalContent) {
    return newPartialContent;
  }

  const originalBlocks = parseMarkdown(fullOriginalContent);
  let occurrence = 0;
  if (blockIndex < originalBlocks.length && originalBlocks[blockIndex].content === partialOriginalContent) {
    for (let i = 0; i < blockIndex; i++) {
      if (originalBlocks[i].content === partialOriginalContent) {
        occurrence++;
      }
    }
  } else {
    // Fallback if something is inconsistent
    return fullOriginalContent.replace(partialOriginalContent, newPartialContent);
  }

  return replaceNthOccurrence(fullOriginalContent, partialOriginalContent, newPartialContent, occurrence + 1);
}

function handleSaveEdit(newContent: string) {
  if (!editingSubMessage.value) return;
  const updatedContent = getUpdatedFullContent(newContent);
  chatStore.updateSubMessage({
    subMessageId: editingSubMessage.value.id,
    data: { content: updatedContent },
  });
}

function handleSaveAndResend(newContent: string) {
  if (!editingSubMessage.value) return;

  const updatedContent = getUpdatedFullContent(newContent);

  const newSubMessages: SubMessageCreate[] = props.message.sub_messages.map(sm => {
    return {
      content: sm.id === editingSubMessage.value!.id ? updatedContent : sm.content,
      sortOrder: sm.sortOrder,
      type: sm.type,
      config: sm.config,
      status: 'completed' as MessageStatus,
    };
  });

  chatStore.editMessageAndRegenerate({
    messageId: props.message.id,
    sub_messages: newSubMessages,
    resend: true,
  });
}

function handleRegenerate() {
  chatStore.regenerateFrom(props.message.id);
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除这条消息吗？（包含所有分区）', '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    });
    await chatStore.deleteMessage(props.message.id);
  } catch { /* User canceled */ }
}

async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content);
    ElMessage.success('已复制到剪贴板');
  } catch { ElMessage.error('复制失败'); }
}

async function handleCopy() {
  const contentToCopy = (isSingleSubMessage.value && firstSubMessage.value)
    ? firstSubMessage.value.content || ''
    : props.message.sub_messages.map(sm => sm.content).join('\n--------------------------\n');
  try {
    await copyToClipboard(contentToCopy);
    ElMessage.success('已复制到剪贴板');
  } catch { ElMessage.error('复制失败'); }
}
</script>


<style scoped>
.message-item-container { display: flex; align-items: flex-start; margin-bottom: 20px; max-width: 90%; }
.message-avatar { flex-shrink: 0; margin-right: 12px; margin-top: 2px; }
.message-body { display: flex; flex-direction: column; min-width: 80px; width: 100%; }
.single-sub-message-wrapper { padding: 10px 15px; border-radius: 8px; background-color: var(--color-background-soft); min-height: 40px; transition: max-height 0.25s ease-out; overflow: hidden; position: relative; }
.is-user .single-sub-message-wrapper { background-color: var(--el-color-primary-light-9); }
.single-sub-message-wrapper :deep(.sub-message-item) { border: none; background-color: transparent; overflow: visible; }
.single-sub-message-wrapper :deep(.message-content) { padding: 0; max-height: none; }
.single-sub-message-wrapper :deep(.message-content)::after { display: none; }
.single-sub-message-wrapper.collapsed { max-height: 5em; }
.single-sub-message-wrapper.collapsed::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3em; background: linear-gradient(to bottom, transparent, var(--color-background-soft)); pointer-events: none; }
.is-user .single-sub-message-wrapper.collapsed::after { background: linear-gradient(to bottom, transparent, var(--el-color-primary-light-9)); }
.multi-part-container { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.message-actions { display: flex; gap: 4px; margin-top: 8px; opacity: 0; visibility: hidden; height: 24px; transition: opacity 0.2s, visibility 0.2s; }
.message-actions.is-visible { opacity: 1; visibility: visible; }
.message-item-container.is-user { flex-direction: row-reverse; margin-left: auto; }
.is-user .message-avatar { margin-right: 0; margin-left: 12px; }
.is-user .single-sub-message-wrapper, .is-user .multi-part-container { margin-left: auto; }
.is-user .message-actions { justify-content: flex-end; }
</style>
