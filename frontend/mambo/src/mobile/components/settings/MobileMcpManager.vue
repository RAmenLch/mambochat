<template>
  <div class="mobile-mcp-manager">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <!-- 列表内容 -->
    <div v-else class="mcp-list">
      <div v-if="availableServices.length === 0" class="empty-state">
        <el-empty :description="t('settings.mcp.empty')" />
      </div>

      <div
        v-for="item in availableServices"
        :key="item.id"
        class="mcp-card"
      >
        <!-- 卡片头部：名称 + 启用开关 -->
        <div class="card-header">
          <div class="title-area">
            <span class="name">{{ item.name }}</span>
            <el-tag v-if="item.isSystem" type="info" size="small" effect="plain">
              {{ t('settings.mcp.system') }}
            </el-tag>
          </div>
          <!-- 修复点：添加 as boolean 断言 -->
          <el-switch
            :model-value="item.isEnabled"
            size="small"
            @change="(val) => handleToggleEnabled(item, val as boolean)"
          />
        </div>

        <!-- 描述 -->
        <div class="card-desc" v-if="item.description">
          {{ item.description }}
        </div>

        <!-- 元信息：类型 + 健康状态 -->
        <div class="card-meta">
          <el-tag
            :type="item.transportType === 'stdio' ? 'info' : 'warning'"
            size="small"
          >
            {{ item.transportType.toUpperCase() }}
          </el-tag>

          <div class="health-status">
             <div
              class="status-dot"
              :class="getStatusClass(item.last_status)"
            ></div>
            <span class="status-text">{{ getStatusText(item.last_status) }}</span>
            <!-- 测试按钮 -->
            <el-button
              link
              type="primary"
              size="small"
              :icon="Refresh"
              :loading="testingRowIds.has(item.id)"
              @click="handleTestConnection(item)"
              style="margin-left: 8px;"
            />
          </div>
        </div>

        <!-- 配置预览 -->
        <div class="card-config">
          <template v-if="item.transportType === 'stdio'">
            <span class="label">Cmd:</span>
            <span class="value">{{ item.command }}</span>
            <span v-if="item.args && item.args.length" class="args">
              {{ item.args.join(' ') }}
            </span>
          </template>
          <template v-else>
            <span class="label">URL:</span>
            <span class="value">{{ item.url }}</span>
          </template>
        </div>

        <!-- 错误提示 -->
        <div
          v-if="item.last_status === 'unhealthy' && item.last_error"
          class="card-error"
          @click="showErrorDetail(item)"
        >
          <el-icon><WarningFilled /></el-icon>
          <span>{{ t('settings.mcp.checkError') }}</span>
          <el-icon class="arrow"><ArrowRight /></el-icon>
        </div>

        <!-- 操作按钮 -->
        <div class="card-actions">
          <el-button
            size="small"
            :disabled="item.isSystem"
            @click="handleEdit(item)"
          >
            {{ t('common.action.edit') }}
          </el-button>
          <el-popconfirm
            :title="t('settings.mcp.deleteConfirm')"
            @confirm="handleDelete(item)"
            :disabled="item.isSystem"
          >
            <template #reference>
              <el-button size="small" type="danger" :disabled="item.isSystem">
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>

    <!-- 悬浮添加按钮 -->
    <el-button
      class="fab-add"
      type="primary"
      :icon="Plus"
      circle
      size="large"
      @click="handleCreate"
    />

    <!-- 表单弹窗 -->
    <MobileMcpFormDialog
      v-model:visible="dialogVisible"
      :initial-data="editingMcp"
      :is-submitting="isSubmitting"
      @save="handleSave"
    />

    <!-- 错误详情弹窗 -->
    <el-dialog
      v-model="errorDialogVisible"
      :title="t('settings.mcp.errorDetail.title')"
      width="90%"
      append-to-body
      class="error-dialog-mobile"
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
          style="margin-bottom: 12px;"
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
import { Plus, Refresh, WarningFilled, ArrowRight, Loading } from '@element-plus/icons-vue';
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

// 手机端特有：直接切换开关
const handleToggleEnabled = async (row: McpServer, val: boolean) => {
  try {
    // 构造更新请求，保持其他字段不变
    const updateData: McpCreateRequest = {
      name: row.name,
      description: row.description,
      transportType: row.transportType,
      isEnabled: val,
      command: row.command,
      args: row.args,
      env: row.env,
      url: row.url
    };
    await mcpStore.updateMcp(row.id, updateData);
    ElMessage.success(t('settings.mcp.updateSuccess'));
  } catch (error) {
    ElMessage.error(t('settings.mcp.updateFailed'));
    // 如果失败，因为 v-model 绑定的是 store 的引用，可能需要刷新或回滚
    // 这里简单处理：重新获取列表以确保状态一致
    await mcpStore.fetchAvailableServices();
  }
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

const getStatusText = (status: McpHealthStatus) => {
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
    minute: '2-digit'
  });
};
</script>

<style scoped>
.mobile-mcp-manager {
  height: 100%;
  background-color: var(--color-background);
  padding-bottom: 80px; /* Space for FAB */
  position: relative;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

.mcp-list {
  padding: 0 12px;
}

.mcp-card {
  background-color: var(--color-background-soft);
  border-radius: 8px;
  margin-top: 12px;
  padding: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.title-area {
  display: flex;
  align-items: center;
  gap: 6px;
}

.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  line-height: 1.4;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.health-status {
  display: flex;
  align-items: center;
  font-size: 12px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.status-healthy { background-color: var(--el-color-success); }
.status-unhealthy { background-color: var(--el-color-danger); }
.status-unknown { background-color: var(--el-color-info-light-3); }

.status-text {
  color: var(--el-text-color-regular);
}

.card-config {
  font-size: 12px;
  color: var(--el-text-color-regular);
  background-color: var(--color-background);
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 8px;
  word-break: break-all;
}

.card-config .label {
  font-weight: bold;
  margin-right: 4px;
}

.card-error {
  display: flex;
  align-items: center;
  color: var(--el-color-danger);
  font-size: 13px;
  padding: 8px 0;
  border-top: 1px solid var(--color-border);
  margin-top: 4px;
}

.card-error span {
  flex: 1;
  margin-left: 4px;
}

.card-error .arrow {
  margin-left: auto;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
  border-top: 1px solid var(--color-border);
  padding-top: 8px;
}

.fab-add {
  position: fixed;
  bottom: 70px; /* Adjust based on tab bar height */
  right: 20px;
  z-index: 100;
  box-shadow: 0 2px 12px rgba(0,0,0,0.2);
}

/* Error Dialog */
.error-detail-content {
  font-size: 14px;
}
.error-meta p {
  margin: 4px 0 12px;
}
.error-stack-trace {
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
}
.error-stack-trace pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  color: var(--el-color-danger-dark-2);
}
</style>
