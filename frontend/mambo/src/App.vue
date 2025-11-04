<script setup lang="ts">
import { onMounted } from 'vue';
import { RouterView } from 'vue-router';
import { useChatStore } from '@/stores/chatStore';

const chatStore = useChatStore();

onMounted(() => {
  // Initialize the global notification listener when the application mounts.
  chatStore.initializeNotificationListener();
});
</script>

<template>
  <RouterView />
</template>

<style>
/*
  添加一些全局样式，确保我们的应用布局能占满整个屏幕高度。
  这对于创建类似聊天应用的侧边栏固定布局至关重要。
*/
html, body, #app {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden; /* 防止出现不必要的滚动条 */
}
</style>
