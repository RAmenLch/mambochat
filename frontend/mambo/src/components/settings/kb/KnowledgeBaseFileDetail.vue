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
                <el-form-item label="切分方式" prop="splitter_type">
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
                <el-button
                  v-if="isProcessing"
                  type="danger"
                  size="small"
                  :loading="isSubmitting"
                  @click="handleStop"
                >
                  停止任务
                </el-button>
                <el-button
                  v-if="canResume"
                  type="warning"
                  size="small"
                  :loading="isSubmitting"
                  @click="handleResume"
                >
                  继续任务
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
          </el-descriptions-item>
          <el-descriptions-item label="内容状态" v-if="statusInfo?.is_stale">
            <el-tag type="warning" effect="dark">
              <el-icon><Warning /></el-icon> 内容已更新，需重新嵌入
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Document, QuestionFilled, Warning } from '@element-plus/icons-vue'
import { useKBFileTask } from '@/composables/useKBFileTask'
import type {
  Resource,
  KBChunkStatus,
  SplitterType,
  KBSplitterConfig,
  KBResumeConflictErrorDetail,
} from '@/api/types'

const props = defineProps<{
  resource: Resource
}>()

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

const startButtonText = computed(() => {
  if (optimisticStatus.value === 'STARTING') return '启动中...'
  if (statusInfo.value?.file_status === 'INITIAL') return '开始切分与嵌入'
  return hasIndexedData.value ? '重新切分并嵌入' : '启动切分任务'
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
  if (optimisticStatus.value === 'STARTING') return '启动中...'
  if (optimisticStatus.value === 'STOPPING') return '停止中...'

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

const savedConfig = computed<KBSplitterConfig>(() => {
  return props.resource.kb_config
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
    taskConfig.splitter_type = 'simple'
    taskConfig.chunk_size = 500
    taskConfig.chunk_overlap = 50
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
    ElMessage.success('配置已保存')
  } else {
    ElMessage.error('保存配置失败')
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
        '该文件已有向量数据，重新启动将覆盖旧数据，是否继续？',
        '确认覆盖',
        { confirmButtonText: '覆盖并启动', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }

  try {
    await startTask(taskConfig, isConfigDirty.value)
    ElMessage.success('任务已启动')
  } catch (error) {
    ElMessage.error('启动任务失败')
  }
}

const handleResume = async () => {
  try {
    await resumeTask()
    ElMessage.success('任务已继续')
  } catch (error: any) {
    const detail = error as KBResumeConflictErrorDetail

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
    await ElMessageBox.confirm('确定要停止当前任务吗？', '确认停止', {
      confirmButtonText: '停止',
      cancelButtonText: '取消',
      type: 'warning',
    })

    try {
      await stopTask()
      ElMessage.success('任务已停止')
    } catch (error) {
      ElMessage.error('停止任务失败')
    }
  } catch {
    // User canceled
  }
}

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
    }
  },
)

loadInitialConfig()
startSSE()
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
