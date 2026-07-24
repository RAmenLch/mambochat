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
      <div v-if="snapshots.length === 0" class="empty-wrapper">
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
              <el-tooltip
                :content="snap.messagePreview"
                placement="top"
                :show-after="300"
                effect="dark"
                popper-class="snapshot-msg-tooltip"
              >
                <div class="snapshot-msg-tip">
                  <el-icon><ChatLineSquare /></el-icon>
                  <span>{{ $t('agent.versionHistorySnapshotTip', { index: snap.messageIndex }) }}</span>
                </div>
              </el-tooltip>
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
                  <el-button
                    link
                    size="small"
                    class="diff-file-btn"
                    @click.stop="openFileDiff(snap.checkpoint_id, file)"
                  >
                    {{ $t('agent.versionHistoryDiff') }}
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
              </div>
              <div v-else class="no-files-hint">
                {{ $t('agent.versionHistoryFileCount', { count: 0 }) }}
              </div>

              <!-- 回滚记录（归入快照内部，默认折叠） -->
              <div v-if="snap.rollbacks.length > 0" class="rollback-section">
                <div class="rollback-toggle" @click="toggleRollbackExpand(snap.checkpoint_id)">
                  <el-icon :class="{ 'rotate-arrow': expandedRollbacks.has(snap.checkpoint_id) }"><ArrowRight /></el-icon>
                  <span>{{ $t('agent.versionHistoryRollbackCount', { count: snap.rollbacks.length }) }}</span>
                </div>
                <div v-show="expandedRollbacks.has(snap.checkpoint_id)" class="rollback-detail-body">
                  <div v-for="(rb, ri) in snap.rollbacks" :key="ri" class="rollback-item">
                    <div class="rollback-item-header">
                      <el-tag size="small" :type="rb.errors.length === 0 ? 'success' : 'danger'" effect="plain">
                        {{ rb.errors.length === 0 ? $t('agent.versionHistoryRollbackSuccess') : $t('agent.versionHistoryRollbackPartial') }}
                      </el-tag>
                      <span class="rollback-item-time">{{ formatTimestamp(rb.timestamp) }}</span>
                    </div>
                    <div v-if="rb.restored.length > 0" class="rollback-restored">
                      <p class="rollback-section-title">{{ $t('agent.versionHistoryRestoredFiles') }}:</p>
                      <ul class="rollback-file-list">
                        <li v-for="f in rb.restored" :key="f" class="rollback-file-item restored">
                          <el-icon><CircleCheck /></el-icon>
                          <code>{{ f }}</code>
                        </li>
                      </ul>
                    </div>
                    <div v-if="rb.errors.length > 0" class="rollback-errors">
                      <p class="rollback-section-title error-title">{{ $t('agent.versionHistoryRestoreErrors') }}:</p>
                      <ul class="rollback-file-list">
                        <li v-for="e in rb.errors" :key="e" class="rollback-file-item failed">
                          <el-icon><CircleClose /></el-icon>
                          <span>{{ e }}</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
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

    <!-- 差异对比弹窗 -->
    <el-dialog
      v-model="diffDialogVisible"
      :title="$t('agent.versionHistoryDiffTitle') + ': ' + diffFilePath"
      width="850px"
      destroy-on-close
    >
      <div v-if="diffDialogLoading" class="file-dialog-loading">
        <el-skeleton :rows="10" animated />
      </div>
      <div v-else-if="diffError" class="file-dialog-error">
        {{ diffError }}
      </div>
      <div v-else-if="diffReadError" class="file-dialog-error" style="color: var(--el-color-warning);">
        {{ diffReadError }}
      </div>
      <div v-else class="diff-content-wrapper">
        <pre class="diff-content-code"><code><template
          v-for="(line, i) in diffLines"
          :key="i"
        ><span
          :class="line.type"
        >{{ line.text }}</span></template></code></pre>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { Document, CopyDocument, RefreshRight, CircleCheck, CircleClose, ChatLineSquare, ArrowRight } from '@element-plus/icons-vue';
import { getFileVersion, restoreFiles, getFileDiff } from '@/api/versionControlService';

interface RollbackRecord {
  target_checkpoint_id: string;
  timestamp: string;
  restored: string[];
  errors: string[];
}

interface VersionSnapshotItem {
  checkpoint_id: string;
  timestamp: string;
  file_count: number;
  changed_files: string[];
  messageIndex: number;
  messagePreview: string;
  rollbacks: RollbackRecord[];
}

interface SubMessage {
  type: string;
  content: string;
}

interface Message {
  id: string;
  sub_messages?: SubMessage[];
}

const props = defineProps<{
  visible: boolean;
  chatId: string | null;
  messages: Message[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'refreshed'): void;
}>();

const { t } = useI18n();

// 从 messages 中收集快照，并将回滚记录归入目标快照
const snapshots = computed<VersionSnapshotItem[]>(() => {
  const snapshotMap = new Map<string, VersionSnapshotItem>();
  const rollbackRecords: RollbackRecord[] = [];

  props.messages.forEach((msg, msgIndex) => {
    const previewSub = (msg.sub_messages || []).find(sm => sm.type === 'Normal');
    const msgPreview = previewSub?.content?.substring(0, 40) || '';
    for (const sub of (msg.sub_messages || [])) {
      if (sub.type !== 'VersionSnapshot') continue;
      try {
        const content = JSON.parse(sub.content);
        if (content.rollback) {
          // 回滚记录：收集后归入目标快照
          rollbackRecords.push(content.rollback);
        } else {
          // 正常快照
          snapshotMap.set(content.checkpoint_id, {
            checkpoint_id: content.checkpoint_id,
            timestamp: content.timestamp,
            file_count: content.files?.length || 0,
            changed_files: content.files?.map((f: any) => f.path) || [],
            messageIndex: msgIndex + 1,
            messagePreview: msgPreview,
            rollbacks: [],
          });
        }
      } catch {
        // ignore parse errors
      }
    }
  });

  // 将回滚记录归入对应的目标快照
  for (const rb of rollbackRecords) {
    const target = snapshotMap.get(rb.target_checkpoint_id);
    if (target) {
      target.rollbacks.push(rb);
    }
  }

  return [...snapshotMap.values()].sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
});

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
const expandedRollbacks = ref<Set<string>>(new Set());

// diff 弹窗
const diffDialogVisible = ref(false);
const diffDialogLoading = ref(false);
const diffError = ref('');
const diffReadError = ref('');
const diffFilePath = ref('');
const diffLines = ref<{ type: string; text: string }[]>([]);

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

function parseDiff(diffText: string): { type: string; text: string }[] {
  const lines: { type: string; text: string }[] = [];
  for (const line of diffText.split('\n')) {
    if (line.startsWith('+ ')) {
      lines.push({ type: 'diff-add', text: line });
    } else if (line.startsWith('- ')) {
      lines.push({ type: 'diff-del', text: line });
    } else if (line.startsWith('? ')) {
      lines.push({ type: 'diff-hint', text: line });
    } else {
      lines.push({ type: 'diff-context', text: line });
    }
  }
  return lines;
}

async function openFileDiff(checkpointId: string, filePath: string) {
  if (!props.chatId) return;
  diffFilePath.value = filePath;
  diffLines.value = [];
  diffError.value = '';
  diffReadError.value = '';
  diffDialogVisible.value = true;
  diffDialogLoading.value = true;

  try {
    const result = await getFileDiff(props.chatId, filePath, checkpointId);
    diffLines.value = parseDiff(result.diff);
    if (!result.diff) {
      diffError.value = 'No differences found';
    }
    if (result.read_error) {
      diffReadError.value = result.read_error;
    }
  } catch (err: any) {
    diffError.value = err?.response?.data?.detail || err?.message || 'Failed to load diff';
  } finally {
    diffDialogLoading.value = false;
  }
}

function confirmRestore(checkpointId: string, file?: string) {
  pendingRestoreCpid.value = checkpointId;
  if (file) {
    pendingRestoreFiles.value = [file];
  } else {
    const snap = snapshots.value.find(s => s.checkpoint_id === checkpointId);
    pendingRestoreFiles.value = snap?.changed_files || [];
  }
  restoreDialogVisible.value = true;
}

function toggleRollbackExpand(checkpointId: string) {
  const s = new Set(expandedRollbacks.value);
  if (s.has(checkpointId)) {
    s.delete(checkpointId);
  } else {
    s.add(checkpointId);
  }
  expandedRollbacks.value = s;
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
    emit('refreshed');

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
</script>

<style scoped>
.version-history-content {
  height: 100%;
  padding-bottom: 24px;
}

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

.no-files-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding-left: 8px;
}

.snapshot-msg-tip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 8px;
  padding-left: 2px;
}

.snapshot-msg-tip .el-icon {
  font-size: 14px;
}

.rotate-arrow {
  transition: transform 0.2s;
  transform: rotate(90deg);
}

.rollback-detail-body {
  padding-top: 4px;
}

/* rollback section (inside snapshot) */
.rollback-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-light);
}

.rollback-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  padding: 2px 0;
  user-select: none;
}

.rollback-toggle:hover {
  color: var(--el-color-primary);
}

.rollback-toggle .el-icon {
  font-size: 12px;
  transition: transform 0.2s;
}

.rollback-detail-body {
  padding-top: 8px;
}

.rollback-item {
  padding: 8px 0 4px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.rollback-item:first-child {
  border-top: none;
  padding-top: 4px;
}

.rollback-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.rollback-item-time {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.rollback-restored,
.rollback-errors {
  margin-bottom: 4px;
}

.rollback-section-title {
  font-size: 12px;
  font-weight: 600;
  margin: 4px 0;
  color: var(--el-text-color-secondary);
}

.error-title {
  color: var(--el-color-danger);
}

.rollback-file-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.rollback-file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  font-size: 12px;
  border-radius: 4px;
}

.rollback-file-item.restored {
  color: var(--el-color-success);
}

.rollback-file-item.failed {
  color: var(--el-color-danger);
}

.rollback-file-item code {
  font-family: monospace;
  word-break: break-all;
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

.diff-file-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
  font-size: 12px;
  margin-left: 2px;
}

.changed-file-item:hover .diff-file-btn {
  opacity: 1;
}

.diff-content-wrapper {
  max-height: 60vh;
  overflow: auto;
}

.diff-content-code {
  margin: 0;
  padding: 0;
  font-size: 13px;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre;
  background: var(--el-fill-color);
  border-radius: 8px;
}

.diff-content-code code {
  display: block;
  padding: 12px 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.diff-content-code span {
  display: block;
  padding: 0 16px;
}

.diff-add {
  background: #e6ffec;
  color: #1a7f37;
}

.diff-del {
  background: #ffebe9;
  color: #cf222e;
}

.diff-hunk {
  background: #ddf4ff;
  color: #0969da;
  font-weight: 600;
}

.diff-header {
  background: #f6f8fa;
  color: #57606a;
  font-weight: 600;
}

.diff-context {
  background: transparent;
  color: var(--el-text-color-regular);
}

.diff-hint {
  background: #fff8c5;
  color: #9a6700;
}
</style>
