// frontend/mambo/src/composables/useCheckpointCleanup.ts
// checkpoints.db 清理（VACUUM）：状态查询 + 触发 + 进度轮询，桌面与移动端共用。

import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import i18n from '@/i18n'
import {
  getCheckpointCleanupStatus,
  triggerCheckpointCleanup,
  type CheckpointCleanupStatus,
} from '@/api/settingsService'

export type CleanupStatus = CheckpointCleanupStatus['status']

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** idx).toFixed(1)} ${units[idx]}`
}

/**
 * @param autoLoad 是否在挂载时自动拉取状态（默认 true）
 */
export function useCheckpointCleanup(options: { autoLoad?: boolean } = {}) {
  const t = i18n.global.t

  const status = ref<CleanupStatus>('idle')
  const progress = ref(0)
  const message = ref('')
  const reclaimableBytes = ref(0)
  const freedBytes = ref(0)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const isRunning = computed(() => status.value === 'running')

  function apply(next: CheckpointCleanupStatus) {
    status.value = next.status
    progress.value = Math.round(next.progress ?? 0)
    message.value = next.message ?? ''
    reclaimableBytes.value = next.reclaimable_bytes ?? 0
    freedBytes.value = next.freed_bytes ?? 0
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const next = await getCheckpointCleanupStatus()
        apply(next)
        if (next.status !== 'running') {
          stopPolling()
          if (next.status === 'done') {
            ElMessage.success(t('settings.global.cleanupDone', { size: formatBytes(next.freed_bytes) }))
          } else if (next.status === 'failed') {
            ElMessage.error(next.message || t('settings.global.cleanupFailed'))
          }
        }
      } catch {
        stopPolling()
      }
    }, 2000)
  }

  /** 拉取一次状态；后端正在清理时恢复轮询 */
  async function refresh() {
    try {
      const next = await getCheckpointCleanupStatus()
      apply(next)
      if (next.status === 'running') startPolling()
    } catch {
      // 状态查询失败不影响设置页
    }
  }

  /** 触发清理（不做二次确认，调用方负责确认） */
  async function trigger(): Promise<void> {
    try {
      const next = await triggerCheckpointCleanup()
      apply(next)
      if (next.status === 'running') {
        startPolling()
      } else if (next.status === 'skipped') {
        ElMessage.warning(next.message || t('settings.global.cleanupSkipped'))
      }
    } catch {
      ElMessage.error(t('settings.global.cleanupTriggerFailed'))
    }
  }

  /** 带二次确认的触发：清理期间无法对话，避免误触 */
  async function triggerWithConfirm(): Promise<void> {
    if (isRunning.value) return
    try {
      await ElMessageBox.confirm(
        t('settings.global.cleanupTip'),
        t('settings.global.cleanupConfirmTitle'),
        { type: 'warning', confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') },
      )
    } catch {
      return
    }
    await trigger()
  }

  onUnmounted(stopPolling)

  if (options.autoLoad !== false) {
    onMounted(refresh)
  }

  return {
    status,
    progress,
    message,
    reclaimableBytes,
    freedBytes,
    isRunning,
    refresh,
    trigger,
    triggerWithConfirm,
    formatBytes,
  }
}
