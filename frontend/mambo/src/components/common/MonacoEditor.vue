<template>
  <div ref="editorContainer" class="monaco-editor-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import loader from '@monaco-editor/loader'
import type { editor } from 'monaco-editor'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: string
    options?: editor.IStandaloneEditorConstructionOptions
  }>(),
  {
    language: 'markdown',
    options: () => ({}),
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit'): void
  (e: 'editor-mounted', editorInstance: editor.IStandaloneCodeEditor): void
}>()

const editorContainer = ref<HTMLElement | null>(null)
let editorInstance: editor.IStandaloneCodeEditor | null = null
let resizeObserver: ResizeObserver | null = null

// 配置本地资源路径
loader.config({ paths: { vs: '/monaco-editor/vs' } })

onMounted(async () => {
  if (!editorContainer.value) return

  try {
    const monaco = await loader.init()

    // 合并默认配置与用户配置
    const defaultOptions: editor.IStandaloneEditorConstructionOptions = {
      value: props.modelValue,
      language: props.language,
      theme: 'vs', // [修改] 默认改为亮色(白色)主题
      automaticLayout: false, // 手动控制 layout 以获得更好性能
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      lineNumbers: 'off',
      renderLineHighlight: 'none',
      contextmenu: true,
      fixedOverflowWidgets: true,
      padding: { top: 10, bottom: 10 }, // [修改] 默认增加上下内边距
      ...props.options,
    }

    // 使用局部变量 instance 以避免 TS 的 "possibly null" 检查报错
    const instance = monaco.editor.create(editorContainer.value, defaultOptions)
    editorInstance = instance

    // 监听内容变化
    instance.onDidChangeModelContent(() => {
      const value = instance.getValue()
      if (value !== props.modelValue) {
        emit('update:modelValue', value)
      }
    })

    // 注册快捷键: Ctrl + Enter / Command + Enter
    instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      emit('submit')
    })

    // 监听容器大小变化以触发 layout
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
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
  if (editorInstance) {
    editorInstance.dispose()
  }
})

// 监听 props 变化同步到编辑器
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
        if (monaco) {
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
  /* 确保容器背景也是白色，防止加载间隙闪烁 */
  background-color: #ffffff;
}
</style>
