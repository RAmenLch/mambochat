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

      <!-- 新增：健康状态列 -->
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

      <!-- 新增：监测详情列 -->
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

    <!-- 故障详情弹窗 -->
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { Plus, Refresh, WarningFilled } from '@element-plus/icons-vue';
import { useMcpStore } from '@/stores/mcpStore';
import type { McpServer, McpCreateRequest, McpHealthStatus } from '@/api/types';
import McpFormDialog from './dialogs/McpFormDialog.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const mcpStore = useMcpStore();
const { availableServices } = storeToRefs(mcpStore);

const isLoading = ref(false);
const dialogVisible = ref(false);
const isSubmitting = ref(false);
const editingMcp = ref<McpServer | null>(null);

// 测试状态管理
const testingRowIds = reactive(new Set<string>());

// 错误详情弹窗管理
const errorDialogVisible = ref(false);
const currentErrorMcp = ref<McpServer | null>(null);

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

// --- Helpers ---

const getStatusClass = (status: McpHealthStatus) => {
  switch (status) {
    case 'healthy': return 'status-healthy';
    case 'unhealthy': return 'status-unhealthy';
    default: return 'status-unknown';
  }
};

const getStatusTitle = (status: McpHealthStatus) => {
  // 复用 chat.toolbar.mcpStatus 中的翻译
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
</script>

<style scoped>
/* 样式保持不变 */
.mcp-manager {
  height: 100%;
  display: flex;
  flex-direction: column;
}
/* ... (省略其余样式代码，与原文件一致) ... */
</style>
