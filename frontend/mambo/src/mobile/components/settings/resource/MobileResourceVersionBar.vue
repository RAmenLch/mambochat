<!-- frontend/mambo/src/mobile/components/settings/resource/MobileResourceVersionBar.vue -->
<template>
  <div class="mobile-version-bar">
    <div class="version-bar-header">
      <span class="version-bar-title">{{ t('resource.version.history') }}</span>
    </div>
    <el-scrollbar>
      <div class="version-list-horizontal">
        <!-- Special KB Config Card (If applicable) -->
        <div
          v-if="kbId"
          class="version-card-horizontal special-kb-card"
          :class="{ 'is-viewing': viewMode === 'kb_config' }"
          @click="$emit('toggle-kb-view')"
        >
          <div class="special-card-content">
            <el-icon :size="20" class="special-icon"><Setting /></el-icon>
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
              <button class="card-more-btn" @click.stop="openActions(version)">
                <el-icon :size="14"><MoreFilled /></el-icon>
              </button>
            </div>
          </div>
        </template>
        <div v-else-if="!kbId" class="no-versions">{{ t('resource.version.empty') }}</div>
      </div>
    </el-scrollbar>

    <!-- 版本操作面板（触屏无右键菜单，改为点按弹出） -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="actionVersion" class="sheet-overlay" @click="actionVersion = null">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-title">{{ actionVersion.name }}</div>
            <button class="sheet-item" :disabled="actionIndex <= 0" @click="emitMove('up')">
              {{ t('resource.version.moveUp') }}
            </button>
            <button class="sheet-item" :disabled="actionIndex < 0 || actionIndex >= versions.length - 1" @click="emitMove('down')">
              {{ t('resource.version.moveDown') }}
            </button>
            <button
              class="sheet-item danger"
              :disabled="deleteDisabled"
              @click="emitDelete"
            >
              {{ t('resource.version.delete') }}
            </button>
            <button class="sheet-cancel" @click="actionVersion = null">{{ t('common.action.cancel') }}</button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { MoreFilled, Setting } from '@element-plus/icons-vue'
import type { ResourceVersion } from '@/api/types'

const props = defineProps<{
  versions: ResourceVersion[]
  activeVersionId: string | null
  viewingVersionId: string | null
  kbId?: string | null
  viewMode?: 'editor' | 'kb_config'
}>()

const emit = defineEmits<{
  (e: 'select-version', version: ResourceVersion): void
  (e: 'set-active', versionId: string): void
  (e: 'toggle-kb-view'): void
  (e: 'delete-version', versionId: string): void
  (e: 'move-version', payload: { versionId: string; direction: 'up' | 'down' }): void
}>()

const { t } = useI18n()

// --- 版本操作面板 ---
const actionVersion = ref<ResourceVersion | null>(null)

const actionIndex = computed(() =>
  actionVersion.value ? props.versions.findIndex(v => v.id === actionVersion.value!.id) : -1,
)

/** 当前活跃版本与最后一个版本不允许删除（与后端约束一致） */
const deleteDisabled = computed(() => {
  if (!actionVersion.value) return true
  if (actionVersion.value.id === props.activeVersionId) return true
  return props.versions.length <= 1
})

function openActions(version: ResourceVersion) {
  actionVersion.value = version
}

function emitMove(direction: 'up' | 'down') {
  if (!actionVersion.value) return
  emit('move-version', { versionId: actionVersion.value.id, direction })
  actionVersion.value = null
}

function emitDelete() {
  if (!actionVersion.value || deleteDisabled.value) return
  emit('delete-version', actionVersion.value.id)
  actionVersion.value = null
}
</script>

<style scoped>
.mobile-version-bar {
  flex-shrink: 0;
  height: 100px; /* Slightly shorter than desktop for mobile */
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  flex-direction: column;
}

.version-bar-header {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.version-list-horizontal {
  display: flex;
  padding: 0 10px 10px 10px;
  gap: 10px;
}

.version-card-horizontal {
  flex-shrink: 0;
  width: 160px; /* Narrower for mobile screens */
  height: 56px;
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.2s;
}

.version-card-horizontal:active {
  background-color: var(--el-fill-color-light);
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
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
}

.version-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 4px;
  flex: 1;
}

.version-date {
  font-weight: normal;
  font-size: 10px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.version-card-footer {
  display: flex;
  justify-content: flex-end;
  height: 20px;
  align-items: center;
  gap: 4px;
}

.card-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--el-text-color-secondary);
}

/* 操作面板 */
.sheet-overlay { position: fixed; inset: 0; z-index: 2200; background: rgba(0, 0, 0, 0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 520px; background: var(--el-bg-color); border-radius: 16px 16px 0 0; padding: 0 14px 12px; display: flex; flex-direction: column; }
.sheet-handle { width: 36px; height: 4px; border-radius: 2px; background: var(--el-border-color); margin: 8px auto 4px; }
.sheet-title { padding: 8px 2px; font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); word-break: break-all; }
.sheet-item { height: 46px; border: none; background: transparent; font-size: 15px; color: var(--el-text-color-primary); border-top: 0.5px solid var(--el-border-color-lighter); text-align: left; padding: 0 4px; }
.sheet-item:disabled { color: var(--el-text-color-disabled); }
.sheet-item.danger { color: var(--el-color-danger); }
.sheet-cancel { height: 46px; margin-top: 8px; border: none; border-radius: 10px; background: var(--el-fill-color-light); font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.2s ease; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }

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
  width: 110px;
}

.special-kb-card:active {
  background-color: var(--el-color-primary-light-8);
}

.special-kb-card.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.special-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  color: var(--el-color-primary);
}

.special-icon {
  margin-bottom: 2px;
}

.special-label {
  font-size: 11px;
  font-weight: 600;
}
</style>
