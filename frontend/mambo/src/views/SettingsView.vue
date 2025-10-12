<template>
  <el-container class="settings-container">
    <el-header class="settings-header">
      <h1>系统设置</h1>
      <router-link to="/chat">
        <el-button type="primary">返回聊天</el-button>
      </router-link>
    </el-header>

    <el-main class="settings-main">
      <div class="settings-content">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="服务商与模型管理" name="providerModel">
            <ProviderModelManager />
          </el-tab-pane>
          <el-tab-pane label="全局配置" name="globalSettings">
            <GlobalSettings />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ProviderModelManager from '@/components/settings/ProviderModelManager.vue';
import GlobalSettings from '@/components/settings/GlobalSettings.vue';

const activeTab = ref('providerModel');
</script>

<style scoped>
.settings-container {
  height: 100vh;
  background-color: #f0f2f5;
}
.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #ffffff;
  border-bottom: 1px solid #dcdfe6;
}
.settings-main {
  padding: 20px;
}
.settings-content {
  max-width: 1200px;
  margin: 0 auto;
  background-color: #ffffff;
  padding: 24px;
  border-radius: 8px;
}
/* 确保标签页内容区域有合适的内边距 */
.el-tabs >>> .el-tab-pane {
    padding-top: 16px;
}
</style>
