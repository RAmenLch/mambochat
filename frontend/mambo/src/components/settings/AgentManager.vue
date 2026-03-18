<template>
  <div class="agent-manager-container">
    <div class="sidebar">
      <AgentTreePanel />
    </div>
    <div class="main-content">
      <AgentEditor />
    </div>
  </div>
</template>

<script setup lang="ts">
import AgentTreePanel from './agent/AgentTreePanel.vue';
import AgentEditor from './agent/AgentEditor.vue';
</script>

<style scoped>
.agent-manager-container {
  display: flex;
  height: 100%;
  width: 100%;
  background-color: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}
.sidebar {
  width: 280px;
  flex-shrink: 0;
  background-color: var(--el-bg-color-page);
}
.main-content {
  flex-grow: 1;
  min-width: 0;
}
</style>
