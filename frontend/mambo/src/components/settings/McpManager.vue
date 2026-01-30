<template>
  <div class="mcp-manager">
    <div class="header">
      <div class="title-section">
        <h2>MCP 工具管理</h2>
        <span class="subtitle">管理 Model Context Protocol 服务连接，扩展 AI 能力。</span>
      </div>
      <el-button type="primary" :icon="Plus" @click="handleCreate">新增 MCP 服务</el-button>
    </div>

    <el-table :data="availableServices" style="width: 100%" v-loading="isLoading">
      <el-table-column prop="name" label="名称" min-width="150">
        <template #default="{ row }">
          <div class="name-cell">
            <span class="name-text">{{ row.name }}</span>
            <el-tag v-if="row.isSystem" type="info" size="small" effect="plain">系统内置</el-tag>
          </div>
          <div class="description-text" v-if="row.description">{{ row.description }}</div>
        </template>
      </el-table-column>

      <el-table-column prop="transportType" label="连接类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.transportType === 'stdio' ? '' : 'warning'">
            {{ row.transportType.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="配置详情" min-width="180">
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

      <el-table-column prop="isEnabled" label="启用" width="80">
        <template #default="{ row }">
          <el-tag :type="row.isEnabled ? 'success' : 'danger'" effect="dark" size="small">
            {{ row.isEnabled ? 'ON' : 'OFF' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 新增：健康状态列 -->
      <el-table-column label="运行状态" width="100" align="center">
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
              title="测试连接"
            />
          </div>
        </template>
      </el-table-column>

      <!-- 新增：监测详情列 -->
      <el-table-column label="监测详情" min-width="160">
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
              <span>查看故障</span>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.isSystem">
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-popconfirm
              title="确定要删除该 MCP 服务吗？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
          <template v-else>
            <el-button link disabled title="系统内置服务不可编辑">编辑</el-button>
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
      title="MCP 服务故障详情"
      width="600px"
      append-to-body
    >
      <div class="error-detail-content">
        <div class="error-meta">
          <p><strong>服务名称:</strong> {{ currentErrorMcp?.name }}</p>
          <p><strong>发生时间:</strong> {{ currentErrorMcp?.last_test_at ? formatTime(currentErrorMcp.last_test_at) : '未知' }}</p>
        </div>
        <el-alert
          title="连接测试失败"
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
        <el-button @click="errorDialogVisible = false">关闭</el-button>
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
    ElMessage.success('MCP 服务已删除');
  } catch (error) {
    ElMessage.error('删除失败');
  }
};

const handleSave = async (data: McpCreateRequest) => {
  isSubmitting.value = true;
  try {
    if (editingMcp.value) {
      await mcpStore.updateMcp(editingMcp.value.id, data);
      ElMessage.success('MCP 服务更新成功');
    } else {
      await mcpStore.createMcp(data);
      ElMessage.success('MCP 服务创建成功');
    }
    dialogVisible.value = false;
  } catch (error) {
    ElMessage.error(editingMcp.value ? '更新失败' : '创建失败');
  } finally {
    isSubmitting.value = false;
  }
};

const handleTestConnection = async (row: McpServer) => {
  if (testingRowIds.has(row.id)) return;

  testingRowIds.add(row.id);
  try {
    await mcpStore.testConnection(row.id);
    ElMessage.success(`[${row.name}] 连接测试成功`);
  } catch (error) {
    ElMessage.error(`[${row.name}] 连接测试失败`);
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
  switch (status) {
    case 'healthy': return '正常';
    case 'unhealthy': return '异常';
    default: return '未测试';
  }
};

const formatTime = (isoString: string) => {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
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

/* Status Column Styles */
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

/* Monitor Column Styles */
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

/* Error Dialog Styles */
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
</style>
