<template>
  <div class="mobile-layout">
    <el-drawer
      v-model="drawerVisible"
      direction="ltr"
      size="85%"
      :with-header="false"
      :close-on-press-escape="true"
      class="mobile-drawer"
    >
      <ChatList @close-drawer="drawerVisible = false" />
    </el-drawer>

    <div class="mobile-main">
      <template v-if="isGroupSelected">
        <div class="group-mobile-bar">
          <el-button :icon="Menu" text @click="drawerVisible = true" />
        </div>
        <GroupChatWindow />
      </template>
      <ChatWindow v-else @toggle-drawer="drawerVisible = true" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { Menu } from '@element-plus/icons-vue'
import ChatList from '@/mobile/components/chat/ChatList.vue'
import ChatWindow from '@/mobile/components/chat/ChatWindow.vue'
import GroupChatWindow from '@/components/chat/group/GroupChatWindow.vue'
import { useChatSessionStore } from '@/stores/chatSessionStore'

const drawerVisible = ref(false)
const { isGroupSelected } = storeToRefs(useChatSessionStore())

// 群聊分支不经过 ChatWindow，视口高度需在此统一维护（键盘弹起时底部不被遮挡）
const vvResizeHandler = () => {
  const vh = window.visualViewport ? window.visualViewport.height : window.innerHeight
  document.documentElement.style.setProperty('--vv-height', `${vh}px`)
}

onMounted(() => {
  vvResizeHandler()
  window.visualViewport?.addEventListener('resize', vvResizeHandler)
  window.visualViewport?.addEventListener('scroll', vvResizeHandler)
  window.addEventListener('resize', vvResizeHandler)
})

onUnmounted(() => {
  window.visualViewport?.removeEventListener('resize', vvResizeHandler)
  window.visualViewport?.removeEventListener('scroll', vvResizeHandler)
  window.removeEventListener('resize', vvResizeHandler)
})
</script>

<style scoped>
.mobile-layout {
  height: var(--vv-height, 100vh);
  height: var(--vv-height, 100dvh);
  width: 100vw;
  overflow: hidden;
  background-color: var(--color-background);
}

.mobile-main {
  height: 100%;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.group-mobile-bar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding: 4px 8px;
  border-bottom: 1px solid var(--color-border);
}

/* 样式穿透调整 Drawer 样式 */
:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
}
</style>
