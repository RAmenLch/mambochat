<script setup lang="ts">
import { onMounted, computed, watch } from 'vue'
import { RouterView } from 'vue-router'
import { useChatListStore } from '@/stores/chatListStore'
import { useMcpStore } from '@/stores/mcpStore'
import { useSettingsStore } from '@/stores/settingsStore'
import loader from '@monaco-editor/loader'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { useI18n } from 'vue-i18n'

const chatListStore = useChatListStore()
const mcpStore = useMcpStore()
const settingsStore = useSettingsStore()
const { locale } = useI18n()

// 根据全局设置计算 Element Plus 的语言包
const elementLocale = computed(() => {
  return settingsStore.globalSettings.language === 'en' ? en : zhCn
})

// 监听全局设置变化，同步更新 vue-i18n 的 locale
watch(
  () => settingsStore.globalSettings.language,
  (newLang) => {
    if (newLang) {
      locale.value = newLang
    }
  },
  { immediate: true }
)

onMounted(async () => {
  // 1. 优先获取全局配置，确保语言环境正确加载
  await settingsStore.fetchGlobalSettings()
  // 确保在异步获取配置后，如果 watch 没有触发（例如初始值与默认值相同），手动同步一次
  if (settingsStore.globalSettings.language) {
    locale.value = settingsStore.globalSettings.language
  }

  // 2. 初始化全局通知监听器
  chatListStore.initializeNotificationListener()
  // 3. 获取可用的 MCP 服务列表
  mcpStore.fetchAvailableServices()

  // 4. Monaco Editor 资源静默预加载
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
  <el-config-provider :locale="elementLocale">
    <RouterView />
  </el-config-provider>
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
