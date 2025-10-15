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

    <!-- 消息主体 (根据子消息数量进行条件渲染) -->
    <div class="message-body">
      <!-- 单一分区视图 -->
      <template v-if="isSingleSubMessage">
        <div class="single-sub-message-wrapper" :class="{ collapsed: isSingleViewCollapsed }">
          <SubMessageItem
            :sub-message="firstSubMessage"
            :parent-message="message"
            @edit="(content) => openEditDialog(firstSubMessage, content)"
            @copy="handleCopy"
          />
        </div>
      </template>

      <!-- 多分区视图 -->
      <template v-else>
        <div class="multi-part-container">
          <SubMessageItem
            v-for="(subMessage, index) in message.sub_messages"
            :key="subMessage.id"
            :sub-message="subMessage"
            :parent-message="message"
            :show-header="true"
            :index="index + 1"
            @edit="(content) => openEditDialog(subMessage, content)"
            @copy="handleCopySingle(subMessage)"
          />
        </div>
      </template>

      <!-- 悬浮操作菜单 (根据视图模式显示不同按钮) -->
      <div class="message-actions" :class="{ 'is-visible': showActions && !isAnySubMessageGenerating }">
        <!-- 通用: 重新回答 -->
        <el-tooltip :content="message.role === 'user' ? '在下方重新回答' : '重新回答'" placement="top" :show-after="500">
          <el-button :icon="message.role === 'user' ? RefreshLeft : Refresh" circle size="small" @click="handleRegenerate" />
        </el-tooltip>

        <!-- 单一视图: 折叠/展开 -->
        <el-tooltip v-if="isSingleSubMessage" :content="isSingleViewCollapsed ? '展开' : '折叠'" placement="top" :show-after="500">
          <el-button :icon="isSingleViewCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleSingleViewCollapse" />
        </el-tooltip>

        <!-- 单一视图: 编辑 -->
        <el-tooltip v-if="isSingleSubMessage" content="编辑" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="openEditDialog(firstSubMessage, firstSubMessage.content)" />
        </el-tooltip>

        <!-- 复制 (行为不同) -->
        <el-tooltip :content="isSingleSubMessage ? '复制' : '全部复制'" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>

        <!-- 通用: 删除 -->
        <el-tooltip content="删除" placement="top" :show-after="500">
          <el-button :icon="Delete" circle size="small" type="danger" plain @click="handleDelete" />
        </el-tooltip>
      </div>
    </div>
  </div>

  <!-- 编辑消息弹窗 (由MessageItem统一管理) -->
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
          v-if="message.role === 'user'"
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
import { computed, ref, watch } from 'vue';
import type { Message, SubMessage } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, Cpu, Refresh, RefreshLeft, Delete, Edit, CopyDocument, ArrowUpBold, ArrowDownBold } from '@element-plus/icons-vue';
import SubMessageItem from './SubMessageItem.vue';

const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
}>();

const chatStore = useChatStore();
const showActions = ref(false);

// --- 计算属性 ---
const isSingleSubMessage = computed(() => props.message.sub_messages.length <= 1);
const firstSubMessage = computed(() => props.message.sub_messages[0]);
const isAnySubMessageGenerating = computed(() => props.message.sub_messages.some(sm => sm.status === 'generating'));
const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));

// --- 单一视图折叠逻辑 ---
const isSingleViewCollapsed = ref(firstSubMessage.value?.config?.is_collapsed || false);
watch(() => firstSubMessage.value?.config?.is_collapsed, (newValue) => {
  isSingleViewCollapsed.value = newValue || false;
});

const toggleSingleViewCollapse = () => {
  if (!firstSubMessage.value) return;
  const newCollapsedState = !isSingleViewCollapsed.value;
  isSingleViewCollapsed.value = newCollapsedState;
  chatStore.updateSubMessage({
    subMessageId: firstSubMessage.value.id,
    data: {
      config: { ...firstSubMessage.value.config, is_collapsed: newCollapsedState },
    },
  });
};

// --- 编辑逻辑 (统一管理) ---
const editDialogVisible = ref(false);
const editingContent = ref('');
const originalEditingContent = ref('');
const editingSubMessage = ref<SubMessage | null>(null);

const openEditDialog = (subMessage: SubMessage, contentToEdit: string) => {
  editingSubMessage.value = subMessage;
  editingContent.value = contentToEdit;
  originalEditingContent.value = contentToEdit;
  editDialogVisible.value = true;
};

const getUpdatedFullContent = () => {
  if (!editingSubMessage.value) return '';
  const fullOriginalContent = editingSubMessage.value.content;
  const newContent = editingContent.value;
  // 如果原始编辑内容与完整内容相同，则直接替换；否则，进行字符串替换
  if (originalEditingContent.value === fullOriginalContent) {
    return newContent;
  }
  return fullOriginalContent.replace(originalEditingContent.value, newContent);
};

const handleSaveEdit = () => {
  if (!editingSubMessage.value || editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }
  const updatedContent = getUpdatedFullContent();
  chatStore.updateSubMessage({
    subMessageId: editingSubMessage.value.id,
    data: { content: updatedContent },
  });
  editDialogVisible.value = false;
};

const handleSaveAndResend = () => {
  if (!editingSubMessage.value || editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空');
    return;
  }
  const updatedContent = getUpdatedFullContent();
  const newSubMessages = props.message.sub_messages.map(sm => ({
    content: sm.id === editingSubMessage.value!.id ? updatedContent : sm.content,
    sortOrder: sm.sortOrder,
    type: sm.type,
    config: sm.config,
    status: sm.status,
  }));
  chatStore.editMessageAndRegenerate({
    messageId: props.message.id,
    sub_messages: newSubMessages,
    resend: true,
  });
  editDialogVisible.value = false;
};

// --- 其他操作 ---
const handleRegenerate = () => {
  chatStore.regenerateFrom(props.message.id);
};

const handleDelete = () => {
  ElMessageBox.confirm('确定要删除这条消息吗？（包含所有分区）', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => chatStore.deleteMessage(props.message.id))
    .catch(() => {});
};

const handleCopySingle = (subMessage: SubMessage) => {
  navigator.clipboard
    .writeText(subMessage.content)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'));
}

const handleCopy = () => {
  let contentToCopy = '';
  if (isSingleSubMessage.value) {
    contentToCopy = firstSubMessage.value?.content || '';
  } else {
    contentToCopy = props.message.sub_messages
      .map(sm => sm.content)
      .join('\n--------------------------\n');
  }
  navigator.clipboard
    .writeText(contentToCopy)
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'));
};
</script>

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
  width: 100%;
}

/* 单一分区包裹器 */
.single-sub-message-wrapper {
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  min-height: 40px;
  transition: max-height 0.25s ease-out;
  overflow: hidden;
  position: relative;
}
.is-user .single-sub-message-wrapper {
  background-color: var(--el-color-primary-light-9);
}
/* 移除 SubMessageItem 在单一视图下的边框和背景 */
.single-sub-message-wrapper :deep(.sub-message-item) {
  border: none;
  background-color: transparent;
  overflow: visible;
}
.single-sub-message-wrapper :deep(.message-content) {
  padding: 0;
  max-height: none; /* 让SubMessageItem的内容区不限制高度 */
}
.single-sub-message-wrapper :deep(.message-content)::after {
  display: none; /* 移除SubMessageItem内部的折叠遮罩 */
}

/* 单一分区折叠样式 */
.single-sub-message-wrapper.collapsed {
  max-height: 5em;
}
.single-sub-message-wrapper.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(to bottom, transparent, var(--color-background-soft));
  pointer-events: none;
}
.is-user .single-sub-message-wrapper.collapsed::after {
  background: linear-gradient(to bottom, transparent, var(--el-color-primary-light-9));
}

/* 多分区容器 */
.multi-part-container {
  display: flex;
  flex-direction: column;
  gap: 6px; /* 子消息之间的紧凑间距 */
  width: 100%;
}

.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
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
/* 核心修复：将 .is-user 选择器变得更具体，防止样式泄漏到子组件 */
.message-item-container.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}

/* 为了让用户消息整体靠右，我们对消息气泡本身进行对齐 */
.is-user .single-sub-message-wrapper,
.is-user .multi-part-container {
  margin-left: auto;
}

/* 确保用户消息的操作菜单也靠右对齐 */
.is-user .message-actions {
  justify-content: flex-end;
}
</style>
