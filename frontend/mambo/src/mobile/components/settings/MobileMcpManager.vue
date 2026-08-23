<!-- MobileMcpManager.vue — 移动端 MCP 管理（P3 重构） -->
<template>
  <div class="mobile-mcp-manager">
    <div class="list-header">
      <span class="header-title">MCP</span>
      <button class="header-add-btn" @click="handleCreate">
        <el-icon :size="16"><Plus /></el-icon>
      </button>
    </div>

    <div v-if="isLoading" class="loading-container">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <div v-else class="mcp-list">
      <div v-if="availableServices.length === 0" class="empty-state">
        <el-empty :description="t('settings.mcp.empty')" />
      </div>

      <div v-for="item in availableServices" :key="item.id" class="mcp-card">
        <div class="card-top">
          <div class="card-title-row">
            <span class="card-name">{{ item.name }}</span>
            <el-tag v-if="item.isSystem" type="info" size="small" effect="plain">{{ t('settings.mcp.system') }}</el-tag>
          </div>
          <el-switch
            :model-value="item.isEnabled"
            size="small"
            @change="(val: string | number | boolean) => handleToggleEnabled(item, val as boolean)"
          />
        </div>

        <div class="card-desc" v-if="item.description">{{ item.description }}</div>

        <div class="card-meta">
          <span class="meta-tag" :class="'tag-' + item.transportType">{{ item.transportType.toUpperCase() }}</span>
          <div class="health-badge" :class="getStatusClass(item.last_status)">
            <span class="health-dot"></span>
            <span class="health-text">{{ getStatusText(item.last_status) }}</span>
          </div>
        </div>

        <div class="card-config">
          <template v-if="item.transportType === 'stdio'">
            <span class="cfg-label">Cmd:</span>
            <code class="cfg-value">{{ item.command }}</code>
            <span v-if="item.args && item.args.length" class="cfg-args">{{ item.args.join(' ') }}</span>
          </template>
          <template v-else>
            <span class="cfg-label">URL:</span>
            <code class="cfg-value">{{ item.url }}</code>
          </template>
        </div>

        <div v-if="item.last_status === 'unhealthy' && item.last_error" class="card-error" @click="showErrorDetail(item)">
          <el-icon :size="14"><WarningFilled /></el-icon>
          <span>{{ t('settings.mcp.checkError') }}</span>
          <el-icon :size="14" class="error-arrow"><ArrowRight /></el-icon>
        </div>

        <div class="card-footer">
          <button class="card-action-btn" :disabled="item.isSystem" @click="handleEdit(item)">
            {{ t('common.action.edit') }}
          </button>
          <el-popconfirm :title="t('settings.mcp.deleteConfirm')" @confirm="handleDelete(item)" :disabled="item.isSystem">
            <template #reference>
              <button class="card-action-btn action-danger" :disabled="item.isSystem">
                {{ t('common.action.delete') }}
              </button>
            </template>
          </el-popconfirm>
          <button class="card-action-btn action-test" :disabled="testingRowIds.has(item.id)" @click="handleTestConnection(item)">
            <el-icon :size="14" :class="{ 'is-loading': testingRowIds.has(item.id) }"><Refresh /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <!-- Bottom Sheet: MCP 表单 -->
    <MobileMcpFormDialog
      v-model:visible="dialogVisible"
      :initial-data="editingMcp"
      :is-submitting="isSubmitting"
      @save="handleSave"
    />

    <!-- Bottom Sheet: 错误详情 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="errorDialogVisible" class="sheet-overlay" @click="errorDialogVisible = false">
          <div class="sheet-panel sheet-error-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ t('settings.mcp.errorDetail.title') }}</span>
              <button class="sheet-close" @click="errorDialogVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="sheet-body">
              <div class="error-meta">
                <p><strong>{{ t('settings.mcp.errorDetail.serviceName') }}:</strong> {{ currentErrorMcp?.name }}</p>
                <p><strong>{{ t('settings.mcp.errorDetail.occurredAt') }}:</strong> {{ currentErrorMcp?.last_test_at ? formatTime(currentErrorMcp.last_test_at) : t('common.status.unspecified') }}</p>
              </div>
              <el-alert :title="t('settings.mcp.errorDetail.connectionFailed')" type="error" :closable="false" show-icon style="margin-bottom: 12px" />
              <pre class="error-stack">{{ currentErrorMcp?.last_error }}</pre>
            </div>
            <div class="sheet-footer">
              <button class="footer-btn footer-btn-cancel" @click="errorDialogVisible = false">{{ t('common.action.close') }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { Plus, Refresh, WarningFilled, ArrowRight, Loading, Close } from '@element-plus/icons-vue';
import { useMcpStore } from '@/stores/mcpStore';
import type { McpServer, McpCreateRequest, McpHealthStatus } from '@/api/types';
import MobileMcpFormDialog from './dialogs/MobileMcpFormDialog.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const mcpStore = useMcpStore();
const { availableServices } = storeToRefs(mcpStore);

const isLoading = ref(false);
const dialogVisible = ref(false);
const isSubmitting = ref(false);
const editingMcp = ref<McpServer | null>(null);
const testingRowIds = reactive(new Set<string>());
const errorDialogVisible = ref(false);
const currentErrorMcp = ref<McpServer | null>(null);

onMounted(async () => { isLoading.value = true; await mcpStore.fetchAvailableServices(); isLoading.value = false; });

const handleCreate = () => { editingMcp.value = null; dialogVisible.value = true; };
const handleEdit = (row: McpServer) => { editingMcp.value = row; dialogVisible.value = true; };

const handleToggleEnabled = async (row: McpServer, val: boolean) => {
  try {
    await mcpStore.updateMcp(row.id, {
      name: row.name, description: row.description, transportType: row.transportType,
      isEnabled: val, command: row.command, args: row.args, env: row.env, url: row.url
    });
    ElMessage.success(t('settings.mcp.updateSuccess'));
  } catch { ElMessage.error(t('settings.mcp.updateFailed')); await mcpStore.fetchAvailableServices(); }
};

const handleDelete = async (row: McpServer) => {
  try { await mcpStore.deleteMcp(row.id); ElMessage.success(t('settings.mcp.deleteSuccess')); }
  catch { ElMessage.error(t('settings.mcp.deleteFailed')); }
};

const handleSave = async (data: McpCreateRequest) => {
  isSubmitting.value = true;
  try {
    if (editingMcp.value) { await mcpStore.updateMcp(editingMcp.value.id, data); ElMessage.success(t('settings.mcp.updateSuccess')); }
    else { await mcpStore.createMcp(data); ElMessage.success(t('settings.mcp.createSuccess')); }
    dialogVisible.value = false;
  } catch { ElMessage.error(editingMcp.value ? t('settings.mcp.updateFailed') : t('settings.mcp.createFailed')); }
  finally { isSubmitting.value = false; }
};

const handleTestConnection = async (row: McpServer) => {
  if (testingRowIds.has(row.id)) return;
  testingRowIds.add(row.id);
  try { await mcpStore.testConnection(row.id); ElMessage.success(t('settings.mcp.testSuccess', { name: row.name })); }
  catch { ElMessage.error(t('settings.mcp.testFailed', { name: row.name })); }
  finally { testingRowIds.delete(row.id); }
};

const showErrorDetail = (row: McpServer) => { currentErrorMcp.value = row; errorDialogVisible.value = true; };

const statusClassMap: Record<string, string> = { healthy: 'status-healthy', unhealthy: 'status-unhealthy' };
const getStatusClass = (s: McpHealthStatus) => (s ? statusClassMap[s] : '') || 'status-unknown';
const statusTextMap: Record<string, string> = { healthy: t('chat.toolbar.mcpStatus.healthy'), unhealthy: t('chat.toolbar.mcpStatus.unhealthy') };
const getStatusText = (s: McpHealthStatus) => (s ? statusTextMap[s] : '') || t('chat.toolbar.mcpStatus.unknown');

const formatTime = (iso: string) => {
  if (!iso) return '-';
  return new Date(iso).toLocaleString(t('locale') === 'en' ? 'en-US' : 'zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};
</script>

<style scoped>
.mobile-mcp-manager { height: 100%; display: flex; flex-direction: column; background: var(--color-background); }

.list-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; flex-shrink: 0;
  background: rgba(255,255,255,0.72); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0,0,0,0.08); z-index: 5;
}
.header-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.header-add-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; border-radius: 50%; background: var(--el-color-primary); color: #fff; cursor: pointer; }

.loading-container { display: flex; justify-content: center; align-items: center; height: 200px; }
.mcp-list { flex: 1; overflow-y: auto; padding: 8px 12px; -webkit-overflow-scrolling: touch; }

.mcp-card {
  background: var(--color-background-soft); border-radius: 12px; padding: 14px;
  margin-bottom: 10px; border: 0.5px solid rgba(0,0,0,0.05);
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}

.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.card-title-row { display: flex; align-items: center; gap: 6px; }
.card-name { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.card-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; line-height: 1.4; }

.card-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.meta-tag { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 4px; }
.tag-stdio { color: var(--el-color-info); background: var(--el-color-info-light-9); }
.tag-sse { color: var(--el-color-warning-dark-2); background: var(--el-color-warning-light-9); }

.health-badge { display: flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.health-dot { width: 6px; height: 6px; border-radius: 50%; }
.health-text { font-weight: 500; }
.status-healthy { background: var(--el-color-success-light-9); color: var(--el-color-success); }
.status-healthy .health-dot { background: var(--el-color-success); }
.status-unhealthy { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }
.status-unhealthy .health-dot { background: var(--el-color-danger); }
.status-unknown { background: var(--el-fill-color-light); color: var(--el-text-color-secondary); }
.status-unknown .health-dot { background: var(--el-text-color-placeholder); }

.card-config { font-size: 12px; padding: 6px 8px; background: var(--el-bg-color); border-radius: 6px; margin-bottom: 8px; word-break: break-all; }
.cfg-label { font-weight: 600; margin-right: 4px; color: var(--el-text-color-secondary); }
.cfg-value { font-family: monospace; font-size: 12px; }
.cfg-args { color: var(--el-text-color-secondary); margin-left: 4px; }

.card-error { display: flex; align-items: center; gap: 4px; padding: 6px 0; color: var(--el-color-danger); font-size: 12px; border-top: 0.5px solid rgba(0,0,0,0.05); cursor: pointer; }
.card-error span { flex: 1; }
.error-arrow { flex-shrink: 0; }

.card-footer { display: flex; justify-content: flex-end; gap: 6px; padding-top: 8px; border-top: 0.5px solid rgba(0,0,0,0.05); margin-top: 4px; }
.card-action-btn { height: 28px; padding: 0 10px; font-size: 12px; font-weight: 500; color: var(--el-text-color-regular); background: var(--el-fill-color); border: none; border-radius: 14px; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.card-action-btn:active { background: var(--el-fill-color-dark); }
.card-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-danger { color: var(--el-color-danger); }
.action-test { width: 28px; padding: 0; display: flex; align-items: center; justify-content: center; }

/* ===== Error Sheet ===== */
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; max-height: 70vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-error-panel { max-height: 60vh; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 16px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-body { flex: 1; overflow-y: auto; padding: 4px 16px 12px; -webkit-overflow-scrolling: touch; }
.sheet-footer { padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; }
.footer-btn { width: 100%; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; cursor: pointer; }
.footer-btn-cancel { color: var(--el-text-color-primary); background: var(--el-fill-color-light); }

.error-meta p { margin: 2px 0 8px; font-size: 13px; }
.error-stack { background: var(--el-fill-color-light); padding: 10px; border-radius: 8px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

@media (prefers-color-scheme: dark) {
  .list-header { background: rgba(30,30,30,0.72); border-bottom-color: rgba(255,255,255,0.08); }
  .mcp-card { border-color: rgba(255,255,255,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
  .sheet-handle { background: rgba(255,255,255,0.2); }
  .sheet-footer { border-top-color: rgba(255,255,255,0.08); }
  .card-footer, .card-error { border-color: rgba(255,255,255,0.05); }
}
</style>
