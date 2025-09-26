<template>
  <el-container class="chat-view-container">
    <!-- 左侧会话列表区域 -->
    <el-aside width="280px" class="chat-sidebar">
      <ChatList />
    </el-aside>

    <!-- 右侧主聊天窗口区域 -->
    <el-main class="chat-main">
      <ChatWindow />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
// 引入我们即将创建的子组件
import ChatList from '@/components/chat/ChatList.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
</script>

<style scoped>
.chat-view-container {
  height: 100vh; /* 关键：利用 App.vue 的全局样式，让容器占满整个视口高度 */
  background-color: var(--color-background);
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft); /* 使用 base.css 中的变量，与设置页面风格统一 */
  border-right: 1px solid var(--color-border);
}

.chat-main {
  /* 移除 main 区域的默认 padding，让 ChatWindow 组件来完全控制其内部布局 */
  padding: 0;
  display: flex;
  flex-direction: column;
}
</style>
