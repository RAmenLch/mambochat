<!-- frontend/mambo/src/mobile/components/settings/dialogs/MobileMcpToolSheet.vue — 移动端 MCP 工具级管理 -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="sheet-overlay" @click="close">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>

          <div class="sheet-header">
            <div class="header-text">
              <span class="sheet-title">{{ t('settings.mcp.toolDrawer.title') }}</span>
              <span class="sheet-subtitle">{{ serverName }}</span>
            </div>
            <button class="sheet-close" @click="close">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <div class="tool-actions">
              <el-button size="small" type="primary" :loading="isSyncing" @click="handleSync">
                {{ t('settings.mcp.toolDrawer.sync') }}
              </el-button>
              <span class="tool-count">{{ tools.length }}</span>
            </div>

            <el-skeleton v-if="isLoading" :rows="4" animated />

            <div v-else-if="tools.length === 0" class="empty-hint">
              {{ t('settings.mcp.toolDrawer.noTools') }}
            </div>

            <div v-else class="tool-list">
              <div v-for="tool in tools" :key="tool.id" class="tool-card">
                <div class="tool-card-head">
                  <span class="tool-name">{{ tool.name }}</span>
                  <el-tag :type="tool.status === 'online' ? 'success' : 'info'" size="small">
                    {{ tool.status === 'online' ? t('settings.mcp.columns.online') : t('settings.mcp.columns.offline') }}
                  </el-tag>
                </div>

                <div v-if="tool.description" class="tool-desc">{{ tool.description }}</div>

                <div class="tool-row">
                  <span class="tool-row-label">{{ t('settings.mcp.columns.enableStatus') }}</span>
                  <el-switch
                    :model-value="tool.is_enabled"
                    @change="(val: string | number | boolean) => handleToggleEnabled(tool, Boolean(val))"
                  />
                </div>

                <div class="tool-row">
                  <span class="tool-row-label">{{ t('settings.mcp.columns.reviewMode') }}</span>
                  <el-select
                    :model-value="tool.review_mode"
                    size="small"
                    class="tool-select"
                    @change="(val: ToolReviewMode) => handleReviewModeChange(tool, val)"
                  >
                    <el-option :label="t('settings.mcp.columns.reviewNone')" value="none" />
                    <el-option :label="t('settings.mcp.columns.reviewRequire')" value="require_review" />
                  </el-select>
                </div>

                <div class="tool-row">
                  <span class="tool-row-label">{{ t('settings.mcp.columns.lastSyncTime') }}</span>
                  <span class="tool-row-value">{{ formatTime(tool.last_synced_at) }}</span>
                </div>

                <div class="tool-card-foot">
                  <el-button size="small" type="danger" plain :disabled="tool.status === 'online'" @click="handleDelete(tool)">
                    {{ t('common.action.delete') }}
                  </el-button>
                </div>
              </div>
            </div>
          </div>

          <button class="sheet-cancel" @click="close">{{ t('common.action.close') }}</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { useMcpStore } from '@/stores/mcpStore'
import type { McpToolResponse, ToolReviewMode } from '@/api/types'

const props = defineProps<{
  visible: boolean
  serverId: string | null
  serverName: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const { t, locale } = useI18n()
const mcpStore = useMcpStore()
const { currentServerTools } = storeToRefs(mcpStore)

const tools = computed<McpToolResponse[]>(() => currentServerTools.value ?? [])
const isLoading = ref(false)
const isSyncing = ref(false)

function close() {
  emit('update:visible', false)
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadTools() {
  if (!props.serverId) return
  isLoading.value = true
  try {
    await mcpStore.fetchTools(props.serverId)
  } catch {
    ElMessage.error(t('settings.mcp.toolDrawer.fetchToolsFailed'))
  } finally {
    isLoading.value = false
  }
}

async function handleSync() {
  if (!props.serverId || isSyncing.value) return
  isSyncing.value = true
  try {
    await mcpStore.syncTools(props.serverId)
    ElMessage.success(t('settings.mcp.toolDrawer.syncSuccess'))
  } catch {
    ElMessage.error(t('settings.mcp.toolDrawer.syncFailed'))
  } finally {
    isSyncing.value = false
  }
}

async function handleToggleEnabled(tool: McpToolResponse, enabled: boolean) {
  try {
    await mcpStore.updateToolConfig(tool.id, { is_enabled: enabled })
  } catch {
    ElMessage.error(t('settings.mcp.toolDrawer.updateFailed'))
    await loadTools()
  }
}

async function handleReviewModeChange(tool: McpToolResponse, mode: ToolReviewMode) {
  try {
    await mcpStore.updateToolConfig(tool.id, { review_mode: mode })
    ElMessage.success(t('settings.mcp.toolDrawer.updateSuccess'))
  } catch {
    ElMessage.error(t('settings.mcp.toolDrawer.updateFailed'))
    await loadTools()
  }
}

async function handleDelete(tool: McpToolResponse) {
  try {
    await ElMessageBox.confirm(
      t('settings.mcp.toolDrawer.deleteConfirm'),
      t('common.action.delete'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await mcpStore.removeTool(tool.id)
    ElMessage.success(t('settings.mcp.toolDrawer.deleteSuccess'))
  } catch {
    ElMessage.error(t('settings.mcp.toolDrawer.deleteFailed'))
  }
}

watch(
  () => props.visible,
  visible => {
    if (visible) loadTools()
  },
)
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0, 0, 0, 0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 560px; max-height: 88vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0, 0, 0, 0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.header-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-subtitle { font-size: 12px; color: var(--el-text-color-secondary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 16px 8px; -webkit-overflow-scrolling: touch; }
.sheet-cancel { height: 44px; margin: 8px 16px; margin-bottom: max(10px, env(safe-area-inset-bottom)); border: none; border-radius: 10px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); font-size: 15px; font-weight: 600; }

.tool-actions { display: flex; align-items: center; gap: 8px; padding: 4px 0 10px; }
.tool-count { font-size: 12px; color: var(--el-text-color-secondary); }

.tool-list { display: flex; flex-direction: column; gap: 10px; }
.tool-card { padding: 10px 12px; border-radius: 10px; background: var(--el-fill-color-light); display: flex; flex-direction: column; gap: 6px; }
.tool-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tool-name { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); word-break: break-all; }
.tool-desc { font-size: 12px; line-height: 1.4; color: var(--el-text-color-secondary); }
.tool-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; }
.tool-row-label { color: var(--el-text-color-secondary); }
.tool-row-value { color: var(--el-text-color-primary); }
.tool-select { width: 150px; }
.tool-card-foot { display: flex; justify-content: flex-end; }

.empty-hint { padding: 16px 0; text-align: center; font-size: 13px; color: var(--el-text-color-placeholder); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }
</style>
