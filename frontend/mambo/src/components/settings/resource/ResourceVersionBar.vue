<template>
  <div class="version-top-bar">
    <div class="version-bar-header">
      <span class="version-bar-title">版本历史</span>
    </div>
    <el-scrollbar>
      <div class="version-list-horizontal">
        <template v-if="versions && versions.length > 0">
          <div
            v-for="version in versions"
            :key="version.id"
            class="version-card-horizontal"
            :class="{
              'is-active': activeVersionId === version.id,
              'is-viewing': viewingVersionId === version.id
            }"
            @click="$emit('select-version', version)"
          >
            <div class="version-card-header">
              <span class="version-name" :title="version.name">{{ version.name }}</span>
              <span class="version-date">{{ new Date(version.createdAt).toLocaleDateString() }}</span>
            </div>
            <div class="version-card-footer">
              <el-button
                v-if="activeVersionId !== version.id"
                type="primary"
                link
                size="small"
                @click.stop="$emit('set-active', version.id)"
              >
                设为当前
              </el-button>
              <el-tag v-else type="success" size="small" effect="plain">当前版本</el-tag>
            </div>
          </div>
        </template>
        <div v-else class="no-versions">暂无历史版本</div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import type { ResourceVersion } from '@/api/types';

defineProps<{
  versions: ResourceVersion[];
  activeVersionId: string | null;
  viewingVersionId: string | null;
}>();

defineEmits<{
  (e: 'select-version', version: ResourceVersion): void;
  (e: 'set-active', versionId: string): void;
}>();
</script>

<style scoped>
.version-top-bar {
  flex-shrink: 0;
  height: 110px; /* Reduced height */
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  flex-direction: column;
}

.version-bar-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.version-list-horizontal {
  display: flex;
  padding: 0 12px 12px 12px;
  gap: 12px;
}

.version-card-horizontal {
  flex-shrink: 0;
  width: 200px;
  height: 62px; /* Reduced height */
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  justify-content: space-between; /* Space out header and footer */
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.version-card-horizontal:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.version-card-horizontal.is-active {
  border-color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.version-card-horizontal.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.version-card-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
}

.version-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 8px;
}

.version-date {
  font-weight: normal;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.version-card-footer {
  display: flex;
  justify-content: flex-end;
}

.no-versions {
  padding: 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
