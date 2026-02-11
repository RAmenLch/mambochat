<!-- frontend/mambo/src/components/chat/dialogs/MessageEditDialog.vue -->
<template>
  <el-dialog
    v-model="internalVisible"
    :title="title || t('chat.edit.title')"
    :width="dialogWidth + 'px'"
    :fullscreen="isFullscreen"
    :close-on-click-modal="false"
    draggable
    align-center
    class="message-edit-dialog"
    @close="handleClose"
    @open="handleOpen"
  >
    <!-- 顶部工具栏 -->
    <div class="dialog-toolbar">
      <el-tooltip :content="isFullscreen ? t('chat.edit.exitFullscreen') : t('chat.edit.fullscreen')" placement="top">
        <el-button link @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <!-- 编辑器容器：高度由 contentHeight 控制 -->
    <div
      class="monaco-wrapper"
      :style="{ height: isFullscreen ? 'calc(100vh - 180px)' : contentHeight + 'px' }"
    >
      <ResourceUniversalEditor
        v-model="editingContent"
        language="markdown"
        :monaco-options="editorOptions"
        @editor-mounted="handleEditorMounted"
      />
    </div>

    <template #footer>
      <div class="dialog-footer-wrapper">
        <div class="footer-buttons">
          <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
          <el-button type="primary" @click="handleSaveOnly">{{ t('chat.edit.saveOnly') }}</el-button>
          <el-button v-if="isUserMessage" type="success" @click="handleSaveAndResend">
            {{ t('chat.edit.saveAndRegenerate') }}
          </el-button>
        </div>

        <!-- 拖拽手柄：仅在非全屏模式下显示 -->
        <div v-if="!isFullscreen" class="resize-handle" @mousedown.prevent="startResize">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path
              fill="currentColor"
              d="M22,22H20V20H22V22M22,18H20V16H22V18M18,22H16V20H18V22M18,18H16V16H18V18M14,22H12V20H14V22M22,14H20V12H22V14Z"
            />
          </svg>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { FullScreen } from '@element-plus/icons-vue'
import type { editor } from 'monaco-editor'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  initialContent: string
  isUserMessage: boolean
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'save', newContent: string): void
  (e: 'saveAndResend', newContent: string): void
}>()

// --- 状态管理 ---
const internalVisible = ref(false)
const editingContent = ref('')
const isFullscreen = ref(false)
let editorInstance: editor.IStandaloneCodeEditor | null = null

// --- 尺寸控制状态 ---
const dialogWidth = ref(800)
const contentHeight = ref(400)
const minWidth = 400
const minHeight = 200

// --- Monaco 配置 ---
const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
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
  padding: { top: 12, bottom: 12 },
  automaticLayout: true,
}))

// --- 监听器 ---
watch(
  () => props.visible,
  (newVal) => {
    internalVisible.value = newVal
    if (newVal) {
      editingContent.value = props.initialContent
      isFullscreen.value = false
    }
  },
)

// --- 方法 ---

const handleOpen = () => {
  if (dialogWidth.value < minWidth) dialogWidth.value = 800
  if (contentHeight.value < minHeight) contentHeight.value = 400
}

const handleEditorMounted = (instance: editor.IStandaloneCodeEditor) => {
  editorInstance = instance
}

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value
  setTimeout(() => editorInstance?.layout(), 100)
}

const handleClose = () => {
  emit('update:visible', false)
}

const validateContent = (): boolean => {
  if (editingContent.value.trim() === '') {
    ElMessage.warning(t('chat.edit.contentEmpty'))
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

// --- 拖拽调整大小逻辑 ---

const isResizing = ref(false)
let startX = 0
let startY = 0
let startWidth = 0
let startHeight = 0

const startResize = (event: MouseEvent) => {
  isResizing.value = true
  startX = event.clientX
  startY = event.clientY
  startWidth = dialogWidth.value
  startHeight = contentHeight.value

  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', stopResize)

  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'nwse-resize'
}

const handleMouseMove = (event: MouseEvent) => {
  if (!isResizing.value) return

  const deltaX = event.clientX - startX
  const deltaY = event.clientY - startY

  dialogWidth.value = Math.max(minWidth, startWidth + deltaX)
  contentHeight.value = Math.max(minHeight, startHeight + deltaY)
}

const stopResize = () => {
  isResizing.value = false
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', stopResize)

  document.body.style.userSelect = ''
  document.body.style.cursor = ''

  editorInstance?.layout()
}

onUnmounted(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', stopResize)
})
</script>

<style scoped>
.dialog-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
  padding-right: 4px;
}

.monaco-wrapper {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background-color: #ffffff;
  padding: 0 2px;
  overflow: hidden;
}

.monaco-wrapper :deep(.simple-textarea .el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  padding: 8px 2px;
  background-color: transparent;
}

.dialog-footer-wrapper {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  position: relative;
  margin: -10px -10px -10px 0;
  padding: 10px 10px 10px 0;
}

.footer-buttons {
  margin-right: 10px;
}

.resize-handle {
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  position: absolute;
  bottom: 6px;
  right: 6px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.resize-handle:hover {
  opacity: 1;
  color: var(--el-color-primary);
}
</style>
