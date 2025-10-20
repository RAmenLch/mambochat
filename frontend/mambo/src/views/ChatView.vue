<template>
  <el-container class="chat-view-container">
    <el-aside :width="`${asideWidth}px`" class="chat-sidebar">
      <ChatList />
    </el-aside>

    <div class="resizer" @mousedown.prevent="startResize"></div>

    <el-main class="chat-main">
      <ChatWindow />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ChatList from '@/components/chat/ChatList.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
import { useResizablePanels } from '@/composables/useResizablePanels';

// --- Responsive Panel Logic ---
const asideWidth = ref(220); // Default width
const { startResize } = useResizablePanels(asideWidth, {
  min: 180,       // Minimum width
  max: 500,       // Maximum width
  orientation: 'horizontal'
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
}

.resizer {
  width: 3px;
  cursor: col-resize;
  background-color: var(--color-border);
  flex-shrink: 0;
  transition: background-color 0.2s ease, width 0.2s ease;
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
