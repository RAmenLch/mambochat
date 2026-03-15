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
      @paste="handlePaste"
    />
    <div v-else class="input-field editor-wrapper">
      <ChatUniversalEditor
        ref="universalEditorRef"
        :model-value="singlePartDraft"
        @update:model-value="(val) => $emit('update:singlePartDraft', val)"
        :monaco-options="monacoOptions"
        @submit="$emit('send')"
        @paste-file="(files) => $emit('files-pasted', files)"
      />
    </div>

    <el-button
      v-if="isPendingReview"
      type="warning"
      class="action-button review-button"
      @click="$emit('open-review')"
    >
      <el-icon><Warning /></el-icon>
    </el-button>
    <el-button
      v-else-if="!isGenerating"
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
import { Promotion, VideoPause, Warning } from '@element-plus/icons-vue'
import type { editor } from 'monaco-editor'
import MultiPartInput from './MultiPartInput.vue'
import ChatUniversalEditor from '@/components/common/ChatUniversalEditor.vue'

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
  isPendingReview: {
    type: Boolean,
    default: false,
  }
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
  (e: 'open-review'): void
}>()

const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>()
const universalEditorRef = ref<InstanceType<typeof ChatUniversalEditor>>()

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

function handlePaste(event: ClipboardEvent) {
  if (!event.clipboardData) return

  const files = event.clipboardData.files
  if (files && files.length > 0) {
    event.preventDefault()
    event.stopPropagation()
    emit('files-pasted', files)
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
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

const focus = () => {
  if (props.isMultiPartMode) {
    multiPartInputRef.value?.focus()
  } else {
    universalEditorRef.value?.focus()
  }
}

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
  min-height: 0;
}

.editor-wrapper {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
  padding: 0 12px;
  height: 100%;
}

.editor-wrapper :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 12px 0;
  background-color: transparent;
}

.action-button {
  width: 54px;
  font-size: 20px;
  flex-shrink: 0;
  align-self: flex-end;
  height: calc(100% - 2px);
}

.review-button {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
