<!-- frontend/mambo/src/components/common/ResourceUniversalEditor.vue -->
<template>
  <div class="universal-editor-container">
    <template v-if="isMonacoMode">
      <MonacoEditor
        :model-value="modelValue"
        :language="language"
        :options="computedMonacoOptions"
        :allow-file-paste="false"
        @update:model-value="handleUpdateValue"
        @editor-mounted="handleMonacoMounted"
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
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settingsStore'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
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
  (e: 'editor-mounted', instance: editor.IStandaloneCodeEditor): void
}>()

const { t } = useI18n()
const settingsStore = useSettingsStore()
const textareaRef = ref()
let monacoInstance: editor.IStandaloneCodeEditor | null = null

// --- Computed States ---

const isMonacoMode = computed(() => {
  return settingsStore.globalSettings.frontend_editor === 'monaco'
})

// 编辑模式下不需要监听快捷键配置，Enter 永远是换行
const computedMonacoOptions = computed(() => ({
  ...props.monacoOptions,
}))

// --- Event Handlers ---

const handleUpdateValue = (val: string) => {
  emit('update:modelValue', val)
}

// --- Monaco Logic ---

const handleMonacoMounted = async (instance: editor.IStandaloneCodeEditor) => {
  monacoInstance = instance
  emit('editor-mounted', instance)
  // 编辑模式不需要绑定发送快捷键
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
  box-shadow: none;
  border: 1px solid var(--el-border-color);
}

:deep(.simple-textarea .el-textarea__inner:focus) {
  border-color: var(--el-color-primary);
}
</style>
