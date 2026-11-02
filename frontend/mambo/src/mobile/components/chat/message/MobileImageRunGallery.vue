<!-- frontend/mambo/src/mobile/components/chat/message/MobileImageRunGallery.vue — 移动端生图结果按批次分组/切换/重跑 -->
<template>
  <div class="mobile-image-run-gallery">
    <!-- 批次切换 -->
    <div class="gallery-header">
      <button class="run-nav" :disabled="slot.runs.length <= 1 || isRerunning" @click="prevRun">
        <el-icon :size="16"><ArrowLeft /></el-icon>
      </button>
      <span class="run-indicator">{{ runIndicator }}</span>
      <button class="run-nav" :disabled="slot.runs.length <= 1 || isRerunning" @click="nextRun">
        <el-icon :size="16"><ArrowRight /></el-icon>
      </button>
      <span class="run-summary">{{ summary }}</span>
    </div>

    <!-- 图片主体 -->
    <div class="gallery-body">
      <template v-if="activeRun && activeRun.files.length > 0">
        <SubMessageItem
          v-if="mainFile"
          :sub-message="mainFile"
          :parent-message="parentMessage"
          :show-header="false"
          :is-inline="false"
          :preview-src-list="previewList"
          :preview-index="previewIndex"
          @edit-file="(file) => $emit('edit-file', file)"
        />
        <div v-if="activeRun.files.length > 1" class="run-thumbs">
          <img
            v-for="file in activeRun.files"
            :key="file.id"
            :src="file.file_info?.url"
            :class="{ 'is-active': file.id === pinnedFileId }"
            alt=""
            @click="pinnedFileId = file.id"
          />
        </div>
      </template>

      <div v-else-if="activeRun && activeRun.status === 'failed'" class="run-failed">
        <el-icon><Warning /></el-icon>
        <span class="run-failed-text">{{ failureText }}</span>
        <button v-if="fetchableSubId" class="mini-btn" :disabled="isFetching" @click="fetchFile">
          {{ t('chat.imageRun.fetchFile') }}
        </button>
      </div>

      <div v-else class="run-pending">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ t('chat.imageRun.pending') }}</span>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="gallery-actions">
      <button v-if="detailSubId" class="mini-btn" @click="$emit('open-tool-dialog', detailSubId)">
        <el-icon :size="14"><Document /></el-icon>
        {{ t('chat.imageRun.params') }}
      </button>
      <button
        v-if="activeRun?.canRerun"
        class="mini-btn primary"
        :disabled="isRerunning"
        @click="openRerunSheet"
      >
        <el-icon :size="14"><RefreshRight /></el-icon>
        {{ activeRun?.status === 'failed' ? t('chat.imageRun.retry') : t('chat.imageRun.rerun') }}
      </button>
    </div>

    <div v-if="isRerunning" class="gallery-progress">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>{{ t('chat.imageRun.generating') }}</span>
    </div>

    <!-- 重跑表单：底部面板 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="sheetVisible" class="rerun-overlay" @click="sheetVisible = false">
          <div class="rerun-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="rerun-title">{{ t('chat.imageRun.rerunTitle') }}</div>
            <div class="rerun-body">
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.prompt') }}</span>
                <textarea v-model="form.prompt" rows="3" class="field-input"></textarea>
              </label>
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.negativePrompt') }}</span>
                <textarea v-model="form.negativePrompt" rows="2" class="field-input"></textarea>
              </label>
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.resolution') }}</span>
                <input v-model="form.resolution" class="field-input" placeholder="1024x1024" />
              </label>
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.count') }}</span>
                <el-input-number v-model="form.count" :min="1" :max="8" size="default" />
              </label>
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.mode') }}</span>
                <el-select v-model="form.mode" style="width: 100%">
                  <el-option v-for="mode in modeOptions" :key="mode" :label="mode" :value="mode" />
                </el-select>
              </label>
              <label class="field">
                <span class="field-label">{{ t('chat.imageRun.seed') }}</span>
                <div class="seed-row">
                  <input v-model="form.seed" class="field-input" placeholder="-1 / 12345" />
                  <button class="mini-btn" @click="form.seed = randomSeed()">
                    {{ t('chat.imageRun.randomSeed') }}
                  </button>
                </div>
              </label>
            </div>
            <div class="rerun-actions">
              <button class="mini-btn" @click="sheetVisible = false">{{ t('common.action.cancel') }}</button>
              <button class="mini-btn primary" :disabled="isRerunning" @click="submitRerun">
                {{ t('chat.imageRun.submit') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Warning, Loading, Document, RefreshRight } from '@element-plus/icons-vue'
import type { FileResponse, Message, SubMessage } from '@/api/types'
import { rerunImageRun, updateSubMessage, fetchPendingFile } from '@/api/chatService'
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
const pinnedFileId = ref<string | null>(null)
const isRerunning = ref(false)
const isFetching = ref(false)
const sheetVisible = ref(false)

const form = reactive({
  prompt: '',
  negativePrompt: '',
  resolution: '',
  count: 1,
  mode: 'Normal',
  seed: '',
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

const detailSubId = computed(() => activeRun.value?.recordId || activeRun.value?.toolSubId || null)

const mainFile = computed<SubMessage | null>(() => {
  const files = activeRun.value?.files ?? []
  if (files.length === 0) return null
  return files.find(file => file.id === pinnedFileId.value) || files[0]
})

const previewList = computed(() =>
  props.slot.runs.flatMap(run => run.files.map(file => file.file_info?.url || '')).filter(Boolean),
)

const previewIndex = computed(() => {
  const target = mainFile.value
  if (!target) return 0
  const all = props.slot.runs.flatMap(run => run.files)
  return Math.max(all.findIndex(file => file.id === target.id), 0)
})

/** 可用于「获取文件」的子消息：本次 run 里失败或未落盘的图片子消息 */
const fetchableSubId = computed(() => {
  const run = activeRun.value
  if (!run || run.pendingFiles.length === 0) return null
  const target = run.pendingFiles.find(sm => sm.status === 'failed') || run.pendingFiles[0]
  return target?.id ?? null
})

const failureText = computed(() => {
  const run = activeRun.value
  if (!run) return t('chat.imageRun.failed')
  const pending = run.pendingFiles[0]
  if (pending?.config?.pending_failed_reason === 'timeout') return t('chat.imageRun.timedOut')
  const record = run.recordId ? props.parentMessage.sub_messages.find(sm => sm.id === run.recordId) : null
  let reason = ''
  if (record?.content) {
    try {
      reason = JSON.parse(JSON.parse(record.content).result)?.error || ''
    } catch {
      reason = ''
    }
  }
  return reason ? t('chat.imageRun.failedWithReason', { reason }) : t('chat.imageRun.failed')
})

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

watch(activeRun, () => {
  pinnedFileId.value = null
})

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
  selectRun(props.slot.runs[(runIndex.value - 1 + total) % total].runId)
}

function nextRun() {
  const total = props.slot.runs.length
  if (total <= 1) return
  selectRun(props.slot.runs[(runIndex.value + 1) % total].runId)
}

function randomSeed(): string {
  return String(Math.floor(Math.random() * 1_000_000_000))
}

function openRerunSheet() {
  const args = activeRun.value?.args ?? {}
  form.prompt = typeof args.prompt === 'string' ? args.prompt : ''
  form.negativePrompt = typeof args.negative_prompt === 'string' ? args.negative_prompt : ''
  form.resolution = typeof args.resolution === 'string' ? args.resolution : ''
  form.count = Number(args.count) > 0 ? Number(args.count) : 1
  form.mode = typeof args.mode === 'string' ? args.mode : activeRun.value?.mode || 'Normal'
  const extra = args.extra && typeof args.extra === 'object' ? args.extra : {}
  form.seed = extra.seed === undefined || extra.seed === null ? '' : String(extra.seed)
  sheetVisible.value = true
}

async function submitRerun() {
  const sourceId =
    activeRun.value?.sourceSubId ||
    props.slot.runs.flatMap(run => run.files).find(Boolean)?.id ||
    null
  if (!sourceId) {
    ElMessage.error(t('chat.imageRun.noSource'))
    return
  }

  const extra: Record<string, any> = {}
  if (form.seed.trim()) {
    const seed = Number(form.seed)
    if (!Number.isNaN(seed)) extra.seed = seed
  }

  isRerunning.value = true
  try {
    const response = await rerunImageRun(sourceId, {
      prompt: form.prompt.trim() || undefined,
      negative_prompt: form.negativePrompt.trim() || undefined,
      resolution: form.resolution.trim() || undefined,
      count: form.count,
      mode: form.mode,
      extra: Object.keys(extra).length > 0 ? extra : undefined,
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
    sheetVisible.value = false
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.imageRun.failed'))
  } finally {
    isRerunning.value = false
  }
}

/** 手动获取文件：查任务 → 下载 → 入库；成功后把子消息就地更新为完成态 */
async function fetchFile() {
  const targetId = fetchableSubId.value
  if (!targetId) return
  isFetching.value = true
  try {
    const res = await fetchPendingFile(targetId)
    if (res.status === 'completed') {
      const target = props.parentMessage.sub_messages.find(sm => sm.id === targetId)
      if (target) {
        target.content = res.file_id || ''
        target.status = 'completed'
        if (res.file_info) target.file_info = res.file_info
        const config = { ...(target.config ?? {}) } as Record<string, any>
        delete config.pending_file_path
        delete config.pending_file_timeout
        delete config.pending_failed_reason
        target.config = config as any
      }
    } else if (res.status === 'running') {
      ElMessage.info(t('chat.attachment.stillGenerating'))
    } else {
      ElMessage.error(res.error || t('chat.imageRun.failed'))
    }
  } catch (error: any) {
    ElMessage.error(error?.message || t('chat.imageRun.failed'))
  } finally {
    isFetching.value = false
  }
}
</script>

<style scoped>
.mobile-image-run-gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background-color: var(--el-fill-color-blank);
}

.gallery-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.run-nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--el-border-color-lighter);
  background: transparent;
  color: var(--el-text-color-regular);
}

.run-nav:disabled {
  opacity: 0.4;
}

.run-indicator {
  min-width: 48px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.run-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-left: 4px;
}

.gallery-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.run-thumbs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.run-thumbs img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 6px;
  border: 2px solid transparent;
  flex-shrink: 0;
}

.run-thumbs img.is-active {
  border-color: var(--el-color-primary);
}

.run-failed,
.run-pending {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.run-failed {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.gallery-actions {
  display: flex;
  gap: 8px;
}

.mini-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.mini-btn.primary {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.mini-btn:disabled {
  opacity: 0.5;
}

.gallery-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 重跑底部面板 */
.rerun-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
}

.rerun-panel {
  width: 100%;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color);
  border-radius: 16px 16px 0 0;
  padding: 0 14px calc(14px + env(safe-area-inset-bottom));
}

.sheet-handle {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background-color: var(--el-border-color);
  margin: 8px auto 4px;
  flex-shrink: 0;
}

.rerun-title {
  padding: 6px 2px 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.rerun-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.field-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  resize: vertical;
}

.seed-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.rerun-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.2s ease;
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
</style>
