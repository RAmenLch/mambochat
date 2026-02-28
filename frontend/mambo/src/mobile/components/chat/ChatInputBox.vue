<!-- frontend/mambo/src/mobile/components/chat/ChatInputBox.vue -->
<template>
  <div class="mobile-input-box">
    <div class="input-wrapper">
      <el-input
        ref="inputRef"
        :model-value="modelValue"
        type="textarea"
        :autosize="false"
        :placeholder="t('common.placeholder.input')"
        resize="none"
        class="mobile-textarea"
        @input="handleInput"
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
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
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

// 核心优化：手动计算高度
const adjustTextareaHeight = () => {
  nextTick(() => {
    const textarea = inputRef.value?.textarea
    if (!textarea) return

    // 1. 先将高度设为 auto，以便准确获取 scrollHeight (内容实际高度)
    // 这一步会让输入框瞬间收缩再展开，但在真机上速度极快，用户感知不到
    textarea.style.height = 'auto'

    // 2. 获取当前内容所需的高度
    const scrollHeight = textarea.scrollHeight

    // 3. 计算最大高度限制 (屏幕高度的 25%)
    const maxHeight = window.innerHeight * 0.25

    // 4. 设定最小高度 (对应 minRows: 2)
    // 14px(font-size) * 1.5(line-height) * 2(rows) + 16px(padding top/bottom) = 58px
    const minHeight = 58

    // 5. 计算最终高度
    let targetHeight = scrollHeight
    if (targetHeight < minHeight) {
      targetHeight = minHeight
    }

    // 6. 应用高度并处理滚动条
    if (targetHeight > maxHeight) {
      textarea.style.height = `${maxHeight}px`
      // 达到最大高度，允许滚动
      textarea.style.overflowY = 'auto'
    } else {
      textarea.style.height = `${targetHeight}px`
      // 未达最大高度，强制隐藏滚动条，防止计算误差导致的滚动条闪烁
      textarea.style.overflowY = 'hidden'
    }
  })
}

// 监听内容变化，触发高度调整
watch(
  () => props.modelValue,
  () => {
    adjustTextareaHeight()
  }
)

// 组件挂载和窗口大小变化时调整
onMounted(() => {
  adjustTextareaHeight()
  window.addEventListener('resize', adjustTextareaHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', adjustTextareaHeight)
})

const handleInput = (value: string) => {
  emit('update:modelValue', value)
  // 虽然 watch 会触发，但在 input 事件中显式调用可以更灵敏
  adjustTextareaHeight()
}

const handlePaste = (event: ClipboardEvent) => {
  if (event.clipboardData && event.clipboardData.files.length > 0) {
    event.preventDefault()
    emit('files-pasted', event.clipboardData.files)
  }
  // 粘贴文本后也会触发 watch，无需额外调用 adjust
}

const handleEnter = (event: Event | KeyboardEvent) => {
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
  border-top: 1px solid var(--el-border-color-lighter);
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

  /* 核心修正：设置最小高度，对应 minRows: 2 */
  /* 计算：14px * 1.5 * 2 + 16px padding = 58px */
  min-height: 58px;

  /* 字体大小 14px */
  font-size: 14px !important;
  line-height: 1.5;

  /* 修改点：改为微圆角 (4px) */
  border-radius: 4px;

  padding: 8px 12px;
  box-shadow: none;
  border: 1px solid var(--el-border-color);
  background-color: #ffffff;

  /* 默认隐藏滚动条，由 JS 控制何时显示 */
  overflow-y: hidden;
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
