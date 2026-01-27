<template>
  <el-dialog
    v-model="internalVisible"
    :title="title"
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
      <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
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
      <MonacoEditor
        v-model="editingContent"
        language="markdown"
        :options="editorOptions"
        @editor-mounted="handleEditorMounted"
      />
    </div>

    <template #footer>
      <div class="dialog-footer-wrapper">
        <div class="footer-buttons">
          <el-button @click="handleClose">取消</el-button>
          <el-button type="primary" @click="handleSaveOnly">仅保存</el-button>
          <el-button v-if="isUserMessage" type="success" @click="handleSaveAndResend">
            保存并重新生成
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
import { ElMessage } from 'element-plus'
import { FullScreen } from '@element-plus/icons-vue'
import type { editor } from 'monaco-editor'
import MonacoEditor from '@/components/common/MonacoEditor.vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    initialContent: string
    isUserMessage: boolean
    title?: string
  }>(),
  {
    title: '编辑分区内容',
  },
)

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
const dialogWidth = ref(800) // 初始宽度 (px)
const contentHeight = ref(400) // 初始高度 (px)
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
  automaticLayout: true, // 关键：确保编辑器随容器大小自动重绘
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
  // 每次打开时，如果当前宽度/高度异常，可以重置为默认值
  if (dialogWidth.value < minWidth) dialogWidth.value = 800
  if (contentHeight.value < minHeight) contentHeight.value = 400
}

const handleEditorMounted = (instance: editor.IStandaloneCodeEditor) => {
  editorInstance = instance
}

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value
  // 切换后强制刷新布局
  setTimeout(() => editorInstance?.layout(), 100)
}

const handleClose = () => {
  emit('update:visible', false)
}

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

// --- 拖拽调整大小逻辑 (Resize Logic) ---

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

  // 添加全局事件监听
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', stopResize)

  // 防止选中文本
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'nwse-resize'
}

const handleMouseMove = (event: MouseEvent) => {
  if (!isResizing.value) return

  const deltaX = event.clientX - startX
  const deltaY = event.clientY - startY

  // 计算新尺寸
  // const newWidth = startWidth + deltaX * 2 // *2 是因为 el-dialog 默认居中，向右拉伸时左边也会动，为了视觉跟手通常乘以系数，或者简单相加
  // Element Plus 的 dialog 是 transform 居中的，单纯加 deltaX 实际上是单边扩展。
  // 为了体验更好，我们直接加 deltaX，用户感觉是向右下角拉伸。

  dialogWidth.value = Math.max(minWidth, startWidth + deltaX)
  contentHeight.value = Math.max(minHeight, startHeight + deltaY)
}

const stopResize = () => {
  isResizing.value = false
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', stopResize)

  // 恢复样式
  document.body.style.userSelect = ''
  document.body.style.cursor = ''

  // 触发一次 layout 确保 Monaco 渲染正确
  editorInstance?.layout()
}

// 组件卸载时清理事件，防止内存泄漏
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
  /* 移除 CSS resize，改用 JS 控制 */
}

/* Footer 布局 */
.dialog-footer-wrapper {
  display: flex;
  justify-content: flex-end; /* 按钮靠右 */
  align-items: center;
  position: relative;
  /* 修正 el-dialog footer 默认 padding 带来的视觉偏差 */
  margin: -10px -10px -10px 0;
  padding: 10px 10px 10px 0;
}

.footer-buttons {
  margin-right: 10px;
}

/* 拖拽手柄样式 */
.resize-handle {
  width: 16px;
  height: 16px;
  cursor: nwse-resize; /* 鼠标样式：西北-东南方向调整 */
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  /* 绝对定位到右下角 */
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
