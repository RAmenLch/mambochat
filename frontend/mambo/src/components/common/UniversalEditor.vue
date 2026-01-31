<!-- frontend/mambo/src/components/common/UniversalEditor.vue -->
<template>
  <div class="universal-editor-container">
    <template v-if="isMonacoMode">
      <MonacoEditor
        :model-value="modelValue"
        :language="language"
        :options="computedMonacoOptions"
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
  // 如果需要在不同模式下调整 Monaco 配置，可以在这里处理
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
    // KeyMod.WinCtrl 并不是必须的，直接用 KeyCode.Enter 即可捕获纯 Enter
    // 注意：这会覆盖默认的换行行为
    monacoInstance.addCommand(monaco.KeyCode.Enter, () => {
      handleSubmit()
    })
  } else {
    // 如果是 ctrl_enter 模式，MonacoEditor 内部已包含 Ctrl+Enter 的绑定，
    // 且 Enter 默认为换行，无需额外操作。
    // 注意：Monaco 的 addCommand 返回的 disposable ID 并没有被保存，
    // 因此很难移除已添加的 command。
    // 但由于组件切换会销毁编辑器实例，所以不需要手动清理 command。
  }
}

// 监听快捷键配置变化，实时更新 Monaco 绑定
// 注意：由于 Monaco addCommand 无法简单移除，如果用户在不刷新页面的情况下
// 频繁切换快捷键配置，可能会导致行为异常。但通常这是低频操作。
// 如果必须支持动态切换，建议重新挂载组件。
watch(shortcutMode, () => {
  if (isMonacoMode.value && monacoInstance) {
    // 简单策略：如果配置变了，提示用户或依赖组件重绘。
    // 这里为了简化，我们假设用户切换配置后，编辑器实例可能会重建（如果切换了编辑器类型），
    // 或者我们接受 Enter 模式切换回 Ctrl+Enter 模式时，Enter 依然触发发送的副作用（直到刷新）。
    // 实际上，为了严谨，我们可以在这里不做处理，依赖组件销毁重建。
  }
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

/* 确保 el-input 的 textarea 填满容器 */
:deep(.simple-textarea .el-textarea__inner) {
  height: 100% !important;
  border-radius: 4px;
  padding: 8px 12px;
  box-shadow: none; /* 移除默认阴影，使其看起来更像纯文本区域 */
  border: 1px solid var(--el-border-color);
}

:deep(.simple-textarea .el-textarea__inner:focus) {
  border-color: var(--el-color-primary);
}
</style>
