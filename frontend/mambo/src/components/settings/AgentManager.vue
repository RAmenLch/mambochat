<!-- frontend/mambo/src/components/settings/AgentManager.vue -->
<template>
  <div class="agent-manager-wrapper">
    <el-tabs v-model="activeTab" class="agent-tabs">
      <!-- Tab 1: Agent 管理 (原有的树 + 编辑器) -->
      <el-tab-pane :label="$t('agent.manager')" name="agent" class="tab-pane-full">
        <el-container class="agent-manager-container">
          <!-- 左侧：Agent 树 -->
          <AgentTreePanel />

          <!-- 右侧：编辑器 -->
          <el-main class="agent-editor-panel">
            <AgentEditor />
          </el-main>
        </el-container>
      </el-tab-pane>

      <!-- Tab 2: Backend 挂载配置 -->
      <el-tab-pane :label="$t('backend.manager')" name="backend" class="tab-pane-full">
        <BackendManagerPanel />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import AgentTreePanel from './agent/AgentTreePanel.vue';
import AgentEditor from './agent/AgentEditor.vue';
import BackendManagerPanel from './agent/BackendManagerPanel.vue'; // [新增] 引入 Backend 管理面板

const activeTab = ref('agent');
</script>

<style scoped>
.agent-manager-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

/* 覆盖 el-tabs 的默认样式，让其撑满整个高度 */
.agent-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.agent-tabs > .el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  background-color: var(--color-background-soft);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

:deep(.agent-tabs > .el-tabs__content) {
  flex-grow: 1;
  padding: 0;
  overflow: hidden;
}

.tab-pane-full {
  height: 100%;
}

.agent-manager-container {
  height: 100%;
  overflow: hidden;
}

.agent-editor-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
