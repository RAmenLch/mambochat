<!-- frontend/mambo/src/components/chat/MultiPartInput.vue -->
<template>
  <div class="multi-part-input-container">
    <div class="partition-sidebar">
      <el-scrollbar>
        <div
          v-for="(part, index) in localPartitions"
          :key="part.id"
          class="partition-tab"
          :class="{ 'is-active': activeIndex === index }"
          @click="selectPartition(index)"
        >
          <span class="tab-index">{{ index + 1 }}</span>
          <el-icon class="close-icon" @click.stop="removePartition(index)"><Close /></el-icon>
        </div>
      </el-scrollbar>
      <div class="add-partition">
        <el-button :icon="Plus" circle size="small" @click="addPartition" title="添加分区" />
      </div>
    </div>
    <div class="partition-editor">
      <!-- 确保在 localPartitions 可用时才渲染编辑器 -->
      <div v-if="localPartitions.length > 0 && localPartitions[activeIndex]" class="monaco-wrapper">
        <MonacoEditor
          v-model="localPartitions[activeIndex].content"
          language="markdown"
          :options="editorOptions"
          @submit="$emit('send')"
          @editor-mounted="handleEditorMounted"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { Plus, Close } from '@element-plus/icons-vue'
import type { SubMessageCreate } from '@/api/types'
import type { editor } from 'monaco-editor'
import MonacoEditor from '@/components/common/MonacoEditor.vue'

// 分区对象的本地UI表示
interface Partition {
  id: number
  content: string
}

// 接收 modelValue prop (用于 v-model)
const props = defineProps<{
  modelValue: Partition[]
  activeIndex: number
}>()

// 定义组件可发出的事件
const emit = defineEmits<{
  (e: 'update:modelValue', value: Partition[]): void
  (e: 'update:activeIndex', index: number): void
  (e: 'send'): void
}>()

const localPartitions = ref<Partition[]>([])
let editorInstance: editor.IStandaloneCodeEditor | null = null

// Monaco Editor 配置
const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  minimap: { enabled: false },
  lineNumbers: 'off',
  folding: false,
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  renderLineHighlight: 'none',
  scrollbar: {
    vertical: 'auto',
    horizontal: 'hidden',
  },
  padding: { top: 8, bottom: 8 },
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
}))

// --- 数据同步 ---

// 1. 从父组件(prop)到本地状态的单向同步
watch(
  () => props.modelValue,
  (newVal) => {
    if (JSON.stringify(newVal) !== JSON.stringify(localPartitions.value)) {
      const partitionsToSet =
        newVal && newVal.length > 0 ? newVal : [{ id: Date.now(), content: '' }]
      localPartitions.value = JSON.parse(JSON.stringify(partitionsToSet))
    }
  },
  { deep: true, immediate: true },
)

// 2. 从本地状态到父组件(emit)的单向同步
watch(
  localPartitions,
  (newVal) => {
    emit('update:modelValue', newVal)
  },
  { deep: true },
)

// --- UI 交互方法 ---

const handleEditorMounted = (instance: editor.IStandaloneCodeEditor) => {
  editorInstance = instance
}

const selectPartition = (index: number) => {
  emit('update:activeIndex', index)
  editorInstance?.focus()
}

const addPartition = async () => {
  localPartitions.value.push({ id: Date.now(), content: '' })
  const newIndex = localPartitions.value.length - 1
  emit('update:activeIndex', newIndex)
  await nextTick()
  editorInstance?.focus()
}

const removePartition = (index: number) => {
  if (localPartitions.value.length <= 1) return

  const currentActiveIndex = props.activeIndex
  localPartitions.value.splice(index, 1)

  if (index <= currentActiveIndex) {
    const newIndex = Math.max(0, currentActiveIndex - 1)
    if (newIndex !== currentActiveIndex) {
      emit('update:activeIndex', newIndex)
    }
  }
}

// --- 暴露给父组件的方法 ---

/**
 * 获取符合API格式的分区数据。
 */
const getData = (): SubMessageCreate[] => {
  return localPartitions.value
    .map(
      (part, index): SubMessageCreate => ({
        content: part.content,
        sortOrder: index,
        type: 'Normal',
      }),
    )
    .filter((part) => part.content.trim() !== '')
}

/**
 * 重置输入框为初始状态。
 */
const reset = () => {
  localPartitions.value = [{ id: Date.now(), content: '' }]
  emit('update:activeIndex', 0)
}

/**
 * 将焦点设置到当前激活的文本区域。
 */
const focus = () => {
  editorInstance?.focus()
}

defineExpose({
  getData,
  reset,
  focus,
})
</script>

<style scoped>
.multi-part-input-container {
  display: flex;
  height: 100%;
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  background-color: var(--el-bg-color);
}

.partition-sidebar {
  width: 40px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color);
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
}

.partition-sidebar .el-scrollbar {
  flex-grow: 1;
}

.partition-tab {
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  color: var(--el-text-color-regular);
}

.partition-tab:hover {
  background-color: var(--el-color-primary-light-9);
}

.partition-tab.is-active {
  background-color: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.tab-index {
  font-weight: 500;
}

.close-icon {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 12px;
  display: none;
  color: var(--el-text-color-placeholder);
}

.partition-tab:hover .close-icon {
  display: block;
}
.close-icon:hover {
  color: var(--el-color-danger);
}

.add-partition {
  height: 25px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-top: 1px solid var(--el-border-color);
}

.partition-editor {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  min-width: 0; /* 防止 flex 子项溢出 */
}

.monaco-wrapper {
  flex-grow: 1;
  height: 100%;
  overflow: hidden;
  background-color: #ffffff;
  padding: 0 12px;
}
</style>
