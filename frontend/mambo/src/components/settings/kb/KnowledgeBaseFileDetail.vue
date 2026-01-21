<template>
  <div class="kb-file-detail-container">
    <div class="detail-header">
      <div class="header-content">
        <h2 class="file-title">
          <el-icon class="file-icon"><Document /></el-icon>
          {{ resource.name }}
        </h2>
        <div class="file-meta">
          <el-tag :type="statusTagType" effect="dark" size="small" class="status-tag">
            {{ statusLabel }}
          </el-tag>
          <span class="meta-item">ID: {{ resource.id }}</span>
          <span class="meta-item">上传时间: {{ new Date(resource.createdAt).toLocaleString() }}</span>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          @click="fetchStatus"
          :loading="isLoading"
          :icon="RefreshRight"
          circle
          title="刷新状态"
        />
      </div>
    </div>

    <el-scrollbar class="detail-content">
      <div class="content-wrapper">
        <!-- 进度概览卡片 -->
        <el-card shadow="never" class="status-card">
          <template #header>
            <div class="card-header">
              <span>向量化进度</span>
              <el-button
                v-if="canRetry"
                type="primary"
                size="small"
                :loading="isRetrying"
                @click="handleRetry"
              >
                重试任务
              </el-button>
            </div>
          </template>

          <div v-if="statusInfo" class="progress-section">
            <el-progress
              type="dashboard"
              :percentage="progressPercentage"
              :status="progressStatus"
              :width="120"
            >
              <template #default="{ percentage }">
                <span class="progress-value">{{ percentage }}%</span>
                <span class="progress-label">完成度</span>
              </template>
            </el-progress>

            <div class="stats-grid">
              <el-statistic title="总切片数" :value="statusInfo.total_chunks" />
              <el-statistic title="已完成" :value="statusInfo.completed_chunks" value-style="color: var(--el-color-success)" />
              <el-statistic title="处理中" :value="statusInfo.pending_chunks" value-style="color: var(--el-color-primary)" />
              <el-statistic title="失败" :value="statusInfo.failed_chunks" value-style="color: var(--el-color-danger)" />
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>

        <!-- 详细信息 -->
        <el-descriptions title="文件详情" :column="1" border class="info-descriptions">
          <el-descriptions-item label="文件名称">{{ resource.name }}</el-descriptions-item>
          <el-descriptions-item label="资源路径">{{ resource.id }}</el-descriptions-item>
          <el-descriptions-item label="最后更新">{{ new Date(resource.updatedAt).toLocaleString() }}</el-descriptions-item>
          <el-descriptions-item label="当前状态">
            {{ statusLabel }}
            <span v-if="statusInfo?.failed_chunks && statusInfo.failed_chunks > 0" class="error-text">
              ({{ statusInfo.failed_chunks }} 个切片处理失败)
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { Document, RefreshRight } from '@element-plus/icons-vue';
import { getKBFileStatus, retryKBFile } from '@/api/kbService';
import type { Resource, KBChunkStatus, KBFileStatus } from '@/api/types';

// --- Props ---
const props = defineProps<{
  resource: Resource;
}>();

// --- State ---
const statusInfo = ref<KBChunkStatus | null>(null);
const isLoading = ref(false);
const isRetrying = ref(false);
let pollTimer: number | null = null;

// --- Computed ---
const progressPercentage = computed(() => {
  if (!statusInfo.value || statusInfo.value.total_chunks === 0) return 0;
  const percent = (statusInfo.value.completed_chunks / statusInfo.value.total_chunks) * 100;
  return Math.min(Math.round(percent), 100);
});

const progressStatus = computed(() => {
  if (!statusInfo.value) return '';
  if (statusInfo.value.file_status === 'FAILED') return 'exception';
  if (statusInfo.value.file_status === 'INDEXED') return 'success';
  return '';
});

const statusLabel = computed(() => {
  const status = statusInfo.value?.file_status;
  const map: Record<string, string> = {
    'PENDING': '等待中',
    'PROCESSING': '处理中',
    'INDEXED': '已完成',
    'FAILED': '失败'
  };
  return status ? (map[status] || status) : '加载中...';
});

const statusTagType = computed(() => {
  const status = statusInfo.value?.file_status;
  const map: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
    'PENDING': 'info',
    'PROCESSING': 'primary',
    'INDEXED': 'success',
    'FAILED': 'danger'
  };
  return status ? (map[status] || 'info') : 'info';
});

const canRetry = computed(() => {
  if (!statusInfo.value) return false;
  return statusInfo.value.file_status === 'FAILED' || statusInfo.value.failed_chunks > 0;
});

// --- Methods ---

const stopPolling = () => {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
};

const startPolling = () => {
  stopPolling();
  pollTimer = window.setInterval(() => {
    fetchStatus(true);
  }, 3000); // Poll every 3 seconds
};

const fetchStatus = async (isPolling = false) => {
  if (!isPolling) isLoading.value = true;
  try {
    const res = await getKBFileStatus(props.resource.id);
    statusInfo.value = res;

    // Determine if we should continue polling
    const shouldPoll = res.file_status === 'PROCESSING' || res.file_status === 'PENDING';

    if (shouldPoll && !pollTimer) {
      startPolling();
    } else if (!shouldPoll && pollTimer) {
      stopPolling();
    }
  } catch (error) {
    console.error('Failed to fetch KB file status', error);
    if (!isPolling) ElMessage.error('获取状态失败');
    stopPolling();
  } finally {
    if (!isPolling) isLoading.value = false;
  }
};

const handleRetry = async () => {
  isRetrying.value = true;
  try {
    await retryKBFile(props.resource.id);
    ElMessage.success('任务重试请求已发送');
    // Immediately refresh status and ensure polling starts
    await fetchStatus();
    if (!pollTimer) startPolling();
  } catch (error) {
    console.error('Retry failed', error);
    ElMessage.error('重试请求失败');
  } finally {
    isRetrying.value = false;
  }
};

// --- Lifecycle ---

onMounted(() => {
  fetchStatus();
});

onUnmounted(() => {
  stopPolling();
});

watch(() => props.resource.id, (newId, oldId) => {
  if (newId !== oldId) {
    statusInfo.value = null;
    stopPolling();
    fetchStatus();
  }
});
</script>

<style scoped>
.kb-file-detail-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #fff;
}

.detail-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-shrink: 0;
}

.header-content {
  flex: 1;
  min-width: 0;
  margin-right: 16px;
}

.file-title {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  font-size: 20px;
  color: var(--el-text-color-secondary);
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.meta-item {
  font-family: monospace;
}

.detail-content {
  flex-grow: 1;
}

.content-wrapper {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.status-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 40px;
  padding: 10px 0;
}

.progress-value {
  display: block;
  font-size: 20px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.progress-label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.stats-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.info-descriptions {
  background-color: #fff;
}

.error-text {
  color: var(--el-color-danger);
  margin-left: 8px;
}
</style>
