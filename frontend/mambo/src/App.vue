<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useChatListStore } from '@/stores/chatListStore'
import { useMcpStore } from '@/stores/mcpStore'
import loader from '@monaco-editor/loader'

const chatListStore = useChatListStore()
const mcpStore = useMcpStore()

onMounted(() => {
  // 初始化全局通知监听器
  chatListStore.initializeNotificationListener()
  // 获取可用的 MCP 服务列表
  mcpStore.fetchAvailableServices()

  // Monaco Editor 资源静默预加载
  const preloadMonaco = () => {
    loader.config({ paths: { vs: '/monaco-editor/vs' } })
    loader
      .init()
      .then(() => {
        // Monaco 核心资源已加载并缓存
      })
      .catch((err) => {
        console.warn('Monaco Editor preload failed:', err)
      })
  }

  if ('requestIdleCallback' in window) {
    ;(window as any).requestIdleCallback(preloadMonaco)
  } else {
    setTimeout(preloadMonaco, 2000)
  }
})
</script>

<template>
  <RouterView />
</template>

<style>
/*
  添加一些全局样式，确保我们的应用布局能占满整个屏幕高度。
  这对于创建类似聊天应用的侧边栏固定布局至关重要。
*/
html,
body,
#app {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden; /* 防止出现不必要的滚动条 */
}
</style>
