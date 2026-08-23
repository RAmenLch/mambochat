<!-- frontend/mambo/src/mobile/components/chat/ChatInputBox.vue -->
<template>
  <div class="mobile-input-box">
    <div class="input-row">
      <button
        class="attach-btn"
        @click="$emit('trigger-file-upload')"
      >
        <el-icon :size="22"><Plus /></el-icon>
      </button>

      <div class="input-wrapper">
        <textarea
          ref="textareaRef"
          :value="modelValue"
          :placeholder="t('common.placeholder.input')"
          rows="1"
          class="chat-textarea"
          @input="handleInput"
          @paste="handlePaste"
        ></textarea>
      </div>

      <button
        v-if="!isGenerating"
        class="send-btn"
        :class="{ 'has-content': modelValue.trim() }"
        :disabled="isSendButtonDisabled || !modelValue.trim()"
        @click="$emit('send')"
      >
        <el-icon :size="18"><Promotion /></el-icon>
      </button>
      <button
        v-else
        class="stop-btn"
        @click="$emit('stop-generation')"
      >
        <el-icon :size="18"><VideoPause /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { Promotion, VideoPause, Plus } from '@element-plus/icons-vue'
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

const emit = defineEmits(['update:modelValue', 'send', 'stop-generation', 'files-pasted', 'trigger-file-upload', 'open-resource-selector'])

const { t } = useI18n()
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  const maxH = window.innerHeight * 0.25
  el.style.height = Math.min(el.scrollHeight, maxH) + 'px'
  el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden'
}

function handleInput(e: Event) {
  const target = e.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
  autoResize()
}

function handlePaste(event: ClipboardEvent) {
  if (event.clipboardData && event.clipboardData.files.length > 0) {
    event.preventDefault()
    emit('files-pasted', event.clipboardData.files)
  }
}

function focus() {
  textareaRef.value?.focus()
}

defineExpose({ focus })

watch(() => props.modelValue, () => {
  nextTick(() => autoResize())
})

onMounted(() => {
  nextTick(() => autoResize())
})
</script>

<style scoped>
.mobile-input-box {
  padding: 8px 10px;
  padding-bottom: max(8px, env(safe-area-inset-bottom));
  background: var(--color-background);
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--el-fill-color-light);
  border-radius: 22px;
  padding: 4px;
  border: 1px solid var(--el-border-color-lighter);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-row:focus-within {
  border-color: var(--el-color-primary-light-3);
  box-shadow: 0 0 0 2px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.12);
}

.attach-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.15s, color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.attach-btn:active {
  background-color: rgba(0, 0, 0, 0.06);
  color: var(--el-color-primary);
}

.input-wrapper {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.chat-textarea {
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  line-height: 1.4;
  color: var(--el-text-color-primary);
  resize: none;
  padding: 5px 0;
  max-height: 25vh;
  min-height: 24px;
  font-family: inherit;
  word-break: break-word;
  overflow-y: hidden;
}

.chat-textarea::placeholder {
  color: var(--el-text-color-placeholder);
}

.send-btn,
.stop-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s;
  -webkit-tap-highlight-color: transparent;
}

.send-btn {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary-light-3);
}

.send-btn.has-content {
  background: var(--el-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.35);
}

.send-btn:active {
  transform: scale(0.92);
}

.stop-btn {
  background: var(--el-color-danger);
  color: #fff;
  box-shadow: 0 2px 8px rgba(245, 108, 108, 0.35);
}

.stop-btn:active {
  transform: scale(0.92);
}

@media (prefers-color-scheme: dark) {
  .input-row {
    background: rgba(255, 255, 255, 0.06);
  }

  .attach-btn:active {
    background-color: rgba(255, 255, 255, 0.08);
  }
}
</style>
