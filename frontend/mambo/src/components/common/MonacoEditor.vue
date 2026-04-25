<!-- frontend/mambo/src/components/common/MonacoEditor.vue -->
<template>
  <div ref="editorContainer" class="monaco-editor-container" @contextmenu="handleContextMenu">
    <!-- 自定义右键菜单 -->
    <div
      v-if="menuVisible"
      class="custom-context-menu"
      :style="{ top: `${menuY}px`, left: `${menuX}px` }"
      @mousedown.stop
    >
      <div class="menu-item" @click="handleCut">
        <span class="label">{{ t('common.action.cut') }}</span>
        <span class="shortcut">Ctrl+X</span>
      </div>
      <div class="menu-item" @click="handleCopy">
        <span class="label">{{ t('common.action.copy') }}</span>
        <span class="shortcut">Ctrl+C</span>
      </div>
      <div class="menu-item" @click="handlePaste">
        <span class="label">{{ t('common.action.paste') }}</span>
        <span class="shortcut">Ctrl+V</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import loader from '@monaco-editor/loader'
import type { editor, IRange } from 'monaco-editor'
import { ElMessage } from 'element-plus'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: string
    options?: editor.IStandaloneEditorConstructionOptions
    allowFilePaste?: boolean
  }>(),
  {
    language: 'markdown',
    options: () => ({}),
    allowFilePaste: true,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit'): void
  (e: 'editor-mounted', editorInstance: editor.IStandaloneCodeEditor): void
  (e: 'paste-file', files: FileList): void
}>()

const { t } = useI18n()
const editorContainer = ref<HTMLElement | null>(null)
let editorInstance: editor.IStandaloneCodeEditor | null = null
let resizeObserver: ResizeObserver | null = null

// --- 自定义菜单状态 ---
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)

loader.config({ paths: { vs: '/monaco-editor/vs' } })

// --- 剪贴板操作逻辑 ---

const getSelection = (): { text: string; range: IRange } | null => {
  if (!editorInstance) return null
  const selection = editorInstance.getSelection()
  if (!selection || selection.isEmpty()) return null
  const model = editorInstance.getModel()
  if (!model) return null
  return {
    text: model.getValueInRange(selection),
    range: selection,
  }
}

const handleCopy = async () => {
  menuVisible.value = false
  const data = getSelection()
  if (data && data.text) {
    try {
      await navigator.clipboard.writeText(data.text)
      editorInstance?.focus()
    } catch (err) {
      console.error('Copy failed:', err)
    }
  }
}

const handleCut = async () => {
  menuVisible.value = false
  const data = getSelection()
  if (data && data.text) {
    try {
      await navigator.clipboard.writeText(data.text)
      editorInstance?.executeEdits('context-menu', [
        {
          range: data.range,
          text: '',
          forceMoveMarkers: true,
        },
      ])
      editorInstance?.focus()
    } catch (err) {
      console.error('Cut failed:', err)
    }
  }
}

/**
 * 右键菜单粘贴逻辑
 * 包含降级处理：read() 失败 -> readText() -> 提示用户使用 Ctrl+V
 */
const handlePaste = async () => {
  menuVisible.value = false

  if (!editorInstance) return

  editorInstance.focus()

  try {
    if (props.allowFilePaste && navigator.clipboard && navigator.clipboard.read) {
      const items = await navigator.clipboard.read()

      for (const item of items) {
        const imageType = item.types.find((t) => t.startsWith('image/'))
        if (imageType) {
          const blob = await item.getType(imageType)
          const file = new File([blob], `pasted_image.${imageType.split('/')[1]}`, {
            type: imageType,
          })

          const dt = new DataTransfer()
          dt.items.add(file)

          emit('paste-file', dt.files)
          return
        }
      }
    }

    throw new Error('No image found or file paste disabled, falling back to text')
  } catch (err) {
    try {
      const text = await navigator.clipboard.readText()

      if (text) {
        const selection = editorInstance.getSelection()
        if (selection) {
          editorInstance.executeEdits('context-menu', [
            {
              range: selection,
              text: text,
              forceMoveMarkers: true,
            },
          ])
        }
      } else if (props.allowFilePaste) {
        ElMessage.warning({
          message: t('editor.monaco.pasteFileError'),
          duration: 4000,
          showClose: true,
        })
      }
    } catch (textErr) {
      console.error('Clipboard access completely failed:', textErr)
      ElMessage.error(t('editor.monaco.clipboardError'))
    }
  }
}

// --- 事件处理 ---

const handleContextMenu = (e: MouseEvent) => {
  e.preventDefault()
  menuX.value = e.clientX
  menuY.value = e.clientY
  menuVisible.value = true
}

const closeMenu = () => {
  menuVisible.value = false
}

/**
 * DOM 粘贴事件监听 (Ctrl+V)
 * 保持 capture: true 以确保优先捕获
 */
const handleDomPaste = (event: ClipboardEvent) => {
  if (props.allowFilePaste && event.clipboardData && event.clipboardData.files.length > 0) {
    event.preventDefault()
    event.stopPropagation()
    emit('paste-file', event.clipboardData.files)
    menuVisible.value = false
  }
}

onMounted(async () => {
  if (!editorContainer.value) return

  window.addEventListener('click', closeMenu)
  editorContainer.value.addEventListener('paste', handleDomPaste, true)

  try {
    const monaco = await loader.init()

    const defaultOptions: editor.IStandaloneEditorConstructionOptions = {
      value: props.modelValue,
      language: props.language,
      theme: 'vs',
      automaticLayout: false,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      lineNumbers: 'off',
      renderLineHighlight: 'none',
      contextmenu: false,
      fixedOverflowWidgets: true,
      padding: { top: 10, bottom: 10 },
      ...props.options,
    }

    const instance = monaco.editor.create(editorContainer.value, defaultOptions)
    editorInstance = instance

    instance.onDidChangeModelContent(() => {
      const value = instance.getValue()
      if (value !== props.modelValue) {
        emit('update:modelValue', value)
      }
    })

    instance.onDidScrollChange(() => {
      menuVisible.value = false
    })

    resizeObserver = new ResizeObserver(() => {
      instance.layout()
    })
    resizeObserver.observe(editorContainer.value)

    emit('editor-mounted', instance)
  } catch (error) {
    console.error('Failed to initialize Monaco Editor:', error)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('click', closeMenu)
  if (editorContainer.value) {
    editorContainer.value.removeEventListener('paste', handleDomPaste, true)
  }
  if (resizeObserver) resizeObserver.disconnect()
  if (editorInstance) editorInstance.dispose()
})

watch(
  () => props.modelValue,
  (newValue) => {
    if (editorInstance && newValue !== editorInstance.getValue()) {
      editorInstance.setValue(newValue)
    }
  },
)

watch(
  () => props.language,
  (newLang) => {
    if (editorInstance) {
      const model = editorInstance.getModel()
      if (model) {
        const monaco = loader.__getMonacoInstance()
        if (monaco && newLang) {
          monaco.editor.setModelLanguage(model, newLang)
        }
      }
    }
  },
)

watch(
  () => props.options,
  (newOptions) => {
    if (editorInstance && newOptions) {
      editorInstance.updateOptions(newOptions)
    }
  },
  { deep: true },
)
</script>

<style scoped>
.monaco-editor-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: #ffffff;
  position: relative;
}

.custom-context-menu {
  position: fixed;
  z-index: 100002;
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 4px 0;
  min-width: 120px;
  font-size: 13px;
  color: var(--el-text-color-primary);
  user-select: none;
}

.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background-color 0.2s;
}

.menu-item:hover {
  background-color: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.menu-item .shortcut {
  margin-left: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
