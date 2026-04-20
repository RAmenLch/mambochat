<template>
  <div class="mcp-manager">
    <div class="header">
      <div class="title-section">
        <h2>{{ t('settings.mcp.title') }}</h2>
        <span class="subtitle">{{ t('settings.mcp.subtitle') }}</span>
      </div>
      <el-button type="primary" :icon="Plus" @click="handleCreate">{{ t('settings.mcp.add') }}</el-button>
    </div>

    <el-table :data="availableServices" style="width: 100%" v-loading="isLoading">
      <el-table-column prop="name" :label="t('settings.mcp.columns.name')" min-width="150">
        <template #default="{ row }">
          <div class="name-cell">
            <span class="name-text">{{ row.name }}</span>
            <el-tag v-if="row.isSystem" type="info" size="small" effect="plain">{{ t('settings.mcp.system') }}</el-tag>
          </div>
          <div class="description-text" v-if="row.description">{{ row.description }}</div>
        </template>
      </el-table-column>

      <el-table-column prop="transportType" :label="t('settings.mcp.columns.type')" width="100">
        <template #default="{ row }">
          <el-tag :type="row.transportType === 'stdio' ? 'info' : 'warning'">
            {{ row.transportType.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.mcp.columns.config')" min-width="180">
        <template #default="{ row }">
          <div v-if="row.transportType === 'stdio'" class="config-detail">
            <div class="detail-item"><strong>Cmd:</strong> {{ row.command }}</div>
            <div class="detail-item" v-if="row.args && row.args.length">
              <strong>Args:</strong> {{ row.args.join(' ') }}
            </div>
          </div>
          <div v-else class="config-detail">
            <div class="detail-item"><strong>URL:</strong> {{ row.url }}</div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="isEnabled" :label="t('settings.mcp.columns.enabled')" width="80">
        <template #default="{ row }">
          <el-tag :type="row.isEnabled ? 'success' : 'danger'" effect="dark" size="small">
            {{ row.isEnabled ? 'ON' : 'OFF' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.mcp.columns.status')" width="100" align="center">
        <template #default="{ row }">
          <div class="health-status-cell">
            <div
              class="status-dot"
              :class="getStatusClass(row.last_status)"
              :title="getStatusTitle(row.last_status)"
            ></div>
            <el-button
              link
              type="primary"
              :icon="Refresh"
              :loading="testingRowIds.has(row.id)"
              @click="handleTestConnection(row)"
              :title="t('settings.mcp.testConnection')"
            />
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.mcp.columns.monitor')" min-width="160">
        <template #default="{ row }">
          <div class="monitor-cell">
            <div v-if="row.last_test_at" class="last-test-time">
              {{ formatTime(row.last_test_at) }}
            </div>
            <div v-else class="text-placeholder">-</div>

            <div
              v-if="row.last_status === 'unhealthy' && row.last_error"
              class="error-trigger"
              @click="showErrorDetail(row)"
            >
              <el-icon><WarningFilled /></el-icon>
              <span>{{ t('settings.mcp.checkError') }}</span>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.mcp.columns.toolManage')" width="100" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openToolDrawer(row.id)">{{ t('settings.mcp.columns.viewTool') }}</el-button>
        </template>
      </el-table-column>

      <el-table-column :label="t('provider.list.action')" width="150" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.isSystem">
            <el-button link type="primary" @click="handleEdit(row)">{{ t('common.action.edit') }}</el-button>
            <el-popconfirm
              :title="t('settings.mcp.deleteConfirm')"
              :confirm-button-text="t('common.action.delete')"
              :cancel-button-text="t('common.action.cancel')"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button link type="danger">{{ t('common.action.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
          <template v-else>
            <el-button link disabled :title="t('settings.mcp.systemEditTip')">{{ t('common.action.edit') }}</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <McpFormDialog
      v-model:visible="dialogVisible"
      :initial-data="editingMcp"
      :is-submitting="isSubmitting"
      @save="handleSave"
    />

    <el-dialog
      v-model="errorDialogVisible"
      :title="t('settings.mcp.errorDetail.title')"
      width="600px"
      append-to-body
    >
      <div class="error-detail-content">
        <div class="error-meta">
          <p><strong>{{ t('settings.mcp.errorDetail.serviceName') }}:</strong> {{ currentErrorMcp?.name }}</p>
          <p><strong>{{ t('settings.mcp.errorDetail.occurredAt') }}:</strong> {{ currentErrorMcp?.last_test_at ? formatTime(currentErrorMcp.last_test_at) : t('common.status.unspecified') }}</p>
        </div>
        <el-alert
          :title="t('settings.mcp.errorDetail.connectionFailed')"
          type="error"
          :closable="false"
          show-icon
          class="mb-2"
        />
        <div class="error-stack-trace">
          <pre>{{ currentErrorMcp?.last_error }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="errorDialogVisible = false">{{ t('common.action.close') }}</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="toolDrawerVisible"
      size="800px"
      destroy-on-close
    >
      <template #header>
        <div class="drawer-header">
          <span class="drawer-title">{{ t('settings.mcp.toolDrawer.title') }}</span>
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="isSyncingTools"
            @click="handleSyncTools"
          >
            {{ t('settings.mcp.toolDrawer.sync') }}
          </el-button>
        </div>
      </template>

      <el-table :data="currentServerTools" style="width: 100%" v-loading="isToolsLoading">
        <el-table-column :label="t('settings.mcp.columns.toolInfo')" min-width="180">
          <template #default="{ row }">
            <div class="tool-info-cell">
              <span>{{ row.name }}</span>
              <el-tooltip placement="top" effect="light">
                <template #content>
                  <div class="tool-tooltip-content">
                    <p v-if="row.description"><strong>{{ t('settings.mcp.toolDrawer.description') }}</strong> {{ row.description }}</p>
                    <p><strong>Input Schema:</strong></p>
                    <pre>{{ formatJson(row.input_schema) }}</pre>
                  </div>
                </template>
                <el-icon class="info-icon"><InfoFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('settings.mcp.columns.onlineStatus')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : 'info'" size="small">
              {{ row.status === 'online' ? t('settings.mcp.columns.online') : t('settings.mcp.columns.offline') }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('settings.mcp.columns.enableStatus')" width="100">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_enabled"
              @change="(val: boolean | string | number) => handleToolSwitchChange(row, Boolean(val))"
            />
          </template>
        </el-table-column>

        <el-table-column :label="t('settings.mcp.columns.reviewMode')" width="140">
          <template #default="{ row }">
            <el-select
              :model-value="row.review_mode"
              @change="(val: ToolReviewMode) => handleToolReviewChange(row, val)"
              size="small"
            >
              <el-option :label="t('settings.mcp.columns.reviewNone')" value="none" />
              <el-option :label="t('settings.mcp.columns.reviewRequire')" value="require_review" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column :label="t('settings.mcp.columns.lastSyncTime')" width="160">
          <template #default="{ row }">
            {{ formatTime(row.last_synced_at) }}
          </template>
        </el-table-column>

        <el-table-column :label="t('common.action.operate')" width="80" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              :title="t('settings.mcp.toolDrawer.deleteConfirm')"
              @confirm="handleDeleteTool(row)"
            >
              <template #reference>
                <el-button link type="danger" :disabled="row.status === 'online'">
                  {{ t('common.action.delete') }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { Plus, Refresh, WarningFilled, InfoFilled } from '@element-plus/icons-vue';
import { useMcpStore } from '@/stores/mcpStore';
import type { McpServer, McpCreateRequest, McpHealthStatus, McpToolResponse, ToolReviewMode } from '@/api/types';
import McpFormDialog from './dialogs/McpFormDialog.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const mcpStore = useMcpStore();
const { availableServices, currentServerTools } = storeToRefs(mcpStore);

const isLoading = ref(false);
const dialogVisible = ref(false);
const isSubmitting = ref(false);
const editingMcp = ref<McpServer | null>(null);

const testingRowIds = reactive(new Set<string>());

const errorDialogVisible = ref(false);
const currentErrorMcp = ref<McpServer | null>(null);

const toolDrawerVisible = ref(false);
const activeServerId = ref('');
const isToolsLoading = ref(false);
const isSyncingTools = ref(false);

onMounted(async () => {
  isLoading.value = true;
  await mcpStore.fetchAvailableServices();
  isLoading.value = false;
});

const handleCreate = () => {
  editingMcp.value = null;
  dialogVisible.value = true;
};

const handleEdit = (row: McpServer) => {
  editingMcp.value = row;
  dialogVisible.value = true;
};

const handleDelete = async (row: McpServer) => {
  try {
    await mcpStore.deleteMcp(row.id);
    ElMessage.success(t('settings.mcp.deleteSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.deleteFailed'));
  }
};

const handleSave = async (data: McpCreateRequest) => {
  isSubmitting.value = true;
  try {
    if (editingMcp.value) {
      await mcpStore.updateMcp(editingMcp.value.id, data);
      ElMessage.success(t('settings.mcp.updateSuccess'));
    } else {
      await mcpStore.createMcp(data);
      ElMessage.success(t('settings.mcp.createSuccess'));
    }
    dialogVisible.value = false;
  } catch (error) {
    ElMessage.error(editingMcp.value ? t('settings.mcp.updateFailed') : t('settings.mcp.createFailed'));
  } finally {
    isSubmitting.value = false;
  }
};

const handleTestConnection = async (row: McpServer) => {
  if (testingRowIds.has(row.id)) return;

  testingRowIds.add(row.id);
  try {
    await mcpStore.testConnection(row.id);
    ElMessage.success(t('settings.mcp.testSuccess', { name: row.name }));
  } catch (error) {
    ElMessage.error(t('settings.mcp.testFailed', { name: row.name }));
  } finally {
    testingRowIds.delete(row.id);
  }
};

const showErrorDetail = (row: McpServer) => {
  currentErrorMcp.value = row;
  errorDialogVisible.value = true;
};

const openToolDrawer = async (serverId: string) => {
  activeServerId.value = serverId;
  toolDrawerVisible.value = true;
  isToolsLoading.value = true;
  try {
    await mcpStore.fetchTools(serverId);
  } catch (error) {
    ElMessage.error(t('settings.mcp.toolDrawer.fetchToolsFailed'));
  } finally {
    isToolsLoading.value = false;
  }
};

const handleSyncTools = async () => {
  if (!activeServerId.value) return;
  isSyncingTools.value = true;
  try {
    await mcpStore.syncTools(activeServerId.value);
    ElMessage.success(t('settings.mcp.toolDrawer.syncSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.toolDrawer.syncFailed'));
  } finally {
    isSyncingTools.value = false;
  }
};

const handleToolSwitchChange = async (row: McpToolResponse, val: boolean) => {
  try {
    await mcpStore.updateToolConfig(row.id, { is_enabled: val });
    ElMessage.success(t('settings.mcp.toolDrawer.updateSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.toolDrawer.updateFailed'));
  }
};

const handleToolReviewChange = async (row: McpToolResponse, val: ToolReviewMode) => {
  try {
    await mcpStore.updateToolConfig(row.id, { review_mode: val });
    ElMessage.success(t('settings.mcp.toolDrawer.updateSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.toolDrawer.updateFailed'));
  }
};

const handleDeleteTool = async (row: McpToolResponse) => {
  try {
    await mcpStore.removeTool(row.id);
    ElMessage.success(t('settings.mcp.toolDrawer.deleteSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.toolDrawer.deleteFailed'));
  }
};

const getStatusClass = (status: McpHealthStatus) => {
  switch (status) {
    case 'healthy': return 'status-healthy';
    case 'unhealthy': return 'status-unhealthy';
    default: return 'status-unknown';
  }
};

const getStatusTitle = (status: McpHealthStatus) => {
  switch (status) {
    case 'healthy': return t('chat.toolbar.mcpStatus.healthy');
    case 'unhealthy': return t('chat.toolbar.mcpStatus.unhealthy');
    default: return t('chat.toolbar.mcpStatus.unknown');
  }
};

const formatTime = (isoString: string) => {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleString(t('locale') === 'en' ? 'en-US' : 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

const formatJson = (obj: Record<string, unknown> | null) => {
  if (!obj) return t('settings.mcp.toolDrawer.noSchema');
  try {
    return JSON.stringify(obj, null, 2);
  } catch (e) {
    return String(obj);
  }
};
</script>

<style scoped>
.mcp-manager {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.title-section h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
}

.subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-text {
  font-weight: 500;
}

.description-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.config-detail {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.detail-item {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.health-status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-healthy {
  background-color: var(--el-color-success);
  box-shadow: 0 0 4px var(--el-color-success-light-5);
}

.status-unhealthy {
  background-color: var(--el-color-danger);
  box-shadow: 0 0 4px var(--el-color-danger-light-5);
}

.status-unknown {
  background-color: var(--el-color-info-light-3);
  border: 1px solid var(--el-color-info-light-5);
}

.monitor-cell {
  display: flex;
  flex-direction: column;
  font-size: 12px;
}

.last-test-time {
  color: var(--el-text-color-regular);
}

.text-placeholder {
  color: var(--el-text-color-placeholder);
}

.error-trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-color-danger);
  cursor: pointer;
  margin-top: 2px;
  transition: opacity 0.2s;
}

.error-trigger:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.error-detail-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.error-meta p {
  margin: 4px 0;
  font-size: 14px;
}

.mb-2 {
  margin-bottom: 8px;
}

.error-stack-trace {
  background-color: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  max-height: 300px;
  overflow-y: auto;
}

.error-stack-trace pre {
  margin: 0;
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-color-danger-dark-2);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.drawer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tool-info-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-icon {
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.tool-tooltip-content {
  max-width: 400px;
  max-height: 300px;
  overflow: auto;
}

.tool-tooltip-content p {
  margin: 4px 0;
}

.tool-tooltip-content pre {
  margin: 8px 0 0 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 12px;
  background-color: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
}
</style>
