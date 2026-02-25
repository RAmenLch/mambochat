<!-- frontend/mambo/src/mobile/components/chat/ChatInputBox.vue -->
<template>
  <div class="mobile-input-box">
    <div class="input-wrapper">
      <el-input
        ref="inputRef"
        :model-value="modelValue"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 12 }"
        :placeholder="t('common.placeholder.input')"
        resize="none"
        class="mobile-textarea"
        @input="$emit('update:modelValue', $event)"
        @paste="handlePaste"
        @keydown.enter="handleEnter"
      />
    </div>

    <el-button
      v-if="!isGenerating"
      type="primary"
      class="send-button"
      :disabled="isSendButtonDisabled || !modelValue.trim()"
      @click="$emit('send')"
    >
      <el-icon><Promotion /></el-icon>
    </el-button>
    <el-button v-else type="danger" class="send-button" @click="$emit('stop-generation')">
      <el-icon><VideoPause /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Promotion, VideoPause } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  isGenerating: {
    type: Boolean,
    default: false,
  },
  isSendButtonDisabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue', 'send', 'stop-generation', 'files-pasted'])

const { t } = useI18n()
const inputRef = ref()

const handlePaste = (event: ClipboardEvent) => {
  if (event.clipboardData && event.clipboardData.files.length > 0) {
    event.preventDefault()
    emit('files-pasted', event.clipboardData.files)
  }
}

// 修复: 适配 Element Plus 的事件类型定义
const handleEnter = (event: Event | KeyboardEvent) => {
  // 仅当是键盘事件且按下 Ctrl 键时触发
  if (event instanceof KeyboardEvent && event.ctrlKey) {
    event.preventDefault()
    if (!props.isSendButtonDisabled && props.modelValue.trim()) {
      emit('send')
    }
  }
}

const focus = () => {
  inputRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.mobile-input-box {
  display: flex;
  align-items: flex-end;
  padding: 8px 10px;
  background-color: var(--color-background-soft);
  border-top: 1px solid var(--color-border-light);
  gap: 8px;
}

.input-wrapper {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.mobile-textarea {
  width: 100%;
}

:deep(.el-textarea__inner) {
  /* 最大高度限制为屏幕的 1/4 */
  max-height: 25vh !important;

  /* 字体大小 14px */
  font-size: 14px !important;
  line-height: 1.5;

  /* 修改点：改为微圆角 (4px) */
  border-radius: 4px;

  padding: 8px 12px;
  box-shadow: none;
  border: 1px solid var(--el-border-color);
  background-color: #ffffff;
}

:deep(.el-textarea__inner:focus) {
  border-color: var(--el-color-primary);
}

/* 滚动条样式 */
:deep(.el-textarea__inner::-webkit-scrollbar) {
  width: 4px;
}
:deep(.el-textarea__inner::-webkit-scrollbar-thumb) {
  background-color: var(--el-text-color-placeholder);
  border-radius: 2px;
}

.send-button {
  width: 40px;
  height: 36px;
  /* 修改点：按钮也改为微圆角，与输入框保持一致 */
  border-radius: 4px;
  padding: 0;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  margin-bottom: 1px;
}
</style>
