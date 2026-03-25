<!-- frontend/mambo/src/components/chat/dialogs/LogViewerDialog.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    title="底层报文日志"
    width="800px"
    class="log-viewer-dialog"
    destroy-on-close
  >
    <div class="log-viewer-container" v-loading="loading">
      <template v-if="logs.length > 0">
        <el-collapse v-model="activeNames">
          <el-collapse-item
            v-for="log in logs"
            :key="log.id"
            :name="log.id"
          >
            <template #title>
              <div class="log-header">
                <span class="log-time">{{ formatDate(log.createdAt) }}</span>
                <el-tag size="small" type="info">{{ log.managerName }}</el-tag>
                <el-tag size="small" v-if="log.agentName">{{ log.agentName }}</el-tag>
              </div>
            </template>

            <div class="log-content">
              <h4>运行元数据 (MetaData)</h4>
              <pre class="json-block">{{ formatJson(log.configMetaData) }}</pre>

              <h4 class="mt-4">底层报文 (Payload)</h4>
              <pre class="json-block">{{ formatJson(log.rawPayload) }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, prev, pager, next"
            @current-change="fetchLogs"
          />
        </div>
      </template>
      <el-empty v-else description="暂无相关日志" />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { getPostPayloadLogs } from '@/api/logService';
import type { LogItem } from '@/api/types/logTypes';

const props = defineProps<{
  visible: boolean;
  messageId: string | null;
  chatId: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const loading = ref(false);
const logs = ref<LogItem[]>([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const activeNames = ref<string[]>([]);

async function fetchLogs() {
  if (!props.messageId) return;
  loading.value = true;
  try {
    const skip = (currentPage.value - 1) * pageSize.value;
    const res = await getPostPayloadLogs({
      skip,
      limit: pageSize.value,
      message_id: props.messageId
    });
    logs.value = res.items;
    total.value = res.total;
    if (logs.value.length > 0) {
      activeNames.value = [logs.value[0].id]; // 默认展开第一条
    }
  } catch (error) {
    console.error('Failed to fetch logs:', error);
  } finally {
    loading.value = false;
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    currentPage.value = 1;
    fetchLogs();
  } else {
    logs.value = [];
    total.value = 0;
  }
});

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString();
}

function formatJson(data: any) {
  if (!data) return '';
  return JSON.stringify(data, null, 2);
}
</script>

<style scoped>
.log-viewer-container {
  min-height: 200px;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.log-time {
  font-weight: bold;
  color: var(--el-text-color-regular);
}
.log-content {
  background-color: var(--el-bg-color-page);
  padding: 12px;
  border-radius: 4px;
  max-height: 500px;
  overflow-y: auto;
}
.json-block {
  background-color: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.mt-4 {
  margin-top: 16px;
  margin-bottom: 8px;
}
h4 {
  margin-top: 0;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
