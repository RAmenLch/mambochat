<!-- frontend/mambo/src/mobile/components/chat/dialogs/MobileMessageEditDialog.vue -->
<template>
  <el-dialog
    v-model="internalVisible"
    :show-close="false"
    :close-on-click-modal="false"
    class="mobile-edit-dialog-screen"
    :style="dialogStyle"
    :modal="true"
    append-to-body
    align-center
    @close="handleClose"
    @open="handleOpen"
  >
    <!-- 头部 -->
    <template #header>
      <div class="mobile-header">
        <span class="title">{{ title || t('chat.edit.title') }}</span>
        <div class="header-actions">
           <el-icon class="close-btn" @click="handleClose"><Close /></el-icon>
        </div>
      </div>
    </template>

    <!--
      编辑器外层容器：
      这里是关键，我们给这个容器加上背景色和内边距，
      制造出“显示器边框”的感觉
    -->
    <div class="mobile-editor-layout">
      <div class="mobile-editor-bezel">
        <ResourceUniversalEditor
          v-if="internalVisible"
          v-model="editingContent"
          language="markdown"
          :monaco-options="editorOptions"
          @editor-mounted="handleEditorMounted"
        />
      </div>
    </div>

    <!-- 底部按钮 -->
    <template #footer>
      <div class="mobile-footer">
        <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
        <div class="footer-right">
          <el-button type="primary" @click="handleSaveOnly">{{ t('chat.edit.saveOnly') }}</el-button>
          <el-button v-if="isUserMessage" type="success" @click="handleSaveAndResend">
            {{ t('chat.edit.saveAndRegenerate') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
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

const internalVisible = ref(false)
const editingContent = ref('')
let editorInstance: editor.IStandaloneCodeEditor | null = null

// --- 布局状态 ---
const layoutState = reactive({
  top: 0,
  height: 0
})

// --- 样式计算：回归全屏逻辑，确保最大化 ---
const dialogStyle = computed(() => {
  // 兜底逻辑
  if (!layoutState.height) {
    return {
      position: 'fixed',
      top: '0',
      left: '0',
      width: '100%',
      height: '100%',
      margin: '0',
      padding: '0',
      overflow: 'hidden'
    }
  }

  return {
    position: 'fixed',
    // 精确贴合可视区域 (Visual Viewport)
    top: `${layoutState.top}px`,
    left: '0',
    width: '100%',
    height: `${layoutState.height}px`,

    margin: '0',
    padding: '0',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--color-background)',
    zIndex: 2000
  }
})

const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  minimap: { enabled: false },
  lineNumbers: 'off',
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  folding: false,
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  renderLineHighlight: 'none',
  fontSize: 16,
  fontFamily: 'var(--el-font-family)',
  padding: { top: 12, bottom: 12 }, // 编辑器内部上下的留白
  automaticLayout: true,
  contextmenu: false,
  fixedOverflowWidgets: true
}))

// --- VisualViewport 适配 ---
const updateLayout = () => {
  if (window.visualViewport) {
    layoutState.top = window.visualViewport.offsetTop
    layoutState.height = window.visualViewport.height
  } else {
    layoutState.top = 0
    layoutState.height = window.innerHeight
  }

  if (editorInstance) {
    nextTick(() => editorInstance?.layout())
  }
}

watch(
  () => props.visible,
  (newVal) => {
    internalVisible.value = newVal
    if (newVal) {
      editingContent.value = props.initialContent
      nextTick(() => updateLayout())
    }
  }
)

onMounted(() => {
  updateLayout()
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', updateLayout)
    window.visualViewport.addEventListener('scroll', updateLayout)
  }
  window.addEventListener('resize', updateLayout)
})

onUnmounted(() => {
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', updateLayout)
    window.visualViewport.removeEventListener('scroll', updateLayout)
  }
  window.removeEventListener('resize', updateLayout)
})

const handleOpen = () => {
  setTimeout(() => updateLayout(), 100)
}

const handleEditorMounted = (instance: editor.IStandaloneCodeEditor) => {
  editorInstance = instance
  setTimeout(() => instance.layout(), 50)
}

const handleClose = () => {
  emit('update:visible', false)
}

const validateContent = () => {
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
</script>

<style>
/*
  .mobile-edit-dialog-screen
  全屏模式，去除圆角和阴影，作为一个基础画布
*/

.mobile-edit-dialog-screen {
  display: flex !important;
  flex-direction: column !important;
  background-color: var(--color-background) !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}

/* 头部 */
.mobile-edit-dialog-screen .el-dialog__header {
  flex-shrink: 0;
  margin: 0 !important;
  padding: 0 16px !important;
  height: 50px;
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
}

/* Body 区域：Flex 1 撑满 */
.mobile-edit-dialog-screen .el-dialog__body {
  flex: 1 !important;
  height: 100% !important;
  min-height: 0 !important;
  padding: 0 !important; /* 注意：这里Body不加padding，padding加在内部容器上 */
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  background-color: var(--el-fill-color-lighter); /* 给背景一个极淡的灰色，突出中间的编辑器 */
}

/* 底部 */
.mobile-edit-dialog-screen .el-dialog__footer {
  flex-shrink: 0;
  padding: 10px 16px !important;
  border-top: 1px solid var(--el-border-color-light);
  background-color: var(--color-background);
  padding-bottom: calc(10px + env(safe-area-inset-bottom)) !important;
}

/* --- 核心修改区域 --- */

/* 1. 布局层：负责背景和内边距 */
.mobile-editor-layout {
  flex: 1;
  width: 100%;
  height: 100%;
  /*
    关键点：在这里设置左右的留白 (12px)
    上下留一点点 (8px) 让它看起来悬浮
  */
  padding: 8px 6px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

/* 2. 边框层：负责包裹编辑器，形成“屏幕”的感觉 */
.mobile-editor-bezel {
  flex: 1;
  width: 100%;
  height: 100%;
  background-color: #fff; /* 编辑器背景纯白 */
  border: 1px solid var(--el-border-color); /* 细微边框 */
  border-radius: 8px; /* 圆角 */
  overflow: hidden; /* 确保内容不溢出圆角 */
  position: relative;
}

/* 确保 Monaco 填满 Bezel */
.mobile-editor-bezel > div {
  height: 100% !important;
  width: 100% !important;
}

/* 内部组件样式 */
.mobile-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.mobile-header .title {
  font-size: 16px;
  font-weight: 600;
}

.mobile-header .close-btn {
  font-size: 20px;
  padding: 8px;
  margin-right: -8px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
}

.mobile-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-right {
  display: flex;
  gap: 8px;
}
</style>
