<template>
  <el-container class="settings-container">
    <el-header class="settings-header">
      <h1>系统设置</h1>
      <router-link to="/chat">
        <el-button type="primary">返回聊天</el-button>
      </router-link>
    </el-header>

    <el-main class="settings-main">
      <!--
        修改点 2: 动态绑定 class
        如果当前是资源中心 (resourceManager)，添加 'is-full-width' 类
      -->
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
          <el-tab-pane label="资源中心" name="resourceManager">
            <ResourceManager />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router'; // 引入路由钩子
import ProviderModelManager from '@/components/settings/ProviderModelManager.vue';
import GlobalSettings from '@/components/settings/GlobalSettings.vue';
import ResourceManager from '@/components/settings/ResourceManager.vue';

const route = useRoute();
const router = useRouter();

// 修改点 1: 初始化时尝试从 URL 获取 tab 参数，如果没有则默认为 'providerModel'
const activeTab = ref(route.query.tab?.toString() || 'providerModel');

// 修改点 1: 监听 activeTab 变化，同步修改 URL query
watch(activeTab, (newTab) => {
  // 使用 replace 而不是 push，避免产生过多的历史记录
  router.replace({ query: { ...route.query, tab: newTab } });
});

// 处理浏览器前进后退按钮的情况
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
  flex-shrink: 0; /* 防止头部被压缩 */
}

.settings-main {
  padding: 20px;
  flex-grow: 1;
  overflow: hidden; /* 防止 main 出现双重滚动条 */
  display: flex;
  flex-direction: column;
}

.settings-content {
  /* 默认状态：限制宽度，居中，适合表单 */
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  background-color: #ffffff;
  padding: 24px;
  border-radius: 8px;

  /* 关键修改：添加过渡效果，让宽度变化更丝滑 */
  transition: max-width 0.3s ease-in-out;

  /* 确保内容区域能撑满高度 (配合 ResourceManager 的高度计算) */
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  overflow: hidden; /* 内部滚动交给子组件 */
}

/* 修改点 2: 宽屏模式样式 */
.settings-content.is-full-width {
  max-width: 98%; /* 或者 100% */
}

/* 让 Tabs 内容区域也能撑满剩余空间 */
.el-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

:deep(.el-tabs__content) {
  flex-grow: 1;
  overflow: hidden; /* 防止溢出 */
  padding-top: 16px;
}

:deep(.el-tab-pane) {
  height: 100%; /* 传递高度给子组件 */
}
</style>
