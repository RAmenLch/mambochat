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
        :placeholder="t('common.placeholder.input')"
        @input="handleUpdateValue"
        @keydown="handleTextareaKeydown"
        @paste="handleTextareaPaste"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
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
    enableShortcuts?: boolean
  }>(),
  {
    language: 'markdown',
    minRows: 3,
    maxRows: 10,
    monacoOptions: () => ({}),
    enableShortcuts: true,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit'): void
  (e: 'paste-file', files: FileList): void
  (e: 'editor-mounted', instance: editor.IStandaloneCodeEditor): void
}>()

const { t } = useI18n()
const settingsStore = useSettingsStore()
const textareaRef = ref()
let monacoInstance: editor.IStandaloneCodeEditor | null = null
let sendOnEnterContextKey: editor.IContextKey<boolean> | null = null

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

  if (props.enableShortcuts) {
    await setupMonacoShortcuts(instance)
  }
}

/**
 * 配置 Monaco 的快捷键
 * 使用 ContextKey 和 addAction 来实现动态切换 Enter 键的行为
 */
const setupMonacoShortcuts = async (instance: editor.IStandaloneCodeEditor) => {
  const monaco = await loader.init()

  // 1. 创建 Context Key，用于动态控制 Enter 键是否触发发送
  sendOnEnterContextKey = instance.createContextKey('isSendOnEnter', shortcutMode.value === 'enter')

  // 2. 绑定 Enter 键 (带条件)
  // 仅当 'isSendOnEnter' 为 true 且没有建议框/重命名框时触发
  instance.addAction({
    id: 'chat-send-message-enter',
    label: t('chat.input.send'),
    keybindings: [monaco.KeyCode.Enter],
    precondition: 'isSendOnEnter && !suggestWidgetVisible && !renameInputVisible',
    run: () => {
      handleSubmit()
    },
  })

  // 3. 绑定 Ctrl+Enter (始终触发)
  instance.addAction({
    id: 'chat-send-message-ctrl-enter',
    label: t('chat.input.send'),
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
    run: () => {
      handleSubmit()
    },
  })
}

// 监听快捷键配置变化，动态更新 Context Key
watch(shortcutMode, (newMode) => {
  if (sendOnEnterContextKey) {
    sendOnEnterContextKey.set(newMode === 'enter')
  }
})

// --- Textarea Logic ---

const handleTextareaKeydown = (evt: Event) => {
  const e = evt as KeyboardEvent

  if (!props.enableShortcuts) return
  if (e.isComposing) return

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
