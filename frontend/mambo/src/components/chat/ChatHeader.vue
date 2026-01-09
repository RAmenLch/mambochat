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
import { Edit, Refresh, Expand } from '@element-plus/icons-vue';
import type { Chat } from '@/api/types';

const props = withDefaults(defineProps<{
  currentChat: Chat | null;
  isTitleRefreshing: boolean;
  mode?: 'horizontal' | 'vertical'; // 新增 mode 属性
}>(), {
  mode: 'horizontal'
});

const emit = defineEmits<{
  (e: 'save-title', newTitle: string): void;
  (e: 'refresh-title'): void;
  (e: 'expand'): void; // 新增 expand 事件
}>();

// --- State ---
const isEditingTitle = ref(false); // 仅用于横向模式
const isPopoverVisible = ref(false); // 仅用于竖向模式
const titleInput = ref('');

// Refs
const titleInputRef = ref<InstanceType<typeof ElInput>>();
const popoverInputRef = ref<InstanceType<typeof ElInput>>();

// --- Actions ---

/**
 * [Horizontal] 切换到行内编辑模式
 */
function startHorizontalEdit() {
  if (!props.currentChat) return;
  isEditingTitle.value = true;
  titleInput.value = props.currentChat.name;
  nextTick(() => titleInputRef.value?.focus());
}

/**
 * [Vertical] 初始化 Popover 输入框
 */
function initPopoverInput() {
  if (!props.currentChat) return;
  titleInput.value = props.currentChat.name;
  nextTick(() => popoverInputRef.value?.focus());
}

/**
 * 保存标题 (通用)
 */
function saveTitle() {
  if (!props.currentChat) return;

  const newName = titleInput.value.trim();
  if (newName && newName !== props.currentChat.name) {
    emit('save-title', newName);
  }

  // Reset states
  isEditingTitle.value = false;
  isPopoverVisible.value = false;
}

function handleRefreshTitle() {
  emit('refresh-title');
}

// Watchers ensure input sync if chat changes while editing
watch(() => props.currentChat?.id, () => {
  isEditingTitle.value = false;
  isPopoverVisible.value = false;
});
</script>

<style scoped>
.chat-header-container {
  box-sizing: border-box;
  background-color: var(--color-background); /* 确保背景一致 */
}

/* --- Horizontal Mode Styles --- */
.mode-horizontal {
  flex-shrink: 0;
  padding: 0 20px;
  height: 60px;
  display: flex;
  justify-content: space-between;
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
  justify-content: center;
  overflow: hidden;
  width: 100%;
}

.vertical-title-wrapper {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* 增加字间距优化竖排阅读体验 */
  letter-spacing: 2px;
  display: flex;
  align-items: center; /* 在竖排模式下，align-items center 实际上是水平居中 */
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
  margin-left: 0 !important; /* Override Element Plus default margins */
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
