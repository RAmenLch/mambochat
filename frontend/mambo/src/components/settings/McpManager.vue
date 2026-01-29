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

      <el-table-column prop="transportType" label="连接类型" width="120">
        <template #default="{ row }">
          <el-tag :type="row.transportType === 'stdio' ? '' : 'warning'">
            {{ row.transportType.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="配置详情" min-width="200">
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

      <el-table-column prop="isEnabled" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.isEnabled ? 'success' : 'danger'" effect="dark">
            {{ row.isEnabled ? '已启用' : '已禁用' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="180" fixed="right">
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import { useMcpStore } from '@/stores/mcpStore';
import type { McpServer, McpCreateRequest } from '@/api/types';
import McpFormDialog from './dialogs/McpFormDialog.vue';

const mcpStore = useMcpStore();
const { availableServices } = storeToRefs(mcpStore);

const isLoading = ref(false);
const dialogVisible = ref(false);
const isSubmitting = ref(false);
const editingMcp = ref<McpServer | null>(null);

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
    // 错误已在 store/service 层打印，此处仅提示
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
</style>
