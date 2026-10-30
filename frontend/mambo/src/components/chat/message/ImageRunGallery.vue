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
      <template v-if="activeRun && activeRun.files.length > 0">
        <div class="run-main">
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
        </div>
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

      <div v-else class="run-failed">
        <el-icon><Warning /></el-icon>
        <span class="run-failed-text">{{ failureText }}</span>
        <el-button link size="small" @click="openRerunDialog">
          {{ t('chat.imageRun.retry') }}
        </el-button>
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
            <el-input v-model="form.seed" placeholder="-1 / 12345" />
            <el-button text size="small" @click="form.seed = randomSeed()">
              {{ t('chat.imageRun.randomSeed') }}
            </el-button>
          </div>
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
import type { FileResponse, Message, SubMessage } from '@/api/types'
import { rerunImageRun, updateSubMessage } from '@/api/chatService'
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
const dialogVisible = ref(false)

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

const summaryTitle = computed(() => {
  const prompt = activeRun.value?.args?.prompt
  return typeof prompt === 'string' ? prompt : ''
})

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

const failureText = computed(() => {
  const run = activeRun.value
  if (!run) return t('chat.imageRun.failed')
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

function openRerunDialog() {
  const args = activeRun.value?.args ?? {}
  form.prompt = typeof args.prompt === 'string' ? args.prompt : ''
  form.negativePrompt = typeof args.negative_prompt === 'string' ? args.negative_prompt : ''
  form.resolution = typeof args.resolution === 'string' ? args.resolution : ''
  form.count = Number(args.count) > 0 ? Number(args.count) : 1
  form.mode = typeof args.mode === 'string' ? args.mode : activeRun.value?.mode || 'Normal'
  const extra = args.extra && typeof args.extra === 'object' ? args.extra : {}
  form.seed = extra.seed === undefined || extra.seed === null ? '' : String(extra.seed)
  dialogVisible.value = true
}

async function submitRerun() {
  // 源图片只需任取插槽内的一张：服务端会据此定位插槽与原始参数
  const source =
    activeRun.value?.files[0] ||
    props.slot.runs.flatMap(run => run.files)[0] ||
    null
  if (!source) {
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
    const response = await rerunImageRun(source.id, {
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
    if (response.status !== 'completed') {
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

.run-main {
  max-width: 100%;
}

.run-thumbs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.run-thumbs img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 4px;
  border: 2px solid transparent;
  cursor: pointer;
}

.run-thumbs img.is-active {
  border-color: var(--el-color-primary);
}

.run-failed {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  font-size: 12px;
  color: var(--el-color-danger);
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
</style>
