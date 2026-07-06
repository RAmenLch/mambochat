<!-- frontend/mambo/src/components/chat/dialogs/VersionHistoryDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    :title="$t('agent.versionHistory')"
    direction="rtl"
    size="450px"
    @update:model-value="handleUpdateModelValue"
  >
    <div class="version-history-content">
      <div v-if="isLoading" class="loading-wrapper">
        <el-skeleton :rows="6" animated />
      </div>

      <div v-else-if="errorMsg" class="error-wrapper">
        <el-empty :description="errorMsg" :image-size="60" />
      </div>

      <div v-else-if="snapshots.length === 0" class="empty-wrapper">
        <el-empty :description="$t('agent.versionHistoryNoData')" :image-size="80" />
      </div>

      <el-scrollbar v-else class="snapshot-list-scrollbar">
        <el-timeline>
          <el-timeline-item
            v-for="snap in snapshots"
            :key="snap.checkpoint_id"
            :timestamp="formatTimestamp(snap.timestamp)"
            placement="top"
            :type="snap.file_count > 0 ? 'primary' : 'info'"
          >
            <div class="snapshot-card">
              <div class="snapshot-header">
                <span class="snapshot-label">{{ $t('agent.versionHistorySnapshotLabel') }}</span>
                <el-tag size="small" :type="snap.file_count > 0 ? 'warning' : 'info'" effect="plain">
                  {{ $t('agent.versionHistoryFileCount', { count: snap.file_count }) }}
                </el-tag>
              </div>
              <div class="snapshot-id">
                <code>{{ snap.checkpoint_id.substring(0, 16) }}...</code>
              </div>
              <ul v-if="snap.file_count > 0" class="changed-files-list">
                <li
                  v-for="file in snap.changed_files"
                  :key="file"
                  class="changed-file-item"
                  @click="openFileContent(snap.checkpoint_id, file)"
                >
                  <el-icon><Document /></el-icon>
                  <span class="file-path">{{ file }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="RefreshRight"
                    class="restore-file-btn"
                    :loading="restoringFile === file && restoringCpid === snap.checkpoint_id"
                    @click.stop="confirmRestore(snap.checkpoint_id, file)"
                  >
                    {{ $t('agent.versionHistoryRestoreFile') }}
                  </el-button>
                </li>
              </ul>
              <div v-if="snap.file_count > 0" class="snapshot-actions">
                <el-button
                  text
                  size="small"
                  :icon="RefreshRight"
                  :loading="restoringCpid === snap.checkpoint_id && !restoringFile"
                  @click="confirmRestore(snap.checkpoint_id)"
                >
                  {{ $t('agent.versionHistoryRestoreAll') }}
                </el-button>
                <el-button
                  text
                  size="small"
                  type="primary"
                  @click="handleRestoreAndContinue(snap.checkpoint_id)"
                >
                  <el-icon style="margin-right: 4px;"><RefreshRight /></el-icon>
                  {{ $t('agent.versionHistoryRollbackContinue') }}
                </el-button>
              </div>
              <div v-else class="no-files-hint">
                {{ $t('agent.versionHistoryFileCount', { count: 0 }) }}
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-scrollbar>
    </div>

    <!-- 恢复确认弹窗 -->
    <el-dialog
      v-model="restoreDialogVisible"
      :title="$t('agent.versionHistoryRestoreTitle')"
      width="420px"
      destroy-on-close
    >
      <div class="restore-dialog-body">
        <el-alert
          :title="$t('agent.versionHistoryRestoreWarning')"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 16px;"
        />
        <p style="margin: 0;">
          <strong>{{ $t('agent.versionHistoryRestoreConfirm', { count: pendingRestoreFiles.length }) }}</strong>
        </p>
        <ul class="restore-file-preview">
          <li v-for="f in pendingRestoreFiles" :key="f">
            <code>{{ f }}</code>
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="restoreDialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="isRestoring" @click="executeRestore">
          {{ $t('common.action.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 文件内容弹窗 -->
    <el-dialog
      v-model="fileDialogVisible"
      :title="$t('agent.versionHistoryFileContent')"
      width="700px"
      destroy-on-close
    >
      <div class="file-dialog-header">
        <div class="file-dialog-path">
          <el-icon><Document /></el-icon>
          <code>{{ viewingFilePath }}</code>
        </div>
        <el-button
          type="primary"
          plain
          size="small"
          :icon="CopyDocument"
          @click="copyFileContent"
        >
          {{ $t('agent.versionHistoryCopyContent') }}
        </el-button>
      </div>
      <div v-if="fileDialogLoading" class="file-dialog-loading">
        <el-skeleton :rows="10" animated />
      </div>
      <div v-else-if="fileContentError" class="file-dialog-error">
        {{ fileContentError }}
      </div>
      <div v-else class="file-content-wrapper">
        <pre class="file-content-code"><code>{{ viewingFileContent }}</code></pre>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Document, CopyDocument, RefreshRight } from '@element-plus/icons-vue';
import { getSnapshots, getFileVersion, restoreFiles } from '@/api/versionControlService';
import type { VersionSnapshotItem } from '@/api/versionControlService';

const props = defineProps<{
  visible: boolean;
  chatId: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'restore-and-continue', checkpointId: string, files: string[]): void;
}>();

const { t } = useI18n();

const isLoading = ref(false);
const errorMsg = ref('');
const snapshots = ref<VersionSnapshotItem[]>([]);

// 文件内容弹窗
const fileDialogVisible = ref(false);
const fileDialogLoading = ref(false);
const fileContentError = ref('');
const viewingFilePath = ref('');
const viewingFileContent = ref('');

// 恢复相关
const restoreDialogVisible = ref(false);
const isRestoring = ref(false);
const pendingRestoreFiles = ref<string[]>([]);
const pendingRestoreCpid = ref('');
const restoringCpid = ref('');
const restoringFile = ref('');
const viewingCheckpointId = ref('');

function handleUpdateModelValue(value: boolean) {
  emit('update:visible', value);
}

function formatTimestamp(ts: string): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString();
  } catch {
    return ts;
  }
}

async function openFileContent(checkpointId: string, filePath: string) {
  if (!props.chatId) return;
  viewingFilePath.value = filePath;
  viewingCheckpointId.value = checkpointId;
  viewingFileContent.value = '';
  fileContentError.value = '';
  fileDialogVisible.value = true;
  fileDialogLoading.value = true;

  try {
    const result = await getFileVersion(props.chatId, filePath, checkpointId);
    viewingFileContent.value = result.content || '';
  } catch (err: any) {
    fileContentError.value = err?.response?.data?.detail || err?.message || 'Failed to load file content';
  } finally {
    fileDialogLoading.value = false;
  }
}

async function copyFileContent() {
  try {
    await navigator.clipboard.writeText(viewingFileContent.value);
    ElMessage.success(t('agent.versionHistoryContentCopied'));
  } catch {
    ElMessage.error('Copy failed');
  }
}

function confirmRestore(checkpointId: string, file?: string) {
  pendingRestoreCpid.value = checkpointId;
  if (file) {
    pendingRestoreFiles.value = [file];
  } else {
    // restore all files in the snapshot
    const snap = snapshots.value.find(s => s.checkpoint_id === checkpointId);
    pendingRestoreFiles.value = snap?.changed_files || [];
  }
  restoreDialogVisible.value = true;
}

async function executeRestore() {
  if (!props.chatId || pendingRestoreFiles.value.length === 0) return;
  isRestoring.value = true;
  restoringCpid.value = pendingRestoreCpid.value;
  restoringFile.value = pendingRestoreFiles.value.length === 1 ? pendingRestoreFiles.value[0] : '';

  try {
    const result = await restoreFiles(
      props.chatId,
      pendingRestoreCpid.value,
      pendingRestoreFiles.value,
    );
    restoreDialogVisible.value = false;

    if (result.errors.length > 0) {
      ElMessage.warning(
        `${t('agent.versionHistoryRestored')}: ${result.restored.length}, ${t('agent.versionHistoryRestoreErrors')}: ${result.errors.length}`,
      );
    } else {
      ElMessage.success(t('agent.versionHistoryRestoreSuccess', { count: result.restored.length }));
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'Restore failed');
  } finally {
    isRestoring.value = false;
    restoringCpid.value = '';
    restoringFile.value = '';
    pendingRestoreFiles.value = [];
  }
}

function handleRestoreAndContinue(checkpointId: string) {
  const snap = snapshots.value.find(s => s.checkpoint_id === checkpointId);
  const files = snap?.changed_files || [];
  if (files.length === 0) {
    ElMessage.warning(t('agent.versionHistoryNoFiles'));
    return;
  }
  emit('restore-and-continue', checkpointId, files);
}

async function loadSnapshots() {
  if (!props.chatId) return;
  isLoading.value = true;
  errorMsg.value = '';
  snapshots.value = [];

  try {
    const result = await getSnapshots(props.chatId);
    snapshots.value = result.snapshots || [];
  } catch (err: any) {
    const status = err?.response?.status;
    if (status === 404) {
      errorMsg.value = t('agent.versionHistoryNoData');
      snapshots.value = [];
    } else {
      errorMsg.value = err?.response?.data?.detail || err?.message || 'Failed to load version history';
    }
  } finally {
    isLoading.value = false;
  }
}

watch(
  () => props.visible,
  (newVal) => {
    if (newVal) {
      loadSnapshots();
    }
  },
);
</script>

<style scoped>
.version-history-content {
  height: 100%;
  padding-bottom: 24px;
}

.loading-wrapper,
.error-wrapper,
.empty-wrapper {
  padding: 40px 0;
}

.snapshot-list-scrollbar {
  height: calc(100vh - 120px);
  padding-right: 8px;
}

.snapshot-card {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 4px;
}

.snapshot-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.snapshot-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.snapshot-id {
  margin-bottom: 8px;
}

.snapshot-id code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
}

.changed-files-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.changed-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  margin: 4px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 13px;
}

.changed-file-item:hover {
  background: var(--el-color-primary-light-9);
}

.changed-file-item .el-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.file-path {
  font-family: monospace;
  word-break: break-all;
  color: var(--el-text-color-regular);
  flex: 1;
}

.restore-file-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
  font-size: 12px;
}

.changed-file-item:hover .restore-file-btn {
  opacity: 1;
}

.snapshot-actions {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-light);
  display: flex;
  justify-content: flex-end;
}

.restore-dialog-body {
  line-height: 1.6;
}

.restore-file-preview {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  max-height: 200px;
  overflow-y: auto;
}

.restore-file-preview li {
  padding: 4px 8px;
  margin: 2px 0;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
}

.restore-file-preview code {
  font-family: 'Consolas', 'Monaco', monospace;
  word-break: break-all;
}

.no-files-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding-left: 8px;
}

.file-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.file-dialog-path {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.file-dialog-path code {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-dialog-loading {
  padding: 20px 0;
}

.file-dialog-error {
  padding: 20px;
  color: var(--el-color-danger);
  text-align: center;
}

.file-content-wrapper {
  max-height: 60vh;
  overflow: auto;
}

.file-content-code {
  margin: 0;
  padding: 16px;
  background: var(--el-fill-color);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.file-content-code code {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}
</style>
