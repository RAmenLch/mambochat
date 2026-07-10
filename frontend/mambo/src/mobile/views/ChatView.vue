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
      <ChatWindow @toggle-drawer="drawerVisible = true" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ChatList from '@/mobile/components/chat/ChatList.vue'
import ChatWindow from '@/mobile/components/chat/ChatWindow.vue'

const drawerVisible = ref(false)
</script>

<style scoped>
.mobile-layout {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: var(--color-background);
}

.mobile-main {
  height: 100%;
  width: 100%;
}

/* 样式穿透调整 Drawer 样式 */
:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
}
</style>
