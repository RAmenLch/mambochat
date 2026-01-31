<!-- frontend/mambo/src/components/common/ChatUniversalEditor.vue -->
<template>
  <div class="universal-editor-container">
    <template v-if="isMonacoMode">
      <MonacoEditor
        :model-value="modelValue"
        :language="language"
        :options="computedMonacoOptions"
        :allow-file-paste="true"
        @update:model-value="handleUpdateValue"
        @submit="handleSubmit"
        @editor-mounted="handleMonacoMounted"
        @paste-file="(files) => $emit('paste-file', files)"
      />
    </template>
    <template v-else>
      <el-input
        ref="textareaRef"
        type="textarea"
        :model-value="modelValue"
        :autosize="{ minRows, maxRows }"
        resize="none"
        class="simple-textarea"
        placeholder="请输入内容..."
        @input="handleUpdateValue"
        @keydown="handleTextareaKeydown"
        @paste="handleTextareaPaste"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import loader from '@monaco-editor/loader'
import type { editor } from 'monaco-editor'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: string
    minRows?: number
    maxRows?: number
    monacoOptions?: editor.IStandaloneEditorConstructionOptions
  }>(),
  {
    language: 'markdown',
    minRows: 3,
    maxRows: 10,
    monacoOptions: () => ({}),
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit'): void
  (e: 'paste-file', files: FileList): void
  (e: 'editor-mounted', instance: editor.IStandaloneCodeEditor): void
}>()

const settingsStore = useSettingsStore()
const textareaRef = ref()
let monacoInstance: editor.IStandaloneCodeEditor | null = null

// --- Computed States ---

const isMonacoMode = computed(() => {
  return settingsStore.globalSettings.frontend_editor === 'monaco'
})

const shortcutMode = computed(() => {
  return settingsStore.globalSettings.send_message_shortcut || 'enter'
})

const computedMonacoOptions = computed(() => ({
  ...props.monacoOptions,
}))

// --- Event Handlers ---

const handleUpdateValue = (val: string) => {
  emit('update:modelValue', val)
}

const handleSubmit = () => {
  emit('submit')
}

// --- Monaco Logic ---

const handleMonacoMounted = async (instance: editor.IStandaloneCodeEditor) => {
  monacoInstance = instance
  emit('editor-mounted', instance)
  await updateMonacoKeybindings()
}

/**
 * 根据快捷键配置更新 Monaco 的按键绑定
 */
const updateMonacoKeybindings = async () => {
  if (!monacoInstance) return

  const monaco = await loader.init()

  // MonacoEditor 组件内部默认绑定了 Ctrl+Enter 发送。
  // 这里我们需要根据配置决定是否添加 Enter 发送的绑定。
  if (shortcutMode.value === 'enter') {
    // 绑定 Enter 为发送
    monacoInstance.addCommand(monaco.KeyCode.Enter, () => {
      handleSubmit()
    })
  }
}

// 监听快捷键配置变化
watch(shortcutMode, () => {
  // 注意：Monaco 动态移除 command 比较复杂，通常依赖组件重绘更新
  // 如果需要严格支持动态切换，建议在上层通过 key 强制重新渲染组件
})

// --- Textarea Logic ---

const handleTextareaKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return // 输入法输入中不处理

  if (shortcutMode.value === 'enter') {
    // Enter 发送, Shift+Enter 换行
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault()
      handleSubmit()
    }
  } else {
    // Ctrl+Enter 发送, Enter 换行
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }
}

const handleTextareaPaste = (e: ClipboardEvent) => {
  if (e.clipboardData && e.clipboardData.files.length > 0) {
    e.preventDefault()
    emit('paste-file', e.clipboardData.files)
  }
}

// --- Expose ---

const focus = () => {
  if (isMonacoMode.value) {
    monacoInstance?.focus()
  } else {
    textareaRef.value?.focus()
  }
}

defineExpose({
  focus,
})
</script>

<style scoped>
.universal-editor-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.simple-textarea {
  font-family: var(--el-font-family);
  font-size: 14px;
  height: 100%;
}

:deep(.simple-textarea .el-textarea__inner) {
  height: 100% !important;
  border-radius: 4px;
  padding: 8px 12px;
  box-shadow: none;
  border: 1px solid var(--el-border-color);
}

:deep(.simple-textarea .el-textarea__inner:focus) {
  border-color: var(--el-color-primary);
}
</style>
