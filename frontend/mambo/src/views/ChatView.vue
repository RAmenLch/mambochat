<!-- frontend/mambo/src/views/ChatView.vue -->
<template>
  <el-container class="chat-view-container">
    <el-aside :width="`${asideWidth}px`" class="chat-sidebar">
      <!-- 变更点：传入 width 属性 -->
      <ChatList
        :is-collapsed="isSidebarCollapsed"
        :width="asideWidth"
        @expand="expand"
      />
    </el-aside>

    <div class="resizer" @mousedown.prevent="startResize"></div>

    <el-main class="chat-main">
      <ChatWindow
        :is-sidebar-collapsed="isSidebarCollapsed"
      />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import ChatList from '@/components/chat/ChatList.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
import { useResizablePanels } from '@/composables/useResizablePanels';

// --- Constants for Persistence ---
const SIDEBAR_WIDTH_KEY = 'mambo_sidebar_width';
const SIDEBAR_COLLAPSED_KEY = 'mambo_sidebar_collapsed';

// --- State Initialization ---
const savedWidth = localStorage.getItem(SIDEBAR_WIDTH_KEY);
// 如果上次是折叠状态，恢复时宽度设为 60 (collapsedWidth)，否则设为保存值或默认 260
// 注意：这里需要根据保存的 collapsed 状态来决定初始 width，防止逻辑冲突
const savedCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
const initialWidth = savedWidth ? parseInt(savedWidth, 10) : (savedCollapsed ? 60 : 260);

const asideWidth = ref(initialWidth);
const isSidebarCollapsed = ref(savedCollapsed);

// --- Responsive Panel Logic ---
const { startResize, expand } = useResizablePanels(asideWidth, isSidebarCollapsed, {
  min: 180, // 正常列表的最小舒适宽度
  max: 500,
  snapThreshold: 150, // 拖过这里松手就会折叠
  collapsedWidth: 60,
  orientation: 'horizontal'
});

// --- Persistence Watchers ---
watch(asideWidth, (newWidth) => {
  localStorage.setItem(SIDEBAR_WIDTH_KEY, newWidth.toString());
});

watch(isSidebarCollapsed, (isCollapsed) => {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isCollapsed.toString());
});
</script>

<style scoped>
.chat-view-container {
  height: 100vh;
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
