<!-- frontend/mambo/src/mobile/components/settings/resource/MobileKnowledgeBaseFileDetail.vue -->
<template>
  <div class="mobile-kb-file-detail">
    <el-scrollbar class="main-scroll">
      <div class="content-wrapper">

        <!-- Section 1: Task Configuration -->
        <el-card shadow="never" class="config-card">
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
              </el-radio-group>
            </el-form-item>

            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item prop="chunk_size">
                  <template #label>
                    <div class="label-with-icon">
                      <span>{{ $t('kb.task.chunkSize') }}</span>
                      <el-tooltip :content="$t('kb.task.chunkSizeTooltip')">
                        <el-icon><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-input-number v-model="taskConfig.chunk_size" :min="50" :step="50" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item prop="chunk_overlap">
                  <template #label>
                    <div class="label-with-icon">
                      <span>{{ $t('kb.task.chunkOverlap') }}</span>
                      <el-tooltip :content="$t('kb.task.chunkOverlapTooltip')">
                        <el-icon><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </div>
                  </template>
                  <el-input-number v-model="taskConfig.chunk_overlap" :min="0" :step="10" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item v-if="taskConfig.splitter_type === 'separator'" prop="separator">
              <template #label>
                <div class="label-with-icon">
                  <span>{{ $t('kb.task.separatorChar') }}</span>
                  <el-tooltip :content="$t('kb.task.separatorTooltip')">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </div>
              </template>
              <el-input v-model="taskConfig.separator" placeholder="e.g. \n\n" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Section 2: Status & Progress -->
        <el-card shadow="never" class="status-card">
          <template #header>
            <div class="card-header">
              <span>{{ $t('kb.task.statusTitle') }}</span>
              <div class="header-actions">
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
            <div class="progress-area">
              <el-progress
                type="dashboard"
                :percentage="progressPercentage"
                :status="progressStatus"
                :width="120"
                :stroke-width="8"
              >
                <template #default="{ percentage }">
                  <span class="percent">{{ percentage }}%</span>
                  <span class="label">{{ $t('kb.task.progress') }}</span>
                </template>
              </el-progress>
            </div>

            <div class="stats-grid">
              <div class="stat-item">
                <span class="label">{{ $t('kb.task.completed') }}</span>
                <span class="value success">{{ statusInfo.completed_chunks }}</span>
              </div>
              <div class="stat-item">
                <span class="label">{{ $t('kb.task.pending') }}</span>
                <span class="value primary">{{ statusInfo.pending_chunks }}</span>
              </div>
              <div class="stat-item">
                <span class="label">{{ $t('kb.task.failed') }}</span>
                <span class="value danger">{{ statusInfo.failed_chunks }}</span>
              </div>
              <div class="stat-item">
                <span class="label">{{ $t('kb.task.stopped') }}</span>
                <span class="value warning">{{ statusInfo.stopped_chunks }}</span>
              </div>
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>

        <!-- Section 3: Chunk List -->
        <el-card shadow="never" class="chunks-card">
          <template #header>
            <div class="card-header">
              <span>{{ $t('kb.chunk.title') }}</span>
              <span class="chunk-badge" v-if="totalChunks > 0">{{ totalChunks }}</span>
            </div>
          </template>

          <div v-loading="isLoadingChunks" class="chunks-container">
            <div v-if="chunkList.length > 0" class="chunk-list">
              <div v-for="chunk in chunkList" :key="chunk.id" class="chunk-item">
                <div class="chunk-header" @click="toggleExpand(chunk.id)">
                  <el-tag size="small" type="info">#{{ chunk.chunk_index }}</el-tag>
                  <span class="byte-size">{{ formatBytes(chunk.byte_size) }}</span>
                  <el-tag size="small" :type="getChunkStatusType(chunk.status)" effect="plain">
                    {{ chunk.status }}
                  </el-tag>
                </div>
                <div class="chunk-content" :class="{ expanded: isExpanded(chunk.id) }">
                  {{ chunk.content }}
                </div>
                <el-button
                  v-if="chunk.content && chunk.content.length > 100"
                  link
                  type="primary"
                  size="small"
                  class="expand-btn"
                  @click="toggleExpand(chunk.id)"
                >
                  {{ isExpanded(chunk.id) ? $t('common.action.collapse') : $t('common.action.expand') }}
                </el-button>
              </div>
            </div>
            <el-empty v-else :description="$t('kb.chunk.empty')" :image-size="60" />

            <div class="pagination-area" v-if="totalChunks > 0">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50]"
                layout="prev, pager, next"
                :total="totalChunks"
                small
                @change="fetchChunks"
              />
            </div>
          </div>
        </el-card>

      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
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
  chunk_size: [{ required: true, message: 'Required', trigger: 'change' }],
  chunk_overlap: [{ required: true, message: 'Required', trigger: 'change' }],
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
const pageSize = ref(10) // Smaller for mobile
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
    if (saved.separator) taskConfig.separator = saved.separator
  } else {
    taskConfig.splitter_type = 'simple'
    taskConfig.chunk_size = settingsStore.globalSettings.kb_default_chunk_size ?? 500
    taskConfig.chunk_overlap = settingsStore.globalSettings.kb_default_chunk_overlap ?? 50
    taskConfig.separator = '\\n\\n'
  }
}

const handleSaveConfig = async (): Promise<boolean> => {
  if (!configFormRef.value) return false
  try {
    await configFormRef.value.validate()
  } catch {
    return false
  }
  const success = await saveConfig(taskConfig)
  if (success) ElMessage.success(t('kb.msg.configSaved'))
  else ElMessage.error(t('kb.msg.saveFailed'))
  return success
}

const handleStart = async () => {
  if (isConfigDirty.value) {
    const saved = await handleSaveConfig()
    if (!saved) return
  }
  if (hasIndexedData.value) {
    try {
      await ElMessageBox.confirm(t('kb.msg.confirmOverwrite'), t('common.action.confirm'), { type: 'warning' })
    } catch { return }
  }
  try {
    await startTask(taskConfig, isConfigDirty.value)
    ElMessage.success(t('kb.msg.taskStarted'))
    fetchChunks()
  } catch { ElMessage.error(t('kb.msg.taskStartFailed')) }
}

const handleResume = async () => {
  try {
    await resumeTask()
    ElMessage.success(t('kb.msg.taskResumed'))
  } catch (error: any) {
    const detail = error as KBResumeConflictErrorDetail
    // Simplified conflict handling for mobile
    try {
      await ElMessageBox.confirm(t('kb.msg.conflictMsg'), t('kb.msg.conflictTitle'), { type: 'warning' })
      handleStart()
    } catch {}
  }
}

const handleStop = async () => {
  try {
    await ElMessageBox.confirm('确定停止任务吗？', t('kb.task.stop'), { type: 'warning' })
    await stopTask()
    ElMessage.success(t('kb.msg.taskStopped'))
  } catch {}
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

const toggleExpand = (id: string) => {
  if (expandedChunks.value.has(id)) expandedChunks.value.delete(id)
  else expandedChunks.value.add(id)
}

const isExpanded = (id: string) => expandedChunks.value.has(id)

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const getChunkStatusType = (status: string) => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    PENDING: 'info', COMPLETED: 'success', FAILED: 'danger', STOPPED: 'warning'
  }
  return map[status] || 'info'
}

// --- Watchers & Lifecycle ---

watch(savedConfig, (newConfig) => {
  if (newConfig) loadInitialConfig()
}, { deep: true })

watch(() => props.resource.id, (newId, oldId) => {
  if (newId !== oldId) {
    loadInitialConfig()
    startSSE()
    currentPage.value = 1
    fetchChunks()
  }
})

watch(() => statusInfo.value?.file_status, (newStatus, oldStatus) => {
  if (newStatus === 'COMPLETED' && oldStatus !== 'COMPLETED') fetchChunks()
})

onMounted(async () => {
  await settingsStore.fetchGlobalSettings()
  loadInitialConfig()
  startSSE()
  fetchChunks()
})
</script>

<style scoped>
.mobile-kb-file-detail {
  height: 100%;
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
}

.main-scroll {
  flex: 1;
}

.content-wrapper {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Cards */
.el-card {
  border-radius: 8px;
  border: none;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 15px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Config Form */
.label-with-icon {
  display: flex;
  align-items: center;
  gap: 4px;
}

.w-full {
  width: 100%;
}

/* Status Body */
.status-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.progress-area {
  padding: 10px 0;
}

.percent {
  font-size: 20px;
  font-weight: bold;
  display: block;
}

.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  width: 100%;
}

.stat-item {
  background: var(--el-fill-color-lighter);
  padding: 10px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-item .label {
  font-size: 12px;
  margin-bottom: 4px;
}

.stat-item .value {
  font-size: 18px;
  font-weight: bold;
  font-family: monospace;
}

.value.success { color: var(--el-color-success); }
.value.primary { color: var(--el-color-primary); }
.value.danger { color: var(--el-color-danger); }
.value.warning { color: var(--el-color-warning); }

/* Chunk List */
.chunk-badge {
  background: var(--el-fill-color);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chunk-item {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 10px 0;
}

.chunk-item:last-child {
  border-bottom: none;
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.byte-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto; /* Push to right */
}

.chunk-content {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  white-space: pre-wrap;
  overflow: hidden;
  max-height: 60px;
  transition: max-height 0.3s;
}

.chunk-content.expanded {
  max-height: none;
}

.expand-btn {
  margin-top: 4px;
  padding: 0;
}

.pagination-area {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
