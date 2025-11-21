<!-- frontend/mambo/src/components/chat/ChatInputBox.vue -->
<template>
  <div class="chat-input-area" @keydown="handleGlobalKeydown">
    <MultiPartInput
      v-if="isMultiPartMode"
      ref="multiPartInputRef"
      :model-value="multiPartDraft"
      @update:model-value="val => $emit('update:multiPartDraft', val)"
      class="input-field"
      @send="$emit('send')"
    />
    <el-input
      v-else
      ref="inputRef"
      :model-value="singlePartDraft"
      @update:model-value="val => $emit('update:singlePartDraft', val)"
      type="textarea"
      :autosize="false"
      resize="none"
      placeholder="输入消息... (Shift + Enter 换行)"
      :disabled="isGenerating"
      @keydown="handleSingleInputKeydown"
      class="input-field"
    />
    <el-button
      v-if="!isGenerating"
      type="primary"
      class="action-button"
      :disabled="isSendButtonDisabled"
      @click="$emit('send')"
    >
      <el-icon><Promotion /></el-icon>
    </el-button>
    <el-button v-else type="warning" class="action-button" @click="$emit('stop-generation')">
      <el-icon><VideoPause /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { PropType } from 'vue';
import { ElInput } from 'element-plus';
import { Promotion, VideoPause } from '@element-plus/icons-vue';
import MultiPartInput from './MultiPartInput.vue';

interface Partition {
  id: number;
  content: string;
}

const props = defineProps({
  isMultiPartMode: {
    type: Boolean,
    required: true,
  },
  isGenerating: {
    type: Boolean,
    required: true,
  },
  isSendButtonDisabled: {
    type: Boolean,
    required: true,
  },
  singlePartDraft: {
    type: String,
    required: true,
  },
  multiPartDraft: {
    type: Array as PropType<Partition[]>,
    required: true,
  },
});

const emit = defineEmits<{
  (e: 'update:singlePartDraft', value: string): void;
  (e: 'update:multiPartDraft', value: Partition[]): void;
  (e: 'send'): void;
  (e: 'stop-generation'): void;
  (e: 'undo'): void;
  (e: 'redo'): void;
}>();

const inputRef = ref<InstanceType<typeof ElInput>>();
const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>();

/**
 * 处理全局键盘快捷键，如撤销和重做。
 * @param event - 键盘事件对象。
 */
function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    emit('undo');
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    emit('redo');
  }
}

/**
 * 处理单行输入模式下的键盘事件，主要用于拦截 Enter 键发送消息。
 * @param event - 键盘事件对象。
 */
function handleSingleInputKeydown(event: Event) {
  if (!(event instanceof KeyboardEvent)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    emit('send');
  }
}

/**
 * 将焦点设置到当前激活的输入框。
 */
const focus = () => {
  if (props.isMultiPartMode) {
    multiPartInputRef.value?.focus();
  } else {
    inputRef.value?.focus();
  }
};

// 使用 defineExpose 暴露 focus 方法给父组件
defineExpose({
  focus,
});
</script>

<style scoped>
.chat-input-area {
  flex-grow: 1;
  padding: 10px 20px;
  background-color: var(--color-background-soft);
  display: flex;
  align-items: stretch;
  min-height: 0;
}

.input-field {
  flex-grow: 1;
  margin-right: 10px;
}

.input-field:deep(.el-textarea__inner) {
  height: 100% !important;
}

.action-button {
  width: 54px;
  font-size: 20px;
  flex-shrink: 0;
  align-self: flex-end;
  height: calc(100% - 2px);
}
</style>
