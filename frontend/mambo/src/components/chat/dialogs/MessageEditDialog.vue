<template>
  <el-dialog v-model="internalVisible" title="编辑分区内容" width="650px" @close="handleClose">
    <div class="monaco-wrapper">
      <MonacoEditor v-model="editingContent" language="markdown" :options="editorOptions" />
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleSaveOnly">仅保存</el-button>
        <el-button v-if="isUserMessage" type="success" @click="handleSaveAndResend">
          保存并重新生成
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { editor } from 'monaco-editor'
import MonacoEditor from '@/components/common/MonacoEditor.vue'

const props = defineProps<{
  visible: boolean
  // 需要编辑的原始文本内容
  initialContent: string
  // 指示此消息是否为用户消息，以决定是否显示“保存并重新生成”按钮
  isUserMessage: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  // 仅保存事件，传递更新后的内容
  (e: 'save', newContent: string): void
  // 保存并重新生成事件，传递更新后的内容
  (e: 'saveAndResend', newContent: string): void
}>()

const internalVisible = ref(false)
const editingContent = ref('')

// Monaco Editor 配置
const editorOptions: editor.IStandaloneEditorConstructionOptions = {
  minimap: { enabled: false },
  lineNumbers: 'off',
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  folding: false,
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  renderLineHighlight: 'none',
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
  padding: { top: 8, bottom: 8 },
}

// 监听外部 visible 属性的变化
watch(
  () => props.visible,
  (newVal) => {
    internalVisible.value = newVal
    if (newVal) {
      // 每次打开对话框时，用 props 的初始内容填充输入框
      editingContent.value = props.initialContent
    }
  },
)

const handleClose = () => {
  emit('update:visible', false)
}

// 校验内容是否为空
const validateContent = (): boolean => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning('内容不能为空')
    return false
  }
  return true
}

const handleSaveOnly = () => {
  if (validateContent()) {
    emit('save', editingContent.value)
    handleClose()
  }
}

const handleSaveAndResend = () => {
  if (validateContent()) {
    emit('saveAndResend', editingContent.value)
    handleClose()
  }
}
</script>

<style scoped>
.monaco-wrapper {
  height: 320px; /* 约等于原 12 行 textarea 的高度 */
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  background-color: #ffffff;
  padding: 0 12px;
}
</style>
