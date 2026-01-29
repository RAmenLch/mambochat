<template>
  <el-container class="settings-container">
    <el-header class="settings-header">
      <h1>系统设置</h1>
      <router-link to="/chat">
        <el-button type="primary">返回聊天</el-button>
      </router-link>
    </el-header>

    <el-main class="settings-main">
      <div
        class="settings-content"
        :class="{ 'is-full-width': activeTab === 'resourceManager' }"
      >
        <el-tabs v-model="activeTab">
          <el-tab-pane label="服务商与模型管理" name="providerModel">
            <ProviderModelManager />
          </el-tab-pane>
          <el-tab-pane label="全局配置" name="globalSettings">
            <GlobalSettings />
          </el-tab-pane>
          <el-tab-pane label="MCP 工具" name="mcpManager">
            <McpManager />
          </el-tab-pane>
          <el-tab-pane label="资源中心" name="resourceManager">
            <ResourceManager />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ProviderModelManager from '@/components/settings/ProviderModelManager.vue';
import GlobalSettings from '@/components/settings/GlobalSettings.vue';
import ResourceManager from '@/components/settings/ResourceManager.vue';
import McpManager from '@/components/settings/McpManager.vue';

const route = useRoute();
const router = useRouter();

const activeTab = ref(route.query.tab?.toString() || 'providerModel');

watch(activeTab, (newTab) => {
  router.replace({ query: { ...route.query, tab: newTab } });
});

watch(() => route.query.tab, (newTab) => {
  if (newTab && newTab !== activeTab.value) {
    activeTab.value = newTab.toString();
  }
});
</script>

<style scoped>
.settings-container {
  height: 100vh;
  background-color: #f0f2f5;
  display: flex;
  flex-direction: column;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #ffffff;
  border-bottom: 1px solid #dcdfe6;
  flex-shrink: 0;
}

.settings-main {
  padding: 20px;
  flex-grow: 1;
  /* 主内容区域负责滚动 */
  overflow-y: auto;
}

.settings-content {
  /* 默认状态：高度由内容决定 */
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  background-color: #ffffff;
  padding: 24px;
  border-radius: 8px;
  transition: max-width 0.3s ease-in-out;
}

/* 资源中心激活时，应用全屏 Flex 布局 */
.settings-content.is-full-width {
  max-width: 98%;
  /* 占满父容器 .settings-main 的所有可用高度 */
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 以下强制高度的样式，都限定在 .is-full-width 类下 */
.settings-content.is-full-width .el-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-content.is-full-width :deep(.el-tabs__content) {
  flex-grow: 1;
  overflow: hidden;
}

.settings-content.is-full-width :deep(.el-tab-pane) {
  height: 100%;
}

/* 为所有标签页提供一个统一的顶部内边距 */
:deep(.el-tabs__content) {
  padding-top: 16px;
}
</style>
