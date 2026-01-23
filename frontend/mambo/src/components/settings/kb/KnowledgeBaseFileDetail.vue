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
        <!-- 1. 任务配置卡片 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <div class="card-header">
              <span>切分配置</span>
              <el-button
                type="primary"
                size="small"
                :disabled="!isConfigDirty || isProcessing"
                :loading="isSubmitting"
                @click="handleSaveConfig"
              >
                保存配置
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

        <!-- 2. 进度概览卡片 -->
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
                <!-- 启动/重新启动任务 -->
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
import { runKBFileTask, subscribeToKBFileProgress, updateKBFileConfig } from '@/api/kbService'
import { useResourceStore } from '@/stores/resourceStore'
import type {
  Resource,
  KBChunkStatus,
  SplitterType,
  KBTaskProgressPayload,
  KBSplitterConfig,
  KBResumeConflictErrorDetail,
  KBFileStatus
} from '@/api/types'

// --- Props ---
const props = defineProps<{
  resource: Resource
}>()

// --- Store ---
const resourceStore = useResourceStore()

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
  const s = statusInfo.value?.file_status
  if (!s) return false
  return ['CLEANING', 'READING', 'SPLITTING', 'EMBEDDING'].includes(s)
})

const hasIndexedData = computed(() => {
  return statusInfo.value?.file_status === 'COMPLETED' || (statusInfo.value?.total_chunks || 0) > 0
})

const canResume = computed(() => {
  if (!statusInfo.value) return false
  const s = statusInfo.value.file_status
  return s === 'FAILED' || s === 'STOPPED'
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
  if (s === 'COMPLETED') return 'success'
  return ''
})

const statusLabel = computed(() => {
  const status = statusInfo.value?.file_status
  const map: Record<string, string> = {
    INITIAL: '待处理',
    CLEANING: '清理中',
    READING: '读取中',
    SPLITTING: '切分中',
    EMBEDDING: '向量化中',
    COMPLETED: '已完成',
    FAILED: '失败',
    STOPPED: '已停止',
  }
  return status ? map[status] || status : '加载中...'
})

const statusTagType = computed(() => {
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

// 获取当前资源保存的配置
const savedConfig = computed<KBSplitterConfig | undefined>(() => {
  return props.resource.latest_version?.attributes?.splitter_config
})

// 脏检查：表单值 vs 已保存的配置
const isConfigDirty = computed(() => {
  const saved = savedConfig.value
  if (!saved) return true // 如果没有保存过配置，视为 Dirty (需要保存默认值)

  // 比较各项值
  if (taskConfig.splitter_type !== saved.splitter_type) return true
  if (taskConfig.chunk_size !== saved.chunk_size) return true
  if (taskConfig.chunk_overlap !== saved.chunk_overlap) return true

  // 比较 separator (注意 null/undefined 处理)
  const formSep = taskConfig.splitter_type === 'separator' ? taskConfig.separator : null
  const savedSep = saved.separator || null
  if (formSep !== savedSep) return true

  return false
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
  // 建立连接时显示 Loading，收到第一条消息后取消
  isLoading.value = true

  sseController = subscribeToKBFileProgress({
    resourceId: props.resource.id,
    onMessage: (data: KBTaskProgressPayload) => {
      isLoading.value = false

      // 1. 处理快照数据 (Snapshot) - 包含 total_chunks 字段
      if ('total_chunks' in data) {
        statusInfo.value = data
      }
      // 2. 处理流式事件 (Stream Event) - 包含 processed/total 字段
      else {
        // 确保 statusInfo 已初始化 (通常 Snapshot 会先到达)
        if (statusInfo.value) {
          statusInfo.value.file_status = data.status
          statusInfo.value.message = data.message

          // 如果是 Embedding 阶段，利用 processed/total 更新进度条数据
          // 注意：不要直接覆盖 total_chunks，除非在 Embedding 阶段它代表了确切的切片总数
          if (data.status === 'EMBEDDING') {
             statusInfo.value.completed_chunks = data.processed
             statusInfo.value.total_chunks = data.total
             statusInfo.value.pending_chunks = Math.max(0, data.total - data.processed)
          }
        }
      }

      // 获取当前统一状态以判断是否结束
      const currentStatus: KBFileStatus = 'file_status' in data ? data.file_status : data.status

      if (currentStatus === 'COMPLETED') {
        ElMessage.success('任务已完成')
      } else if (currentStatus === 'FAILED') {
        ElMessage.error(`任务失败: ${data.message || '未知错误'}`)
      } else if (currentStatus === 'STOPPED') {
        ElMessage.warning('任务已停止')
      }
    },
    onError: (err) => {
      console.error('SSE Error:', err)
      stopSSE()
      isLoading.value = false
    },
    onClose: () => {
      sseController = null
      isLoading.value = false
    },
  })
}

const manualRefresh = () => {
  // 重新建立 SSE 连接以获取最新快照
  startSSE()
}

const handleSaveConfig = async () => {
  if (!configFormRef.value) return false

  try {
    await configFormRef.value.validate()
  } catch {
    return false
  }

  isSubmitting.value = true
  try {
    const configToSave: KBSplitterConfig = {
      splitter_type: taskConfig.splitter_type,
      chunk_size: taskConfig.chunk_size,
      chunk_overlap: taskConfig.chunk_overlap,
      separator: taskConfig.splitter_type === 'separator' ? taskConfig.separator : null
    }

    const updatedResource = await updateKBFileConfig(props.resource.id, {
      splitter_config: configToSave
    })

    // 同步更新本地 Store 中的资源属性，确保 Dirty Check 状态正确复位
    if (updatedResource.latest_version?.attributes) {
      resourceStore.updateResourceAttributes(props.resource.id, updatedResource.latest_version.attributes)
    }

    ElMessage.success('配置已保存')
    return true
  } catch (error) {
    console.error('Save config failed', error)
    ElMessage.error('保存配置失败')
    return false
  } finally {
    isSubmitting.value = false
  }
}

const handleStart = async () => {
  // 1. 如果配置有变更，强制先保存
  if (isConfigDirty.value) {
    const saveSuccess = await handleSaveConfig()
    if (!saveSuccess) return // 保存失败则终止
  }

  // 2. 确认覆盖旧数据
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
    // 3. 启动任务 (不再携带配置参数)
    await runKBFileTask(props.resource.id, {
      action: 'start'
    })
    ElMessage.success('任务已启动')
    // 任务启动后，确保 SSE 连接处于活跃状态
    if (!sseController) {
      startSSE()
    }
  } catch (error) {
    console.error('Start task failed', error)
    ElMessage.error('启动任务失败')
  } finally {
    isSubmitting.value = false
  }
}

const handleResume = async () => {
  isSubmitting.value = true
  try {
    await runKBFileTask(props.resource.id, {
      action: 'resume',
    })
    ElMessage.success('任务已继续')
    if (!sseController) {
      startSSE()
    }
  } catch (error: any) {
    // 处理 409 Conflict (配置不一致)
    if (error.response && error.response.status === 409) {
      const detail = error.response.data.detail as KBResumeConflictErrorDetail

      const current = detail.current_config
      const last = detail.last_ingest_config

      const msg = `
        <p>检测到配置变更，无法继续上次任务。</p>
        <p><strong>当前配置:</strong> Size=${current.chunk_size}, Overlap=${current.chunk_overlap}</p>
        <p><strong>上次配置:</strong> Size=${last.chunk_size}, Overlap=${last.chunk_overlap}</p>
        <p>请选择"重新处理"以应用新配置。</p>
      `

      try {
        await ElMessageBox.confirm(msg, '配置冲突', {
          confirmButtonText: '重新处理',
          cancelButtonText: '取消',
          type: 'warning',
          dangerouslyUseHTMLString: true
        })
        // 用户选择重新处理，调用 Start 逻辑
        handleStart()
      } catch {
        // 用户取消
      }
    } else {
      console.error('Resume task failed', error)
      ElMessage.error('继续任务失败')
    }
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
  // 优先从当前保存的配置回显
  const saved = savedConfig.value

  if (saved) {
    taskConfig.splitter_type = saved.splitter_type
    taskConfig.chunk_size = saved.chunk_size
    taskConfig.chunk_overlap = saved.chunk_overlap
    if (saved.separator) {
      taskConfig.separator = saved.separator
    }
  } else {
    // 默认值
    taskConfig.splitter_type = 'simple'
    taskConfig.chunk_size = 500
    taskConfig.chunk_overlap = 50
    taskConfig.separator = '\\n\\n'
  }
}

// --- Lifecycle ---

onMounted(() => {
  loadInitialConfig()
  // 直接启动 SSE 获取状态快照，替代已废弃的 GET 状态接口
  startSSE()
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
      startSSE()
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
