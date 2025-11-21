<!-- frontend/mambo/src/components/chat/ChatHeader.vue -->
<template>
  <div class="chat-window-header">
    <div v-if="!isEditingTitle && currentChat" class="title-display-area">
      <h3 class="chat-title">{{ currentChat.name }}</h3>
      <div class="title-actions">
        <el-tooltip content="编辑标题" placement="bottom" :show-after="500">
          <el-button :icon="Edit" circle text @click="startTitleEdit" />
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
    <div v-else class="title-edit-area">
      <el-input
        ref="titleInputRef"
        v-model="titleInput"
        @blur="saveTitle"
        @keydown.enter.prevent="saveTitle"
        class="title-input"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue';
import type { ElInput } from 'element-plus';
import { Edit, Refresh } from '@element-plus/icons-vue';
import type { Chat } from '@/api/types';

const props = defineProps<{
  currentChat: Chat | null;
  isTitleRefreshing: boolean;
}>();

const emit = defineEmits<{
  (e: 'save-title', newTitle: string): void;
  (e: 'refresh-title'): void;
}>();

const isEditingTitle = ref(false);
const titleInput = ref('');
const titleInputRef = ref<InstanceType<typeof ElInput>>();

/**
 * 切换到标题编辑模式。
 */
function startTitleEdit() {
  if (!props.currentChat) return;
  isEditingTitle.value = true;
  titleInput.value = props.currentChat.name;
  nextTick(() => titleInputRef.value?.focus());
}

/**
 * 保存编辑后的标题。
 * 如果标题有变更，则触发 save-title 事件。
 */
function saveTitle() {
  if (!props.currentChat || !isEditingTitle.value) return;

  const newName = titleInput.value.trim();
  if (newName && newName !== props.currentChat.name) {
    emit('save-title', newName);
  }
  isEditingTitle.value = false;
}

/**
 * 触发标题刷新流程。
 */
function handleRefreshTitle() {
  emit('refresh-title');
}
</script>

<style scoped>
.chat-window-header {
  flex-shrink: 0;
  padding: 0 20px;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
}

.title-display-area {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  width: 100%;
}

.chat-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-heading);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-actions {
  display: flex;
  align-items: center;
}

.title-edit-area {
  width: 100%;
}
</style>
