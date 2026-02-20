<!-- frontend/mambo/src/mobile/components/chat/ChatInputBox.vue -->
<template>
  <div class="mobile-input-box">
    <div class="input-wrapper">
      <!--
        复用 ChatUniversalEditor 组件以保持功能一致性（Markdown、粘贴等）
        样式上这里调整为常规矩形样式
      -->
      <ChatUniversalEditor
        ref="editorRef"
        :model-value="modelValue"
        @update:model-value="$emit('update:modelValue', $event)"
        :monaco-options="mobileMonacoOptions"
        @submit="$emit('send')"
        @paste-file="(files) => $emit('files-pasted', files)"
      />
    </div>

    <el-button
      v-if="!isGenerating"
      type="primary"
      class="send-button"
      :disabled="isSendButtonDisabled"
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
import { ref, computed } from 'vue'
import { Promotion, VideoPause } from '@element-plus/icons-vue'
import ChatUniversalEditor from '@/components/common/ChatUniversalEditor.vue'
import type { editor } from 'monaco-editor'

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

defineEmits(['update:modelValue', 'send', 'stop-generation', 'files-pasted'])

const editorRef = ref()

const mobileMonacoOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  theme: 'vs',
  minimap: { enabled: false },
  lineNumbers: 'off',
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  folding: false,
  lineDecorationsWidth: 0,
  renderLineHighlight: 'none',
  scrollbar: {
    vertical: 'hidden',
    horizontal: 'hidden',
  },
  padding: { top: 10, bottom: 10 },
  fontSize: 16, // 移动端字体稍大
  fontFamily: 'var(--el-font-family)',
}))

const focus = () => {
  editorRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.mobile-input-box {
  display: flex;
  align-items: flex-end; /* 底部对齐 */
  padding: 10px 10px 10px 10px;
  background-color: var(--color-background-soft);
}

.input-wrapper {
  flex-grow: 1;
  border: 1px solid var(--el-border-color);
  border-radius: 4px; /* 恢复常规圆角 */
  overflow: hidden;
  background-color: #ffffff;
  margin-right: 10px;
  min-height: 40px;
  max-height: 120px;
  overflow-y: auto;
  /* 既然使用通用编辑器，确保内部编辑器高度适应 */
  display: flex;
  flex-direction: column;
}

.input-wrapper :deep(.monaco-editor) {
  min-height: 40px !important;
}

.send-button {
  width: 50px;
  height: 40px;
  border-radius: 4px; /* 常规圆角 */
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
</style>
