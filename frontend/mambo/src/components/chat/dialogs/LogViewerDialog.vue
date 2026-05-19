<!-- frontend/mambo/src/components/chat/dialogs/LogViewerDialog.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('chat.logViewer.title')"
    width="900px"
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
              <!-- Metadata Section -->
              <div class="log-section">
                <div class="log-section-header">
                  <h4>{{ $t('chat.logViewer.metaData') }}</h4>
                  <div class="log-section-actions">
                    <el-button size="small" text @click="expandAllInMeta(log.id)">
                      <el-icon><Expand /></el-icon>
                      {{ $t('chat.logViewer.expandAll') }}
                    </el-button>
                    <el-button size="small" text @click="collapseAllInMeta(log.id)">
                      <el-icon><Fold /></el-icon>
                      {{ $t('chat.logViewer.collapseAll') }}
                    </el-button>
                    <el-button size="small" text @click="copySectionData(log.configMetaData)">
                      <el-icon><CopyDocument /></el-icon>
                      {{ $t('chat.logViewer.copyJson') }}
                    </el-button>
                  </div>
                </div>
                <div
                  class="json-tree-wrapper"
                  v-if="log.configMetaData && Object.keys(log.configMetaData).length > 0"
                  :key="getMetaTreeKey(log.id)"
                >
                  <JsonNode
                    :value="log.configMetaData"
                    :depth="0"
                    :maxStringLength="maxStringLength"
                    :maxExpandDepth="getMetaExpandDepth(log.id)"
                    path="$"
                  />
                </div>
                <div v-else class="json-empty">{{ $t('chat.logViewer.emptyData') }}</div>
              </div>

              <!-- Payload Section -->
              <div class="log-section">
                <div class="log-section-header">
                  <h4>{{ $t('chat.logViewer.payload') }}</h4>
                  <div class="log-section-actions">
                    <el-button size="small" text @click="expandAllInPayload(log.id)">
                      <el-icon><Expand /></el-icon>
                      {{ $t('chat.logViewer.expandAll') }}
                    </el-button>
                    <el-button size="small" text @click="collapseAllInPayload(log.id)">
                      <el-icon><Fold /></el-icon>
                      {{ $t('chat.logViewer.collapseAll') }}
                    </el-button>
                    <el-button size="small" text @click="copySectionData(log.rawPayload)">
                      <el-icon><CopyDocument /></el-icon>
                      {{ $t('chat.logViewer.copyJson') }}
                    </el-button>
                  </div>
                </div>
                <div
                  class="json-tree-wrapper"
                  v-if="log.rawPayload && Object.keys(log.rawPayload).length > 0"
                  :key="getTreeKey(log.id)"
                >
                  <div class="payload-summary" v-if="getPayloadSummary(log.rawPayload)">
                    <span class="summary-text">{{ getPayloadSummary(log.rawPayload) }}</span>
                  </div>
                  <JsonNode
                    :value="log.rawPayload"
                    :depth="0"
                    :maxStringLength="maxStringLength"
                    :maxExpandDepth="getExpandDepth(log.id)"
                    path="$"
                  />
                </div>
                <div v-else class="json-empty">{{ $t('chat.logViewer.emptyData') }}</div>
              </div>
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
      <el-empty v-else :description="$t('chat.logViewer.noLogs')" />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { CopyDocument, Expand, Fold } from '@element-plus/icons-vue';
import { getPostPayloadLogs } from '@/api/logService';
import type { LogItem } from '@/api/types/logTypes';
import JsonNode from './JsonNode.vue';

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

// Configuration for JsonNode
const maxStringLength = 200;
const defaultMaxExpandDepth = 3;

// Tree expand/collapse state per log
const treeState = ref<Record<string, { key: number; expandDepth: number }>>({});
const metaTreeState = ref<Record<string, { key: number; expandDepth: number }>>({});

function getTreeKey(logId: string): number {
  return treeState.value[logId]?.key ?? 0;
}
function getExpandDepth(logId: string): number {
  return treeState.value[logId]?.expandDepth ?? defaultMaxExpandDepth;
}
function getMetaTreeKey(logId: string): number {
  return metaTreeState.value[logId]?.key ?? 0;
}
function getMetaExpandDepth(logId: string): number {
  return metaTreeState.value[logId]?.expandDepth ?? defaultMaxExpandDepth;
}

function expandAllInPayload(logId: string) {
  treeState.value[logId] = {
    key: (treeState.value[logId]?.key ?? 0) + 1,
    expandDepth: 20,
  };
}
function collapseAllInPayload(logId: string) {
  treeState.value[logId] = {
    key: (treeState.value[logId]?.key ?? 0) + 1,
    expandDepth: 0,
  };
}
function expandAllInMeta(logId: string) {
  metaTreeState.value[logId] = {
    key: (metaTreeState.value[logId]?.key ?? 0) + 1,
    expandDepth: 20,
  };
}
function collapseAllInMeta(logId: string) {
  metaTreeState.value[logId] = {
    key: (metaTreeState.value[logId]?.key ?? 0) + 1,
    expandDepth: 0,
  };
}

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

function getPayloadSummary(payload: Record<string, any>): string {
  const parts: string[] = [];
  if (payload.messages && Array.isArray(payload.messages)) {
    parts.push(`${payload.messages.length} messages`);
  }
  if (payload.model) {
    parts.push(`model: ${payload.model}`);
  }
  if (payload.temperature !== undefined) {
    parts.push(`temp: ${payload.temperature}`);
  }
  return parts.join(' · ');
}

function copySectionData(data: any) {
  const text = data ? JSON.stringify(data, null, 2) : '';
  navigator.clipboard.writeText(text).catch(() => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  });
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
  max-height: 600px;
  overflow-y: auto;
}

/* Section */
.log-section {
  margin-bottom: 4px;
}
.log-section + .log-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-light);
}
.log-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.log-section-header h4 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.log-section-actions {
  display: flex;
  gap: 4px;
}

/* JSON Tree Wrapper */
.json-tree-wrapper {
  background-color: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.json-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

/* Payload Summary */
.payload-summary {
  background: var(--el-color-info-light-9);
  border-left: 3px solid var(--el-color-info);
  padding: 6px 12px;
  margin-bottom: 10px;
  border-radius: 0 4px 4px 0;
}
.summary-text {
  font-size: 12px;
  color: var(--el-color-info-dark-2);
  font-weight: 500;
}

/* Pagination */
.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

h4 {
  margin-top: 0;
  margin-bottom: 8px;
}
</style>
