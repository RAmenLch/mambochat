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
      <!--
        [适配变更]
        使用 UniversalEditor 替代直接使用 MonacoEditor。
        UniversalEditor 内部根据全局配置决定渲染 Monaco 还是普通 Textarea，
        并统一处理快捷键逻辑。
      -->
      <UniversalEditor
        ref="universalEditorRef"
        :model-value="singlePartDraft"
        @update:model-value="(val) => $emit('update:singlePartDraft', val)"
        :monaco-options="monacoOptions"
        @submit="$emit('send')"
        @paste-file="(files) => $emit('files-pasted', files)"
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
import UniversalEditor from '@/components/common/UniversalEditor.vue'

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
const universalEditorRef = ref<InstanceType<typeof UniversalEditor>>()

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
  // Monaco 内部只控制上下 padding，左右 padding 由外部容器控制
  padding: { top: 12, bottom: 12 },
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
}))

/**
 * 处理外层容器的粘贴事件。
 * 1. 当使用 MultiPartInput 时，此函数处理粘贴。
 * 2. 当焦点不在编辑器内部（例如点击了输入框边缘的 padding 区域）时，此函数作为后备处理。
 */
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
  // 仅处理 MultiPartInput 的自定义撤销/重做逻辑
  // 单输入框模式下的撤销/重做由编辑器原生支持
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
  /* 恢复左右 padding，Monaco Editor 需要这个来保持左右间距 */
  padding: 0 12px;
  height: 100%;
}

/*
  适配 UniversalEditor 内部 el-input 的样式。
  外层已设置左右 padding，这里只需设置上下 padding，并去除左右 padding 以免双重缩进。
  Monaco Editor 的上下 padding 由 options 控制，左右由 .editor-wrapper 控制。
*/
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
</style>
