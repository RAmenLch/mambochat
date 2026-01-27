<!-- frontend/mambo/src/components/chat/ChatInputBox.vue -->
<template>
  <div class="chat-input-area" @keydown="handleGlobalKeydown" @paste="handlePaste">
    <MultiPartInput
      v-if="isMultiPartMode"
      ref="multiPartInputRef"
      :model-value="multiPartDraft"
      :active-index="activePartitionIndex"
      @update:model-value="(val) => $emit('update:multiPartDraft', val)"
      @update:active-index="(val) => $emit('update:activePartitionIndex', val)"
      class="input-field"
      @send="$emit('send')"
    />
    <div v-else class="input-field monaco-wrapper">
      <MonacoEditor
        :model-value="singlePartDraft"
        @update:model-value="(val) => $emit('update:singlePartDraft', val)"
        language="markdown"
        :options="monacoOptions"
        @submit="$emit('send')"
        @editor-mounted="handleEditorMounted"
      />
    </div>
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
import { ref, computed } from 'vue'
import type { PropType } from 'vue'
import { Promotion, VideoPause } from '@element-plus/icons-vue'
import type { editor } from 'monaco-editor'
import MultiPartInput from './MultiPartInput.vue'
import MonacoEditor from '@/components/common/MonacoEditor.vue'

interface Partition {
  id: number
  content: string
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
  activePartitionIndex: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits<{
  (e: 'update:singlePartDraft', value: string): void
  (e: 'update:multiPartDraft', value: Partition[]): void
  (e: 'update:activePartitionIndex', value: number): void
  (e: 'send'): void
  (e: 'stop-generation'): void
  (e: 'undo'): void
  (e: 'redo'): void
  (e: 'files-pasted', files: FileList): void
}>()

const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>()
// 保存 Monaco Editor 实例引用，用于控制焦点
let editorInstance: editor.IStandaloneCodeEditor | null = null

// Monaco Editor 配置项
const monacoOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  theme: 'vs',
  minimap: { enabled: false },
  lineNumbers: 'off',
  wordWrap: 'on',
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  scrollBeyondLastLine: false,
  folding: false,
  glyphMargin: false,
  lineDecorationsWidth: 0,
  lineNumbersMinChars: 0,
  renderLineHighlight: 'none',
  scrollbar: {
    vertical: 'auto',
    horizontal: 'hidden',
  },
  padding: { top: 12, bottom: 12 },
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
}))

/**
 * 处理粘贴事件，用于捕获粘贴的文件。
 * @param event - 剪贴板事件对象。
 */
function handlePaste(event: ClipboardEvent) {
  if (!event.clipboardData) return

  const files = event.clipboardData.files
  if (files && files.length > 0) {
    // 阻止默认的粘贴行为（例如，将文件名作为文本粘贴）
    event.preventDefault()
    emit('files-pasted', files)
  }
}

/**
 * 处理全局键盘快捷键，如撤销和重做。
 * 注意：Monaco Editor 内部有自己的 Undo/Redo 栈，当焦点在编辑器内时，
 * 这里的事件可能会被 Monaco 拦截或作为补充。
 * @param event - 键盘事件对象。
 */
function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
    // 如果焦点不在 Monaco 内，或者是多分区模式，触发外部 Undo
    if (props.isMultiPartMode) {
      event.preventDefault()
      emit('undo')
    }
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
    if (props.isMultiPartMode) {
      event.preventDefault()
      emit('redo')
    }
  }
}

/**
 * Monaco Editor 挂载完成后的回调
 */
function handleEditorMounted(instance: editor.IStandaloneCodeEditor) {
  editorInstance = instance
}

/**
 * 将焦点设置到当前激活的输入框。
 */
const focus = () => {
  if (props.isMultiPartMode) {
    multiPartInputRef.value?.focus()
  } else {
    editorInstance?.focus()
  }
}

// 使用 defineExpose 暴露 focus 方法给父组件
defineExpose({
  focus,
})
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
  /* 确保 Monaco Editor 容器占满可用空间 */
  min-height: 0;
}

.monaco-wrapper {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  background-color: #ffffff;
  padding: 0 12px;
  height: 100%;
}

.action-button {
  width: 54px;
  font-size: 20px;
  flex-shrink: 0;
  align-self: flex-end;
  height: calc(100% - 2px);
}
</style>
