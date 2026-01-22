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
          <span class="meta-item">ID: {{ resource.id }}</span>
          <span class="meta-item"
            >上传时间: {{ new Date(resource.createdAt).toLocaleString() }}</span
          >
        </div>
      </div>
      <div class="header-actions">
        <el-button
          @click="manualRefresh"
          :loading="isLoading"
          :icon="RefreshRight"
          circle
          title="刷新状态"
        />
      </div>
    </div>

    <el-scrollbar class="detail-content">
      <div class="content-wrapper">
        <!-- 1. 进度概览卡片 -->
        <el-card shadow="never" class="status-card">
          <template #header>
            <div class="card-header">
              <span>向量化进度</span>
              <div class="card-header-actions">
                <!-- 停止任务 -->
                <el-button
                  v-if="isProcessing"
                  type="danger"
                  size="small"
                  :loading="isSubmitting"
                  @click="handleStop"
                >
                  停止任务
                </el-button>
                <!-- 继续任务 (断点续连) -->
                <el-button
                  v-if="canResume"
                  type="warning"
                  size="small"
                  :loading="isSubmitting"
                  @click="handleResume"
                >
                  继续任务
                </el-button>
              </div>
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
              <el-statistic
                title="已完成"
                :value="statusInfo.completed_chunks"
                value-style="color: var(--el-color-success)"
              />
              <el-statistic
                title="处理中"
                :value="statusInfo.pending_chunks"
                value-style="color: var(--el-color-primary)"
              />
              <el-statistic
                title="失败"
                :value="statusInfo.failed_chunks"
                value-style="color: var(--el-color-danger)"
              />
              <el-statistic
                title="已停止"
                :value="statusInfo.stopped_chunks"
                value-style="color: var(--el-color-warning)"
              />
            </div>
          </div>
          <el-skeleton v-else :rows="3" animated />
        </el-card>

        <!-- 2. 任务配置卡片 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <div class="card-header">
              <span>切分配置</span>
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
          </template>

          <el-form
            ref="configFormRef"
            :model="taskConfig"
            :rules="configRules"
            label-position="top"
            :disabled="isProcessing"
          >
            <el-row :gutter="20">
              <el-col :span="24">
                <el-form-item label="切分方式 (Splitter Type)" prop="splitter_type">
                  <el-radio-group v-model="taskConfig.splitter_type">
                    <el-radio-button label="simple">简单切分 (Simple)</el-radio-button>
                    <el-radio-button label="separator">分隔符切分 (Separator)</el-radio-button>
                  </el-radio-group>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item prop="chunk_size">
                  <template #label>
                    <div class="label-with-tooltip">
                      <span>切片大小 (Chunk Size)</span>
                      <el-tooltip
                        content="单个文本块的最大字符数量。较小的切片更精确，但可能丢失上下文；较大的切片包含更多上下文，但可能包含噪声。"
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
              </el-col>
              <el-col :span="12">
                <el-form-item prop="chunk_overlap">
                  <template #label>
                    <div class="label-with-tooltip">
                      <span>重叠大小 (Overlap)</span>
                      <el-tooltip
                        content="相邻两个文本块之间重复的字符数量。设置重叠可以防止关键信息在切分点被截断，保持语义连贯性。建议设为切片大小的 10%-20%。"
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
              </el-col>
            </el-row>

            <el-form-item v-if="taskConfig.splitter_type === 'separator'" prop="separator">
              <template #label>
                <div class="label-with-tooltip">
                  <span>分隔符 (Separator)</span>
                  <el-tooltip
                    content="用于识别段落边界的字符序列。系统优先使用此分隔符进行切分。常用：\n\n (双换行), \n (单换行)。"
                    placement="top"
                  >
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </div>
              </template>
              <el-input v-model="taskConfig.separator" placeholder="例如: \n\n" />
              <div class="form-tip">支持输入转义字符，如 \n 代表换行。</div>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 3. 详细信息 -->
        <el-descriptions title="文件详情" :column="1" border class="info-descriptions">
          <el-descriptions-item label="文件名称">{{ resource.name }}</el-descriptions-item>
          <el-descriptions-item label="资源路径">{{ resource.id }}</el-descriptions-item>
          <el-descriptions-item label="最后更新">{{
            new Date(resource.updatedAt).toLocaleString()
          }}</el-descriptions-item>
          <el-descriptions-item label="当前状态">
            {{ statusLabel }}
            <span v-if="statusInfo?.message" class="status-message">
              ({{ statusInfo.message }})
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Document, RefreshRight, QuestionFilled } from '@element-plus/icons-vue'
import { getKBFileStatus, runKBFileTask, subscribeToKBFileProgress } from '@/api/kbService'
import type { Resource, KBChunkStatus, SplitterType, KBTaskProgressPayload } from '@/api/types'

// --- Props ---
const props = defineProps<{
  resource: Resource
}>()

// --- Types ---
interface TaskConfigState {
  splitter_type: SplitterType
  chunk_size: number
  chunk_overlap: number
  separator: string
}

// --- State ---
const statusInfo = ref<KBChunkStatus | null>(null)
const isLoading = ref(false)
const isSubmitting = ref(false)
const configFormRef = ref<FormInstance>()
let sseController: AbortController | null = null

const taskConfig = reactive<TaskConfigState>({
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

// --- Computed ---
const isProcessing = computed(() => {
  return statusInfo.value?.file_status === 'PROCESSING'
})

const hasIndexedData = computed(() => {
  return statusInfo.value?.file_status === 'INDEXED' || (statusInfo.value?.total_chunks || 0) > 0
})

const canResume = computed(() => {
  if (!statusInfo.value) return false
  // 仅当状态为 FAILED, STOPPED 或 PENDING 时允许续连
  const s = statusInfo.value.file_status
  return s === 'FAILED' || s === 'STOPPED' || s === 'PENDING'
})

const startButtonText = computed(() => {
  if (statusInfo.value?.file_status === 'INITIAL') return '开始切分与嵌入'
  return hasIndexedData.value ? '重新切分并嵌入' : '启动切分任务'
})

const progressPercentage = computed(() => {
  if (!statusInfo.value || statusInfo.value.total_chunks === 0) return 0
  const percent = (statusInfo.value.completed_chunks / statusInfo.value.total_chunks) * 100
  return Math.min(Math.round(percent), 100)
})

const progressStatus = computed(() => {
  if (!statusInfo.value) return ''
  const s = statusInfo.value.file_status
  if (s === 'FAILED') return 'exception'
  if (s === 'STOPPED') return 'warning'
  if (s === 'INDEXED') return 'success'
  return ''
})

const statusLabel = computed(() => {
  const status = statusInfo.value?.file_status
  const map: Record<string, string> = {
    INITIAL: '待处理',
    PENDING: '等待中',
    PROCESSING: '处理中',
    INDEXED: '已完成',
    FAILED: '失败',
    STOPPED: '已停止',
  }
  return status ? map[status] || status : '加载中...'
})

const statusTagType = computed(() => {
  const status = statusInfo.value?.file_status
  const map: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
    INITIAL: 'info',
    PENDING: 'warning',
    PROCESSING: 'primary',
    INDEXED: 'success',
    FAILED: 'danger',
    STOPPED: 'warning',
  }
  return status ? map[status] || 'info' : 'info'
})

// --- Methods ---

const stopSSE = () => {
  if (sseController) {
    sseController.abort()
    sseController = null
  }
}

const startSSE = () => {
  stopSSE()
  sseController = subscribeToKBFileProgress({
    resourceId: props.resource.id,
    onMessage: (data: KBTaskProgressPayload) => {
      // 实时更新状态
      statusInfo.value = data

      // 如果状态变为非处理中，说明任务已结束（完成、失败或停止），此时后端会发送 end 事件，
      // 但前端也可根据状态变化进行提示并准备断开
      if (data.file_status !== 'PROCESSING') {
        if (data.file_status === 'INDEXED') {
          ElMessage.success('任务已完成')
        } else if (data.file_status === 'FAILED') {
          ElMessage.error(`任务失败: ${data.message || '未知错误'}`)
        } else if (data.file_status === 'STOPPED') {
          ElMessage.warning('任务已停止')
        }
        // 实际上后端会发送 end 事件来触发 close，此处不做主动 abort 也可以，
        // 但为了保险起见，若状态已终结，可视为流结束。
      }
    },
    onError: (err) => {
      console.error('SSE Error:', err)
      // SSE 连接断开通常意味着需要刷新一次完整状态以确保 UI 一致
      stopSSE()
      fetchStatus(false)
    },
    onClose: () => {
      sseController = null
    },
  })
}

const fetchStatus = async (showLoading = true) => {
  if (showLoading) isLoading.value = true
  try {
    const res = await getKBFileStatus(props.resource.id)
    statusInfo.value = res

    // 如果处于处理中状态，建立 SSE 连接
    if (res.file_status === 'PROCESSING') {
      startSSE()
    } else {
      stopSSE()
    }
  } catch (error) {
    console.error('Failed to fetch KB file status', error)
    ElMessage.error('获取状态失败')
  } finally {
    if (showLoading) isLoading.value = false
  }
}

const manualRefresh = () => {
  fetchStatus(true)
}

const handleStart = async () => {
  if (!configFormRef.value) return
  await configFormRef.value.validate(async (valid) => {
    if (valid) {
      if (hasIndexedData.value) {
        try {
          await ElMessageBox.confirm(
            '该文件已有向量数据，重新启动将覆盖旧数据，是否继续？',
            '确认覆盖',
            { confirmButtonText: '覆盖并启动', cancelButtonText: '取消', type: 'warning' },
          )
        } catch {
          return
        }
      }

      isSubmitting.value = true
      try {
        await runKBFileTask(props.resource.id, {
          action: 'start',
          splitter_config: {
            splitter_type: taskConfig.splitter_type,
            chunk_size: taskConfig.chunk_size,
            chunk_overlap: taskConfig.chunk_overlap,
            separator: taskConfig.splitter_type === 'separator' ? taskConfig.separator : undefined,
          },
        })
        ElMessage.success('任务已启动')
        // 启动后立即开启 SSE，利用 SSE 的初始快照更新状态
        startSSE()
      } catch (error) {
        console.error('Start task failed', error)
        ElMessage.error('启动任务失败')
      } finally {
        isSubmitting.value = false
      }
    }
  })
}

const handleResume = async () => {
  isSubmitting.value = true
  try {
    // Resume 模式下不传配置，使用后端存储的上次配置
    await runKBFileTask(props.resource.id, {
      action: 'resume',
    })
    ElMessage.success('任务已继续')
    startSSE()
  } catch (error) {
    console.error('Resume task failed', error)
    ElMessage.error('继续任务失败')
  } finally {
    isSubmitting.value = false
  }
}

const handleStop = async () => {
  try {
    await ElMessageBox.confirm('确定要停止当前任务吗？', '确认停止', {
      confirmButtonText: '停止',
      cancelButtonText: '取消',
      type: 'warning',
    })

    isSubmitting.value = true
    await runKBFileTask(props.resource.id, {
      action: 'stop',
    })
    // 停止操作后，等待 SSE 推送 STOPPED 状态
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Stop task failed', error)
      ElMessage.error('停止任务失败')
    }
  } finally {
    isSubmitting.value = false
  }
}

const loadInitialConfig = () => {
  // 尝试从资源属性中回显上次的配置
  const attrs = props.resource.latest_version?.attributes
  if (attrs && attrs.last_ingest_config) {
    const savedConfig = attrs.last_ingest_config
    taskConfig.splitter_type = savedConfig.splitter_type || 'simple'
    taskConfig.chunk_size = savedConfig.chunk_size || 500
    taskConfig.chunk_overlap = savedConfig.chunk_overlap || 50
    if (savedConfig.separator) {
      taskConfig.separator = savedConfig.separator
    }
  }
}

// --- Lifecycle ---

onMounted(() => {
  loadInitialConfig()
  fetchStatus()
})

onUnmounted(() => {
  stopSSE()
})

watch(
  () => props.resource.id,
  (newId, oldId) => {
    if (newId !== oldId) {
      statusInfo.value = null
      stopSSE()
      loadInitialConfig()
      fetchStatus()
    }
  },
)
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

.status-card,
.config-card {
  border-radius: 8px;
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
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
}

.info-descriptions {
  background-color: #fff;
}

.status-message {
  color: var(--el-text-color-secondary);
  margin-left: 8px;
  font-size: 12px;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
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
</style>
