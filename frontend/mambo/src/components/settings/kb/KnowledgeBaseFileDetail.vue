<!-- frontend/mambo/src/components/settings/kb/KnowledgeBaseFileDetail.vue -->
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
          <span class="meta-item">{{ $t('resource.meta.id') }}: {{ resource.id }}</span>
          <span class="meta-item">
            {{ $t('kb.detail.uploadTime', { time: new Date(resource.createdAt).toLocaleString() }) }}
          </span>
          <el-tooltip
            v-if="statusInfo?.is_stale"
            :content="$t('kb.detail.staleTooltip')"
            placement="top"
          >
            <el-tag type="warning" effect="plain" size="small" class="stale-tag">
              <el-icon><Warning /></el-icon> {{ $t('kb.task.reEmbed') }}
            </el-tag>
          </el-tooltip>
        </div>
      </div>
    </div>

    <el-scrollbar class="detail-content">
      <div class="content-wrapper">
        <!-- 左右布局：配置与进度 -->
        <el-row :gutter="20" class="top-section">
          <!-- 左侧：任务配置 (变窄，垂直排列) -->
          <el-col :span="8">
            <el-card shadow="never" class="config-card h-full">
              <template #header>
                <div class="card-header">
                  <span>{{ $t('kb.task.configTitle') }}</span>
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="!isConfigDirty || isProcessing"
                    :loading="isSubmitting"
                    @click="handleSaveConfig"
                  >
                    {{ $t('common.action.save') }}
                  </el-button>
                </div>
              </template>

              <el-form
                ref="configFormRef"
                :model="taskConfig"
                :rules="configRules"
                label-position="top"
                :disabled="isProcessing"
                class="config-form"
              >
                <el-form-item :label="$t('kb.task.splitterType')" prop="splitter_type">
                  <el-radio-group v-model="taskConfig.splitter_type" class="w-full">
                    <el-radio-button label="simple">{{ $t('kb.task.simple') }}</el-radio-button>
                    <el-radio-button label="separator">{{ $t('kb.task.separator') }}</el-radio-button>
                    <el-radio-button label="markdown">{{ $t('kb.task.markdown') }}</el-radio-button>
                  </el-radio-group>
                </el-form-item>

                <el-form-item prop="chunk_size">
                  <template #label>
                    <div class="label-with-tooltip">
                      <span>{{ $t('kb.task.chunkSize') }}</span>
                      <el-tooltip
                        :content="$t('kb.task.chunkSizeTooltip')"
                        placement="top"
                      >
                        <el-icon class="help-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-input-number
                    v-model="taskConfig.chunk_size"
                    :min="50"
                    :step="50"
                    style="width: 100%"
                  />
                </el-form-item>

                <el-form-item prop="chunk_overlap">
                  <template #label>
                    <div class="label-with-tooltip">
                      <span>{{ $t('kb.task.chunkOverlap') }}</span>
                      <el-tooltip
                        :content="$t('kb.task.chunkOverlapTooltip')"
                        placement="top"
                      >
                        <el-icon class="help-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-input-number
                    v-model="taskConfig.chunk_overlap"
                    :min="0"
                    :step="10"
                    style="width: 100%"
                  />
                </el-form-item>

                <el-form-item v-if="taskConfig.splitter_type === 'separator'" prop="separator">
                  <template #label>
                    <div class="label-with-tooltip">
                      <span>{{ $t('kb.task.separatorChar') }}</span>
                      <el-tooltip :content="$t('kb.task.separatorTooltip')" placement="top">
                        <el-icon class="help-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-input v-model="taskConfig.separator" placeholder="例如: \n\n" />
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>

          <!-- 右侧：向量化进度 (变宽，包含完整参数) -->
          <el-col :span="16">
            <el-card shadow="never" class="status-card h-full">
              <template #header>
                <div class="card-header">
                  <span>{{ $t('kb.task.statusTitle') }}</span>
                  <div class="card-header-actions">
                    <el-button
                      v-if="isProcessing"
                      type="danger"
                      size="small"
                      :loading="isSubmitting"
                      @click="handleStop"
                    >
                      {{ $t('kb.task.stop') }}
                    </el-button>
                    <el-button
                      v-if="canResume"
                      type="warning"
                      size="small"
                      :loading="isSubmitting"
                      @click="handleResume"
                    >
                      {{ $t('kb.task.resume') }}
                    </el-button>
                    <el-button
                      v-if="!isProcessing"
                      type="primary"
                      size="small"
                      :loading="isSubmitting"
                      @click="handleStart"
                    >
                      {{ startButtonText }}
                    </el-button>
                  </div>
                </div>
              </template>

              <div v-if="statusInfo" class="status-body">
                <!-- 左侧：进度环 -->
                <div class="progress-circle-area">
                  <el-progress
                    type="dashboard"
                    :percentage="progressPercentage"
                    :status="progressStatus"
                    :width="140"
                    :stroke-width="10"
                  >
                    <template #default="{ percentage }">
                      <span class="progress-value">{{ percentage }}%</span>
                      <span class="progress-label">{{ $t('kb.task.progress') }}</span>
                    </template>
                  </el-progress>
                </div>

                <!-- 右侧：三行两列统计数据 -->
                <div class="stats-grid-area">
                  <div class="stats-grid">
                    <!-- Row 1 -->
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.totalChunks') }}</div>
                      <div class="stat-value">{{ statusInfo.total_chunks }}</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.currentStatus') }}</div>
                      <div class="stat-value">
                        <el-tag :type="statusTagType" size="small" effect="plain">
                          {{ statusLabel }}
                        </el-tag>
                      </div>
                    </div>

                    <!-- Row 2 -->
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.completed') }}</div>
                      <div class="stat-value success">{{ statusInfo.completed_chunks }}</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.pending') }}</div>
                      <div class="stat-value primary">{{ statusInfo.pending_chunks }}</div>
                    </div>

                    <!-- Row 3 -->
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.failed') }}</div>
                      <div class="stat-value danger">{{ statusInfo.failed_chunks }}</div>
                    </div>
                    <div class="stat-item">
                      <div class="stat-label">{{ $t('kb.task.stopped') }}</div>
                      <div class="stat-value warning">{{ statusInfo.stopped_chunks }}</div>
                    </div>
                  </div>
                </div>

                <!-- 任务级别错误信息 -->
                <div
                  v-if="statusInfo?.file_status === 'FAILED' && taskErrorMessage"
                  class="error-info-area"
                >
                  <el-alert
                    :title="$t('kb.task.errorInfo')"
                    :description="taskErrorMessage"
                    type="error"
                    show-icon
                    :closable="false"
                  />
                </div>
              </div>
              <el-skeleton v-else :rows="5" animated />
            </el-card>
          </el-col>
        </el-row>

        <!-- 下方：切分详情列表 -->
        <el-card shadow="never" class="chunks-card">
          <template #header>
            <div class="card-header">
              <span>{{ $t('kb.chunk.title') }}</span>
              <span class="chunk-total-badge" v-if="totalChunks > 0">
                {{ $t('kb.chunk.totalCount', { count: totalChunks }) }}
              </span>
            </div>
          </template>

          <div v-loading="isLoadingChunks" class="chunks-container">
            <div v-if="chunkList.length > 0" class="chunk-list">
              <div v-for="chunk in chunkList" :key="chunk.id" class="chunk-item">
                <div class="chunk-header">
                  <el-tag size="small" type="info" effect="plain">#{{ chunk.chunk_index }}</el-tag>
                  <div class="chunk-meta">
                    <span class="byte-size">{{ formatBytes(chunk.byte_size) }}</span>
                    <el-tag
                      size="small"
                      :type="getChunkStatusType(chunk.status)"
                      class="chunk-status-tag"
                    >
                      {{ chunk.status }}
                    </el-tag>
                  </div>
                </div>
                <!-- 单个切片失败原因 -->
                <div
                  v-if="chunk.status === 'FAILED' && chunk.error_message"
                  class="chunk-error-line"
                >
                  <span class="chunk-error-label">{{ $t('kb.chunk.error') }}:</span>
                  <span class="chunk-error-text">{{ chunk.error_message }}</span>
                </div>
                <div class="chunk-body">
                  <div
                    class="chunk-text"
                    :class="{ collapsed: !isExpanded(chunk.id) }"
                    @click="toggleExpand(chunk.id)"
                  >
                    {{ chunk.content }}
                  </div>
                  <el-button
                    link
                    type="primary"
                    size="small"
                    class="expand-btn"
                    @click.stop="toggleExpand(chunk.id)"
                  >
                    {{ isExpanded(chunk.id) ? $t('common.action.collapse') : $t('common.action.expand') }}
                    <el-icon class="el-icon--right">
                      <ArrowUp v-if="isExpanded(chunk.id)" />
                      <ArrowDown v-else />
                    </el-icon>
                  </el-button>
                </div>
              </div>
            </div>
            <el-empty v-else :description="$t('kb.chunk.empty')" :image-size="60" />

            <div class="pagination-wrapper" v-if="totalChunks > 0">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50, 100]"
                layout="total, sizes, prev, pager, next"
                :total="totalChunks"
                @change="handlePageChange"
                size="small"
              />
            </div>
          </div>
        </el-card>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Document, QuestionFilled, Warning, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useKBFileTask } from '@/composables/useKBFileTask'
import { useSettingsStore } from '@/stores/settingsStore'
import { getKBFileChunks } from '@/api/kbService'
import type { Resource, KBSplitterConfig, KBResumeConflictErrorDetail, KBChunk } from '@/api/types'

const props = defineProps<{
  resource: Resource
}>()

const settingsStore = useSettingsStore()
const { t } = useI18n()

// --- Config & Task Logic ---
const configFormRef = ref<FormInstance>()

const taskConfig = reactive<KBSplitterConfig>({
  splitter_type: 'simple',
  chunk_size: 500,
  chunk_overlap: 50,
  separator: '\\n\\n',
})

const configRules = reactive<FormRules>({
  chunk_size: [{ required: true, message: '请输入切片大小', trigger: 'change' }],
  chunk_overlap: [{ required: true, message: '请输入重叠大小', trigger: 'change' }],
  separator: [{ required: true, message: '请输入分隔符', trigger: 'blur' }],
})

const {
  statusInfo,
  optimisticStatus,
  isSubmitting,
  isProcessing,
  hasIndexedData,
  canResume,
  progressPercentage,
  startSSE,
  saveConfig,
  startTask,
  resumeTask,
  stopTask,
} = useKBFileTask(props.resource.id)

// --- Chunk List Logic ---
const isLoadingChunks = ref(false)
const chunkList = ref<KBChunk[]>([])
const totalChunks = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const expandedChunks = ref<Set<string>>(new Set())

// --- Computed ---

const startButtonText = computed(() => {
  if (optimisticStatus.value === 'STARTING') return t('kb.task.starting')
  if (statusInfo.value?.file_status === 'INITIAL') return t('kb.task.start')
  return hasIndexedData.value ? t('kb.task.reEmbed') : t('kb.task.start')
})

const progressStatus = computed(() => {
  if (!statusInfo.value) return ''
  const s = statusInfo.value.file_status
  if (s === 'FAILED') return 'exception'
  if (s === 'STOPPED') return 'warning'
  if (s === 'COMPLETED') return 'success'
  return ''
})

/** 任务级别错误信息：优先来自 statusInfo，回退到本地填充 */
const taskErrorMessage = computed(() => {
  if (!statusInfo.value) return null
  // SSE 推送的 error_message（由后端 KBProcessingStatus.error_message 提供）
  if (statusInfo.value.error_message) return statusInfo.value.error_message
  // 回退：如果没有任何切片数据但有 failed_chunks，给提示
  if (statusInfo.value.file_status === 'FAILED' && statusInfo.value.failed_chunks > 0) {
    return t('kb.task.noErrorDetail')
  }
  return null
})

const statusLabel = computed(() => {
  if (optimisticStatus.value === 'STARTING') return t('kb.task.starting')
  if (optimisticStatus.value === 'STOPPING') return t('kb.task.stopping')

  const status = statusInfo.value?.file_status
  const map: Record<string, string> = {
    INITIAL: t('kb.status.initial'),
    CLEANING: t('kb.status.cleaning'),
    READING: t('kb.status.reading'),
    SPLITTING: t('kb.status.splitting'),
    EMBEDDING: t('kb.status.embedding'),
    COMPLETED: t('kb.status.completed'),
    FAILED: t('kb.status.failed'),
    STOPPED: t('kb.status.stopped'),
  }
  return status ? map[status] || status : t('common.status.loading')
})

const statusTagType = computed(() => {
  if (optimisticStatus.value === 'STARTING') return 'primary'
  if (optimisticStatus.value === 'STOPPING') return 'warning'

  const status = statusInfo.value?.file_status
  const map: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
    INITIAL: 'info',
    CLEANING: 'primary',
    READING: 'primary',
    SPLITTING: 'primary',
    EMBEDDING: 'primary',
    COMPLETED: 'success',
    FAILED: 'danger',
    STOPPED: 'warning',
  }
  return status ? map[status] || 'info' : 'info'
})

const savedConfig = computed<KBSplitterConfig | undefined>(() => {
  return props.resource.kb_config || undefined
})

const isConfigDirty = computed(() => {
  const saved = savedConfig.value
  if (!saved) return true

  if (taskConfig.splitter_type !== saved.splitter_type) return true
  if (taskConfig.chunk_size !== saved.chunk_size) return true
  if (taskConfig.chunk_overlap !== saved.chunk_overlap) return true

  const formSep = taskConfig.splitter_type === 'separator' ? taskConfig.separator : null
  const savedSep = saved.separator || null
  if (formSep !== savedSep) return true

  return false
})

// --- Methods ---

const loadInitialConfig = () => {
  const saved = savedConfig.value
  if (saved) {
    taskConfig.splitter_type = saved.splitter_type
    taskConfig.chunk_size = saved.chunk_size
    taskConfig.chunk_overlap = saved.chunk_overlap
    if (saved.separator) {
      taskConfig.separator = saved.separator
    }
  } else {
    // 使用全局配置作为默认值
    taskConfig.splitter_type = 'simple'
    taskConfig.chunk_size = settingsStore.globalSettings.kb_default_chunk_size ?? 500
    taskConfig.chunk_overlap = settingsStore.globalSettings.kb_default_chunk_overlap ?? 50
    taskConfig.separator = '\\n\\n'
  }
}

const handleSaveConfig = async () => {
  if (!configFormRef.value) return false
  try {
    await configFormRef.value.validate()
  } catch {
    return false
  }
  const success = await saveConfig(taskConfig)
  if (success) {
    ElMessage.success(t('kb.msg.configSaved'))
  } else {
    ElMessage.error(t('kb.msg.saveFailed'))
  }
  return success
}

const handleStart = async () => {
  if (isConfigDirty.value) {
    const saved = await handleSaveConfig()
    if (!saved) return
  }
  if (hasIndexedData.value) {
    try {
      await ElMessageBox.confirm(
        t('kb.msg.confirmOverwrite'),
        t('common.action.confirm'),
        { confirmButtonText: t('kb.msg.overwriteBtn'), cancelButtonText: t('common.action.cancel'), type: 'warning' },
      )
    } catch {
      return
    }
  }
  try {
    await startTask(taskConfig, isConfigDirty.value)
    ElMessage.success(t('kb.msg.taskStarted'))
    fetchChunks()
  } catch (error) {
    ElMessage.error(t('kb.msg.taskStartFailed'))
  }
}

const handleResume = async () => {
  try {
    await resumeTask()
    ElMessage.success(t('kb.msg.taskResumed'))
  } catch (error: any) {
    const detail = error as KBResumeConflictErrorDetail
    const current = detail.current_config
    const last = detail.last_ingest_config
    const msg = t('kb.msg.conflictMsg', {
      currentSize: current.chunk_size,
      currentOverlap: current.chunk_overlap,
      lastSize: last.chunk_size,
      lastOverlap: last.chunk_overlap
    })
    try {
      await ElMessageBox.confirm(msg, t('kb.msg.conflictTitle'), {
        confirmButtonText: t('kb.msg.reprocess'),
        cancelButtonText: t('common.action.cancel'),
        type: 'warning',
        dangerouslyUseHTMLString: true,
      })
      handleStart()
    } catch {
      // User canceled
    }
  }
}

const handleStop = async () => {
  try {
    // 暂使用硬编码或通用确认，因 locale 中未明确定义停止确认消息
    await ElMessageBox.confirm('确定要停止当前任务吗？', t('kb.task.stop'), {
      confirmButtonText: t('kb.task.stop'),
      cancelButtonText: t('common.action.cancel'),
      type: 'warning',
    })
    try {
      await stopTask()
      ElMessage.success(t('kb.msg.taskStopped'))
    } catch (error) {
      ElMessage.error(t('kb.msg.taskStopFailed'))
    }
  } catch {
    // User canceled
  }
}

// --- Chunk Methods ---

const fetchChunks = async () => {
  isLoadingChunks.value = true
  try {
    const res = await getKBFileChunks(props.resource.id, {
      page: currentPage.value,
      page_size: pageSize.value,
    })
    chunkList.value = res.items
    totalChunks.value = res.total
    expandedChunks.value.clear()
  } catch (error) {
    console.error('Failed to fetch chunks', error)
  } finally {
    isLoadingChunks.value = false
  }
}

const handlePageChange = () => {
  fetchChunks()
}

const toggleExpand = (chunkId: string) => {
  if (expandedChunks.value.has(chunkId)) {
    expandedChunks.value.delete(chunkId)
  } else {
    expandedChunks.value.add(chunkId)
  }
}

const isExpanded = (chunkId: string) => {
  return expandedChunks.value.has(chunkId)
}

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const getChunkStatusType = (status: string) => {
  const map: Record<string, TagType> = {
    PENDING: 'info',
    COMPLETED: 'success',
    FAILED: 'danger',
    STOPPED: 'warning',
  }
  return map[status] || 'info'
}

// --- Watchers & Lifecycle ---

watch(
  savedConfig,
  (newConfig) => {
    if (newConfig) {
      loadInitialConfig()
    }
  },
  { deep: true },
)

watch(
  () => props.resource.id,
  (newId, oldId) => {
    if (newId !== oldId) {
      loadInitialConfig()
      startSSE()
      currentPage.value = 1
      fetchChunks()
    }
  },
)

watch(
  () => statusInfo.value?.file_status,
  (newStatus, oldStatus) => {
    if (newStatus === 'COMPLETED' && oldStatus !== 'COMPLETED') {
      fetchChunks()
    }
  },
)

onMounted(async () => {
  // 确保获取最新的全局配置，以便使用正确的默认值
  await settingsStore.fetchGlobalSettings()
  loadInitialConfig()
  startSSE()
  fetchChunks()
})
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

.stale-tag {
  margin-left: 8px;
}

.detail-content {
  flex-grow: 1;
}

.content-wrapper {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.top-section {
  align-items: stretch;
}

.h-full {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.h-full .el-card__body) {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header-actions {
  display: flex;
  gap: 8px;
}

.config-form {
  flex-grow: 1;
}

.label-with-tooltip {
  display: flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--el-text-color-secondary);
  cursor: help;
  font-size: 14px;
}

.help-icon:hover {
  color: var(--el-color-primary);
}

.w-full {
  width: 100%;
  display: flex;
}

.flex-1 {
  flex: 1;
}

/* Status Body Layout */
.status-body {
  display: flex;
  height: 100%;
  gap: 24px;
  align-items: center;
  padding: 10px 0;
}

.progress-circle-area {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  padding-left: 16px;
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

.stats-grid-area {
  flex-grow: 1;
  padding-right: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(3, 1fr);
  gap: 16px;
  width: 100%;
}

.stat-item {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 8px 12px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-family: monospace;
}

.stat-value.success {
  color: var(--el-color-success);
}
.stat-value.primary {
  color: var(--el-color-primary);
}
.stat-value.danger {
  color: var(--el-color-danger);
}
.stat-value.warning {
  color: var(--el-color-warning);
}

/* Chunk List Styles */
.chunk-total-badge {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
  background-color: var(--el-fill-color);
  padding: 2px 8px;
  border-radius: 10px;
}

.chunks-container {
  min-height: 200px;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 12px;
  transition: all 0.2s;
}

.chunk-item:hover {
  border-color: var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
}

.chunk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chunk-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.byte-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.chunk-body {
  position: relative;
}

.chunk-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  word-break: break-all;
  white-space: pre-wrap;
  transition: max-height 0.3s ease;
}

.chunk-text.collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: pointer;
}

.expand-btn {
  margin-top: 4px;
  padding: 0;
  height: auto;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* Error Info Styles */
.error-info-area {
  width: 100%;
  margin-top: 12px;
  padding: 0 8px;
}

.error-info-area :deep(.el-alert__description) {
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 4px;
}

.chunk-error-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
  background-color: var(--el-color-danger-light-9);
  border-left: 3px solid var(--el-color-danger);
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.4;
}

.chunk-error-label {
  color: var(--el-color-danger);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.chunk-error-text {
  color: var(--el-text-color-primary);
  word-break: break-all;
  font-family: monospace;
}</style>
