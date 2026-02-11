<!-- frontend/mambo/src/components/settings/resource/ResourceVersionBar.vue -->
<template>
  <div class="version-top-bar">
    <div class="version-bar-header">
      <span class="version-bar-title">{{ t('resource.version.history') }}</span>
    </div>
    <el-scrollbar>
      <div class="version-list-horizontal">
        <!-- Special KB Config Card -->
        <div
          v-if="kbId"
          class="version-card-horizontal special-kb-card"
          :class="{ 'is-viewing': viewMode === 'kb_config' }"
          @click="$emit('toggle-kb-view')"
        >
          <div class="special-card-content">
            <el-icon :size="24" class="special-icon"><Setting /></el-icon>
            <span class="special-label">{{ t('resource.version.kbConfig') }}</span>
          </div>
        </div>

        <!-- Version List -->
        <template v-if="versions && versions.length > 0">
          <div
            v-for="version in versions"
            :key="version.id"
            class="version-card-horizontal"
            :class="{
              'is-active': activeVersionId === version.id,
              'is-viewing': viewMode === 'editor' && viewingVersionId === version.id,
            }"
            @click="$emit('select-version', version)"
          >
            <div class="version-card-header">
              <span class="version-name" :title="version.name">{{ version.name }}</span>
              <span class="version-date">{{
                new Date(version.createdAt).toLocaleDateString()
              }}</span>
            </div>
            <div class="version-card-footer">
              <el-button
                v-if="activeVersionId !== version.id"
                type="primary"
                link
                size="small"
                @click.stop="$emit('set-active', version.id)"
              >
                {{ t('resource.version.setActive') }}
              </el-button>
              <el-tag v-else type="success" size="small" effect="plain">{{ t('resource.version.current') }}</el-tag>
            </div>
          </div>
        </template>
        <div v-else-if="!kbId" class="no-versions">{{ t('resource.version.empty') }}</div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Setting } from '@element-plus/icons-vue'
import type { ResourceVersion } from '@/api/types'

defineProps<{
  versions: ResourceVersion[]
  activeVersionId: string | null
  viewingVersionId: string | null
  kbId?: string | null
  viewMode?: 'editor' | 'kb_config'
}>()

defineEmits<{
  (e: 'select-version', version: ResourceVersion): void
  (e: 'set-active', versionId: string): void
  (e: 'toggle-kb-view'): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.version-top-bar {
  flex-shrink: 0;
  height: 110px;
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
  height: 62px;
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.version-card-horizontal:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
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

/* Special KB Card Styles */
.special-kb-card {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
  justify-content: center;
  align-items: center;
  width: 140px; /* Slightly narrower than version cards */
}

.special-kb-card:hover {
  background-color: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}

.special-kb-card.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.special-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--el-color-primary);
}

.special-label {
  font-size: 12px;
  font-weight: 600;
}
</style>
