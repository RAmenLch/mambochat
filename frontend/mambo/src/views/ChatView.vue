<!-- frontend/mambo/src/views/ChatView.vue -->
<template>
  <!-- 移动端视图 -->
  <MobileChatView v-if="isMobile" />

  <!-- 桌面端视图 (原有逻辑) -->
  <el-container v-else class="chat-view-container">
    <el-aside :width="`${asideWidth}px`" class="chat-sidebar">
      <ChatList :is-collapsed="isSidebarCollapsed" :width="asideWidth" @expand="expand" />
    </el-aside>

    <div class="resizer" @mousedown.prevent="startResize"></div>

    <el-main class="chat-main">
      <ChatWindow :is-sidebar-collapsed="isSidebarCollapsed" />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch, defineAsyncComponent } from 'vue'
import ChatList from '@/components/chat/ChatList.vue'
import ChatWindow from '@/components/chat/ChatWindow.vue'
import { useResizablePanels } from '@/composables/useResizablePanels'
import { useIsMobile } from '@/composables/useIsMobile'

// 异步加载移动端组件，避免在桌面端加载不必要的代码
const MobileChatView = defineAsyncComponent(() => import('@/mobile/views/ChatView.vue'))

// --- Mobile Detection ---
const { isMobile } = useIsMobile()

// --- Desktop Logic (Keep existing logic) ---
const SIDEBAR_WIDTH_KEY = 'mambo_sidebar_width'
const SIDEBAR_COLLAPSED_KEY = 'mambo_sidebar_collapsed'

const savedWidth = localStorage.getItem(SIDEBAR_WIDTH_KEY)
const savedCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
const initialWidth = savedWidth ? parseInt(savedWidth, 10) : savedCollapsed ? 60 : 260

const asideWidth = ref(initialWidth)
const isSidebarCollapsed = ref(savedCollapsed)

const { startResize, expand } = useResizablePanels(asideWidth, isSidebarCollapsed, {
  min: 180,
  max: 500,
  snapThreshold: 150,
  collapsedWidth: 60,
  orientation: 'horizontal',
})

watch(asideWidth, (newWidth) => {
  localStorage.setItem(SIDEBAR_WIDTH_KEY, newWidth.toString())
})

watch(isSidebarCollapsed, (isCollapsed) => {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isCollapsed.toString())
})
</script>

<style scoped>
.chat-view-container {
  height: 100%;
  background-color: var(--color-background);
  display: flex;
  overflow: hidden;
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
  flex-shrink: 0;
  transition: width 0.3s cubic-bezier(0.25, 0.8, 0.5, 1);
  will-change: width;
  overflow: hidden;
}

.resizer {
  width: 3px;
  cursor: col-resize;
  background-color: var(--color-border);
  flex-shrink: 0;
  transition: background-color 0.2s ease;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.resizer:hover {
  background-color: var(--el-color-primary);
}

.chat-main {
  padding: 0;
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-width: 0;
}
</style>
