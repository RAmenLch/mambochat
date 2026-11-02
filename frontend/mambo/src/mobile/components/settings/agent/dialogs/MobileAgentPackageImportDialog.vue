<!-- frontend/mambo/src/mobile/components/settings/agent/dialogs/MobileAgentPackageImportDialog.vue — 移动端 Agent 包导入向导 -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="sheet-overlay" @click="close">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>

          <div class="sheet-header">
            <span class="sheet-title">{{ t('agentPackage.importDialog.title') }}</span>
            <button class="sheet-close" @click="close">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="step-bar">
            <span v-for="(label, idx) in stepLabels" :key="label" class="step-item" :class="{ active: step === idx + 1, done: step > idx + 1 }">
              {{ idx + 1 }}. {{ label }}
            </span>
          </div>

          <div class="sheet-body">
            <!-- 步骤 1：选择文件与目标文件夹 -->
            <template v-if="step === 1">
              <div class="field-item">
                <label class="field-label">{{ t('agentPackage.importDialog.selectFile') }}</label>
                <input ref="fileInputRef" type="file" accept=".mamboagent" class="native-input" @change="handleFileChange" />
                <span v-if="file" class="file-hint">{{ file.name }}</span>
              </div>
              <div class="field-item">
                <label class="field-label">{{ t('agentPackage.importDialog.targetFolder') }}</label>
                <el-select v-model="targetFolderId" clearable :placeholder="t('agentPackage.importDialog.targetFolderRoot')" style="width: 100%">
                  <el-option v-for="folder in folderOptions" :key="folder.id" :label="folder.name" :value="folder.id" />
                </el-select>
              </div>
            </template>

            <!-- 步骤 2：预检结果 -->
            <template v-else-if="step === 2 && preview">
              <div class="preview-summary">
                <span>{{ preview.format_version }} / {{ preview.mambochat_version }}</span>
                <span v-if="preview.exported_at">{{ new Date(preview.exported_at).toLocaleString() }}</span>
              </div>

              <div v-if="preview.warnings.length > 0" class="preview-block">
                <div class="block-title">{{ t('agentPackage.preview.warnings') }}</div>
                <el-alert v-for="(warning, idx) in preview.warnings" :key="idx" :title="warning" type="warning" :closable="false" class="block-gap" />
              </div>

              <div v-if="preview.rename_suggestions.length > 0" class="preview-block">
                <div class="block-title">{{ t('agentPackage.preview.renameTitle') }}</div>
                <div v-for="item in preview.rename_suggestions" :key="item.source_id" class="rename-row">
                  <span class="rename-original">{{ item.original_name }}</span>
                  <span class="rename-arrow">→</span>
                  <span class="rename-new">{{ item.new_name }}</span>
                </div>
              </div>

              <div v-if="preview.providers_missing_api_key.length > 0" class="preview-block">
                <div class="block-title">{{ t('agentPackage.preview.providersTitle') }}</div>
                <div class="tag-row">
                  <el-tag v-for="p in preview.providers_missing_api_key" :key="p.source_id" type="warning" size="small">{{ p.name }}</el-tag>
                </div>
              </div>
            </template>

            <!-- 步骤 3：导入结果 -->
            <template v-else-if="step === 3 && report">
              <el-result
                :icon="report.success ? 'success' : 'error'"
                :title="report.success ? t('agentPackage.result.successTitle') : t('agentPackage.result.failedTitle')"
              >
                <template #sub-title>
                  <div v-if="report.success">
                    {{ t('agentPackage.result.createdCount', { count: report.created.length }) }}
                  </div>
                  <div v-else class="result-error">
                    <div v-if="report.failed_phase">{{ t('agentPackage.result.phase') }}: {{ report.failed_phase }}</div>
                    <div v-if="report.failed_entity">{{ t('agentPackage.result.failedEntity') }}: {{ report.failed_entity }}</div>
                    <div v-if="report.error" class="error-text">{{ report.error }}</div>
                  </div>
                </template>
              </el-result>
            </template>
          </div>

          <div class="sheet-footer">
            <button v-if="step > 1 && step < 3" class="footer-btn" @click="step = step - 1">
              {{ t('common.action.back') }}
            </button>
            <button
              v-if="step === 1"
              class="footer-btn primary"
              :disabled="!file || isSubmitting"
              @click="handlePreview"
            >
              {{ isSubmitting ? t('common.status.loading') : t('agentPackage.importDialog.next') }}
            </button>
            <button
              v-else-if="step === 2"
              class="footer-btn primary"
              :disabled="!preview?.importable || isSubmitting"
              @click="handleImport"
            >
              {{ isSubmitting ? t('common.status.loading') : t('agentPackage.importDialog.startImport') }}
            </button>
            <button
              v-if="step === 3 && report && !report.success"
              class="footer-btn"
              :disabled="isSubmitting"
              @click="handleCleanup"
            >
              {{ t('agentPackage.result.cleanRetry') }}
            </button>
            <button v-if="step === 3" class="footer-btn primary" @click="close">
              {{ t('common.action.close') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { useAgentStore } from '@/stores/agentStore'
import { useProviderStore } from '@/stores/providerStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useBackendStore } from '@/stores/backendStore'
import { useMcpStore } from '@/stores/mcpStore'
import {
  cleanupImportSession,
  importAgent,
  importAgentPreview,
} from '@/api/agentPackageService'
import type { AgentPackageImportReport, AgentPackagePreview } from '@/api/types/agentPackageTypes'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'imported', agentId: string): void
}>()

const { t } = useI18n()
const agentStore = useAgentStore()
const providerStore = useProviderStore()
const resourceStore = useResourceStore()
const backendStore = useBackendStore()
const mcpStore = useMcpStore()
const { allAgents } = storeToRefs(agentStore)

const step = ref(1)
const file = ref<File | null>(null)
const targetFolderId = ref<string | null>(null)
const preview = ref<AgentPackagePreview | null>(null)
const report = ref<AgentPackageImportReport | null>(null)
const isSubmitting = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const stepLabels = computed(() => [
  t('agentPackage.importDialog.stepFile'),
  t('agentPackage.importDialog.stepPreview'),
  t('agentPackage.importDialog.stepResult'),
])

const folderOptions = computed(() =>
  allAgents.value.filter(a => a.itemType === 'folder').map(a => ({ id: a.id, name: a.name })),
)

function close() {
  emit('update:visible', false)
}

function reset() {
  step.value = 1
  file.value = null
  targetFolderId.value = null
  preview.value = null
  report.value = null
  isSubmitting.value = false
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

async function handlePreview() {
  if (!file.value || isSubmitting.value) return
  isSubmitting.value = true
  try {
    preview.value = await importAgentPreview(file.value, targetFolderId.value)
    step.value = 2
  } catch (error: any) {
    console.error('Agent package preview failed:', error)
    ElMessage.error(error?.response?.data?.detail || t('common.error.operationFailed'))
  } finally {
    isSubmitting.value = false
  }
}

/** 导入成功后刷新各 store，保持与桌面一致 */
async function refreshStores() {
  await Promise.all([
    agentStore.fetchAllAgents?.().catch(() => undefined),
    providerStore.fetchProviders().catch(() => undefined),
    resourceStore.initializeList?.().catch(() => undefined),
    backendStore.fetchBackends?.().catch(() => undefined),
    mcpStore.fetchAvailableServices?.().catch(() => undefined),
  ])
}

async function handleImport() {
  if (!file.value || isSubmitting.value) return
  isSubmitting.value = true
  try {
    report.value = await importAgent(file.value, targetFolderId.value)
    step.value = 3
    if (report.value.success) {
      await refreshStores()
      if (report.value.main_agent_id) emit('imported', report.value.main_agent_id)
      ElMessage.success(t('agentPackage.result.successTitle'))
    }
  } catch (error: any) {
    console.error('Agent package import failed:', error)
    ElMessage.error(error?.response?.data?.detail || t('common.error.operationFailed'))
  } finally {
    isSubmitting.value = false
  }
}

/** 失败后清理已创建的实体，便于重试 */
async function handleCleanup() {
  const sessionId = report.value?.import_session_id
  if (!sessionId) return
  try {
    await cleanupImportSession(sessionId)
    ElMessage.success(t('agentPackage.result.cleanupSuccess'))
    reset()
  } catch {
    ElMessage.error(t('common.error.operationFailed'))
  }
}

watch(
  () => props.visible,
  visible => {
    if (visible) reset()
  },
)

defineExpose({ handleCleanup })
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0, 0, 0, 0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 560px; max-height: 90vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0, 0, 0, 0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); }
.step-bar { display: flex; gap: 8px; padding: 0 16px 8px; flex-wrap: wrap; }
.step-item { font-size: 12px; color: var(--el-text-color-secondary); }
.step-item.active { color: var(--el-color-primary); font-weight: 600; }
.step-item.done { color: var(--el-color-success); }
.sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 16px 8px; }
.field-item { margin-bottom: 12px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 14px; background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; box-sizing: border-box; }
.file-hint { display: block; margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); word-break: break-all; }
.preview-summary { display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.preview-block { margin-bottom: 12px; }
.block-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 6px; }
.block-gap { margin-bottom: 6px; }
.rename-row { display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 0; }
.rename-original { color: var(--el-text-color-secondary); word-break: break-all; }
.rename-arrow { color: var(--el-text-color-placeholder); }
.rename-new { color: var(--el-color-primary); word-break: break-all; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; }
.result-error { font-size: 12px; color: var(--el-text-color-secondary); word-break: break-word; }
.error-text { margin-top: 4px; color: var(--el-color-danger); }
.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid var(--el-border-color-lighter); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.footer-btn.primary { background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); color: #fff; }
.footer-btn:disabled { opacity: 0.5; }
.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
</style>
