<template>
  <el-container class="chat-view-container">
    <!-- 左侧会话列表区域 -->
    <el-aside :width="`${asideWidth}px`" class="chat-sidebar">
      <ChatList />
    </el-aside>

    <!-- 拖拽手柄 -->
    <div class="resizer" @mousedown.prevent="startResize"></div>

    <!-- 右侧主聊天窗口区域 -->
    <el-main class="chat-main">
      <ChatWindow />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ChatList from '@/components/chat/ChatList.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';

// --- 侧边栏宽度常量 ---
const DEFAULT_ASIDE_WIDTH = 190; // 默认宽度
const MIN_ASIDE_WIDTH = 150;     // 最小宽度
const MAX_ASIDE_WIDTH = 500;     // 最大宽度

const asideWidth = ref(DEFAULT_ASIDE_WIDTH);

// --- 拖拽逻辑 ---
const startResize = (event: MouseEvent) => {
  const startX = event.clientX;
  const startWidth = asideWidth.value;

  const doResize = (e: MouseEvent) => {
    const deltaX = e.clientX - startX;
    const newWidth = startWidth + deltaX;
    // 应用宽度限制
    asideWidth.value = Math.max(MIN_ASIDE_WIDTH, Math.min(newWidth, MAX_ASIDE_WIDTH));
  };

  const stopResize = () => {
    window.removeEventListener('mousemove', doResize);
    window.removeEventListener('mouseup', stopResize);
    // 恢复鼠标样式和文本选择
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  // 阻止拖拽过程中的文本选择
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';

  window.addEventListener('mousemove', doResize);
  window.addEventListener('mouseup', stopResize);
};
</script>

<style scoped>
.chat-view-container {
  height: 100vh;
  background-color: var(--color-background);
  /* 确保容器是flex布局, 以便resizer能正常工作 */
  display: flex;
  overflow: hidden; /* 防止拖动过快导致出现滚动条 */
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
  /* 确保侧边栏不会被flex压缩 */
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
  /* 允许主区域根据侧边栏宽度变化而伸缩 */
  flex-grow: 1;
  /* 修复flex布局中内容溢出的问题 */
  min-width: 0;
}
</style>
