<!-- frontend/mambo/src/components/chat/message/ImageRunGallery.vue -->
<template>
  <div class="image-run-gallery">
    <div class="gallery-header">
      <div class="run-switcher">
        <el-button
          :icon="ArrowLeft"
          circle
          text
          size="small"
          :disabled="slot.runs.length <= 1 || isRerunning"
          @click="prevRun"
        />
        <span class="run-indicator">{{ runIndicator }}</span>
        <el-button
          :icon="ArrowRight"
          circle
          text
          size="small"
          :disabled="slot.runs.length <= 1 || isRerunning"
          @click="nextRun"
        />
      </div>

      <div class="run-summary" :title="summaryTitle">{{ summary }}</div>

      <div class="gallery-actions">
        <el-button
          v-if="retryableSubIds.length > 0"
          link
          size="small"
          type="primary"
          :loading="isFetching"
          @click="fetchMissingFiles()"
        >
          {{
            retryableSubIds.length > 1
              ? t('chat.imageRun.fetchAll', { n: retryableSubIds.length })
              : t('chat.imageRun.fetchFile')
          }}
        </el-button>
        <el-button v-if="detailSubId" link size="small" @click="$emit('open-tool-dialog', detailSubId)">
          {{ t('chat.imageRun.params') }}
        </el-button>
        <el-button
          v-if="activeRun?.canRerun"
          link
          size="small"
          :loading="isRerunning"
          @click="openRerunDialog"
        >
          {{ t('chat.imageRun.rerun') }}
        </el-button>
      </div>
    </div>

    <div class="gallery-body">
      <div v-if="activeRun && activeRun.cells.length > 0" class="run-grid">
        <template v-for="cell in activeRun.cells" :key="cell.sub.id">
          <!-- 已落盘：与张数无关，全部铺开 -->
          <SubMessageItem
            v-if="cell.kind === 'file'"
            :sub-message="cell.sub"
            :parent-message="parentMessage"
            :show-header="false"
            :is-inline="false"
            :preview-src-list="previewList"
            :preview-index="previewIndexOf(cell.sub.id)"
            @edit-file="(file) => $emit('edit-file', file)"
          />
          <!-- 超时 / 失败槽位：始终占一格，可单独或整批补录 -->
          <div v-else-if="cell.kind === 'failed'" class="run-slot is-failed">
            <div class="run-slot-head">
              <el-icon><Warning /></el-icon>
              <span class="run-slot-title" :title="slotFilePath(cell.sub)">
                {{ slotFileName(cell.sub) }}
              </span>
            </div>
            <div class="run-slot-reason">{{ slotReasonText(cell.sub) }}</div>
            <div class="run-slot-actions">
              <el-button
                link
                size="small"
                type="primary"
                :loading="isFetching"
                @click="fetchMissingFiles([cell.sub.id])"
              >
                {{ t('chat.imageRun.fetchFile') }}
              </el-button>
            </div>
          </div>
          <!-- 尚未落盘 -->
          <div v-else class="run-slot is-waiting">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span class="run-slot-title" :title="slotFilePath(cell.sub)">
              {{ slotFileName(cell.sub) }}
            </span>
            <div class="run-slot-reason">{{ t('chat.imageRun.waitingSlot') }}</div>
          </div>
        </template>
      </div>

      <div v-else-if="activeRun && activeRun.status === 'failed'" class="run-failed">
        <el-icon><Warning /></el-icon>
        <span class="run-failed-text">{{ failureText }}</span>
        <el-button
          v-if="activeRun?.canRerun"
          link
          size="small"
          @click="openRerunDialog"
        >
          {{ t('chat.imageRun.retry') }}
        </el-button>
      </div>

      <div v-else class="run-pending">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span class="run-pending-text">{{ t('chat.imageRun.pending') }}</span>
      </div>
    </div>

    <div v-if="isRerunning" class="gallery-progress">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>{{ t('chat.imageRun.generating') }}</span>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="t('chat.imageRun.rerunTitle')"
      width="520px"
      append-to-body
    >
      <el-form label-width="96px" label-position="left">
        <el-form-item :label="t('chat.imageRun.prompt')">
          <el-input v-model="form.prompt" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.negativePrompt')">
          <el-input v-model="form.negativePrompt" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.resolution')">
          <el-input v-model="form.resolution" :placeholder="'1024x1024'" />
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.count')">
          <el-input-number v-model="form.count" :min="1" :max="8" />
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.mode')">
          <el-select v-model="form.mode" style="width: 100%">
            <el-option v-for="mode in modeOptions" :key="mode" :label="mode" :value="mode" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.seed')">
          <div class="seed-row">
            <el-input v-model="form.seeds" :placeholder="t('chat.imageRun.seedsPlaceholder')" />
            <el-button text size="small" @click="form.seeds = randomSeed()">
              {{ t('chat.imageRun.randomSeed') }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item :label="t('chat.imageRun.referenceImages')">
          <el-input
            v-model="form.referenceImages"
            type="textarea"
            :rows="2"
            :placeholder="t('chat.imageRun.referenceImagesPlaceholder')"
          />
          <div class="reference-hint">{{ t('chat.imageRun.referenceImagesHint') }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="isRerunning" @click="submitRerun">
          {{ t('chat.imageRun.submit') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Warning, Loading } from '@element-plus/icons-vue'
import type { FileResponse, Message, PendingFileFetchBatchResponse, SubMessage } from '@/api/types'
import { rerunImageRun, updateSubMessage, fetchPendingFiles } from '@/api/chatService'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { describeRunArgs, type ImageRunSlot } from '@/composables/useImageRuns'
import SubMessageItem from '../SubMessageItem.vue'

const props = defineProps<{
  slot: ImageRunSlot
  parentMessage: Message
}>()

const emit = defineEmits<{
  (e: 'open-tool-dialog', subMessageId: string): void
  (e: 'edit-file', file: FileResponse): void
}>()

const { t } = useI18n()
const sessionStore = useChatSessionStore()

const modeOptions = ['Normal', 'Group', 'Mini_Avatar', 'Gal_Avatar', 'Spark']

const activeRunId = ref<string>(props.slot.pinnedRunId)
const isRerunning = ref(false)
const isFetching = ref(false)
const dialogVisible = ref(false)

const form = reactive({
  prompt: '',
  negativePrompt: '',
  resolution: '',
  count: 1,
  mode: 'Normal',
  seeds: '',
  referenceImages: '',
})

const activeRun = computed(
  () => props.slot.runs.find(run => run.runId === activeRunId.value) || props.slot.runs[props.slot.runs.length - 1] || null,
)

const runIndex = computed(() =>
  Math.max(props.slot.runs.findIndex(run => run.runId === activeRun.value?.runId), 0),
)

const runIndicator = computed(() =>
  t('chat.imageRun.runIndicator', { index: runIndex.value + 1, total: props.slot.runs.length }),
)

const summary = computed(() => describeRunArgs(activeRun.value?.args ?? null))

const summaryTitle = computed(() => {
  const prompt = activeRun.value?.args?.prompt
  return typeof prompt === 'string' ? prompt : ''
})

const detailSubId = computed(() => activeRun.value?.recordId || activeRun.value?.toolSubId || null)

/** 预览列表：本次 run 内已落盘的图片（顺序与网格一致） */
const completedFiles = computed(() =>
  (activeRun.value?.cells ?? []).filter(cell => cell.kind === 'file').map(cell => cell.sub),
)

const previewList = computed(() =>
  completedFiles.value.map(file => file.file_info?.url || '').filter(Boolean),
)

function previewIndexOf(subMessageId: string): number {
  return Math.max(
    completedFiles.value.findIndex(file => file.id === subMessageId),
    0,
  )
}

/** 可补录的槽位：失败或尚未落盘、且仍登记着工作区路径 */
const retryableSubIds = computed(() =>
  (activeRun.value?.cells ?? [])
    .filter(cell => cell.kind !== 'file' && !!cell.sub.config?.pending_file_path)
    .map(cell => cell.sub.id),
)

const failureText = computed(() => {
  const run = activeRun.value
  if (!run) return t('chat.imageRun.failed')
  const pending = run.pendingFiles[0]
  const pendingReason = pending?.config?.pending_failed_reason
  if (pendingReason === 'timeout') return t('chat.imageRun.timedOut')
  const record = run.recordId ? props.parentMessage.sub_messages.find(sm => sm.id === run.recordId) : null
  let reason = ''
  if (record?.content) {
    try {
      reason = JSON.parse(record.content)?.result ? JSON.parse(JSON.parse(record.content).result)?.error || '' : ''
    } catch {
      reason = ''
    }
  }
  return reason ? t('chat.imageRun.failedWithReason', { reason }) : t('chat.imageRun.failed')
})

/** 槽位的工作区路径：待生成阶段回退到 pending_file_path */
function slotFilePath(sub: SubMessage): string {
  return sub.config?.show_file_path || sub.config?.pending_file_path || ''
}

function slotFileName(sub: SubMessage): string {
  const path = slotFilePath(sub)
  if (!path) return t('chat.imageRun.waitingSlot')
  return path.split('/').filter(Boolean).pop() || path
}

/** 失败原因文案：与服务端写入的 pending_failed_reason 对应 */
function slotReasonText(sub: SubMessage): string {
  switch (sub.config?.pending_failed_reason) {
    case 'timeout':
      return t('chat.imageRun.reasonTimeout')
    case 'task_failed':
      return t('chat.imageRun.reasonTaskFailed')
    case 'not_produced':
      return t('chat.imageRun.reasonNotProduced')
    case 'no_backend':
      return t('chat.imageRun.reasonNoBackend')
    default:
      return t('chat.imageRun.reasonDownloadFailed')
  }
}

/** 把批量获取结果直接写回子消息（不依赖 SSE 连接是否还在） */
function applyFetchResult(result: PendingFileFetchBatchResponse) {
  for (const item of result.items) {
    const sub = props.parentMessage.sub_messages.find(sm => sm.id === item.sub_message_id)
    if (!sub) continue
    if (item.status === 'completed') {
      if (item.file_id) sub.content = item.file_id
      sub.status = 'completed'
      if (item.file_info) sub.file_info = item.file_info
      sub.config = {
        ...sub.config,
        pending_file_path: undefined,
        pending_file_timeout: undefined,
        pending_failed_reason: undefined,
      }
    } else if (item.status === 'failed') {
      sub.status = 'failed'
      sub.config = { ...sub.config, pending_failed_reason: item.error || 'download_failed' }
    }
  }
}

async function fetchMissingFiles(subMessageIds?: string[]) {
  const targets = (subMessageIds && subMessageIds.length ? subMessageIds : retryableSubIds.value).filter(
    Boolean,
  )
  if (targets.length === 0 || isFetching.value) return
  isFetching.value = true
  try {
    const result = await fetchPendingFiles(targets)
    applyFetchResult(result)
    if (result.completed > 0 && result.failed > 0) {
      ElMessage.warning(t('chat.imageRun.fetchPartial', { n: result.completed, m: result.failed }))
    } else if (result.completed > 0) {
      ElMessage.success(t('chat.imageRun.fetchOk', { n: result.completed }))
    } else if (result.running > 0) {
      ElMessage.info(t('chat.imageRun.fetchRunning'))
    } else {
      ElMessage.error(t('chat.imageRun.fetchFailed'))
    }
  } catch {
    ElMessage.error(t('chat.imageRun.fetchFailed'))
  } finally {
    isFetching.value = false
  }
}

watch(
  () => props.slot.pinnedRunId,
  value => {
    if (value) activeRunId.value = value
  },
)

watch(
  () => props.slot.runs.map(run => run.runId).join(','),
  () => {
    const latest = props.slot.runs[props.slot.runs.length - 1]
    if (latest) activeRunId.value = latest.runId
  },
)

function selectRun(runId: string) {
  activeRunId.value = runId
  const hostId = props.slot.pinnedHostId
  if (!hostId) return
  const host = props.parentMessage.sub_messages.find(sm => sm.id === hostId)
  if (!host) return
  const config = { ...(host.config ?? {}), image_pinned_run_id: runId }
  host.config = config as any
  updateSubMessage(hostId, { config: config as any }).catch(() => {
    /* 置顶只是展示偏好，持久化失败不影响当前视图 */
  })
}

function prevRun() {
  const total = props.slot.runs.length
  if (total <= 1) return
  const next = (runIndex.value - 1 + total) % total
  selectRun(props.slot.runs[next].runId)
}

function nextRun() {
  const total = props.slot.runs.length
  if (total <= 1) return
  const next = (runIndex.value + 1) % total
  selectRun(props.slot.runs[next].runId)
}

function randomSeed(): string {
  return String(Math.floor(Math.random() * 1_000_000_000))
}

/** 参数快照 → 输入框文本：优先 seeds，回落旧字段 extra.seed；多颗用逗号分隔 */
function seedsToInput(seeds: unknown, fallback: unknown): string {
  const source = seeds ?? fallback
  if (Array.isArray(source)) return source.filter(item => item !== null && item !== undefined).join(', ')
  if (source === null || source === undefined || source === '') return ''
  return String(source)
}

/** 输入框文本 → seeds 入参：单颗发数字，多颗发数组；非数字直接提示错误 */
function parseSeeds(raw: string): number | number[] | undefined {
  const items = raw
    .split(/[,，\s]+/)
    .map(item => item.trim())
    .filter(Boolean)
  if (items.length === 0) return undefined
  const values = items.map(item => Number(item))
  if (values.some(value => Number.isNaN(value))) throw new Error('seed')
  return values.length === 1 ? values[0] : values
}

function openRerunDialog() {
  const args = activeRun.value?.args ?? {}
  form.prompt = typeof args.prompt === 'string' ? args.prompt : ''
  form.negativePrompt = typeof args.negative_prompt === 'string' ? args.negative_prompt : ''
  form.resolution = typeof args.resolution === 'string' ? args.resolution : ''
  form.count = Number(args.count) > 0 ? Number(args.count) : 1
  form.mode = typeof args.mode === 'string' ? args.mode : activeRun.value?.mode || 'Normal'
  const extra = args.extra && typeof args.extra === 'object' ? args.extra : {}
  form.seeds = seedsToInput(args.seeds, extra.seed)
  form.referenceImages = Array.isArray(args.reference_images)
    ? (args.reference_images as string[]).join('\n')
    : ''
  dialogVisible.value = true
}

async function submitRerun() {
  // 源子消息只需任取一条：服务端会据此定位插槽与原始参数
  // （失败态没有图片时，用该 run 里未落盘的图片子消息，它同样带参数快照）
  const sourceId =
    activeRun.value?.sourceSubId ||
    props.slot.runs.flatMap(run => run.files).find(Boolean)?.id ||
    null
  if (!sourceId) {
    ElMessage.error(t('chat.imageRun.noSource'))
    return
  }

  let seeds: number | number[] | undefined
  try {
    seeds = parseSeeds(form.seeds)
  } catch {
    ElMessage.error(t('chat.imageRun.seedsInvalid'))
    return
  }

  const referenceImages = form.referenceImages
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)

  isRerunning.value = true
  try {
    const response = await rerunImageRun(sourceId, {
      prompt: form.prompt.trim() || undefined,
      negative_prompt: form.negativePrompt.trim() || undefined,
      resolution: form.resolution.trim() || undefined,
      count: form.count,
      mode: form.mode,
      seeds,
      reference_images: referenceImages.length > 0 ? referenceImages : undefined,
    })

    if (response.record) {
      sessionStore._addOrUpdateSubMessage(props.parentMessage.id, response.record)
    }
    for (const file of response.files || []) {
      sessionStore._addOrUpdateSubMessage(props.parentMessage.id, file)
    }
    // pending：已提交，落盘由平台后台完成，稍后由图区/SSE 自动更新
    if (response.status === 'failed') {
      ElMessage.error(response.error || t('chat.imageRun.failed'))
    }
    dialogVisible.value = false
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.imageRun.failed'))
  } finally {
    isRerunning.value = false
  }
}

</script>

<style scoped>
.image-run-gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  margin: 8px 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-blank);
}

.gallery-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.run-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
}

.run-indicator {
  min-width: 56px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.run-summary {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gallery-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 一次生成的多张图全部铺开：已落盘 / 生成中 / 超时失败各占一格 */
.run-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  align-items: start;
}

.run-slot {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 116px;
  padding: 10px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background-color: var(--el-fill-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.run-slot.is-failed {
  border-color: var(--el-color-danger-light-5);
  color: var(--el-color-danger);
}

.run-slot-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.run-slot-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--el-text-color-regular);
}

.run-slot-reason {
  line-height: 1.5;
}

.run-slot-actions {
  display: flex;
  justify-content: flex-end;
}

.run-failed {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}

.run-pending {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gallery-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.seed-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.reference-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
