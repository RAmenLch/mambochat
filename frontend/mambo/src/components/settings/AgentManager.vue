<!-- frontend/mambo/src/components/settings/AgentManager.vue -->
<template>
  <el-container class="agent-manager-container">
    <!-- 左侧：Agent 树 -->
    <AgentTreePanel />

    <!-- 右侧：编辑器 -->
    <el-main class="agent-editor-panel">
      <AgentEditor />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import AgentTreePanel from './agent/AgentTreePanel.vue';
import AgentEditor from './agent/AgentEditor.vue';
</script>

<style scoped>
.agent-manager-container {
  height: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px; /* 与 Resource 保持一致 */
  background-color: var(--el-bg-color);
  overflow: hidden;
}

.agent-editor-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
