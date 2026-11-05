<!-- frontend/mambo/src/mobile/components/settings/MobileImageGenManager.vue — 移动端生图工具配置（卡片 + 底部表单） -->
<template>
  <div class="mobile-image-gen">
    <div class="page-header">
      <div class="title-block">
        <span class="page-title">{{ t('settings.imageGen.title') }}</span>
        <span class="page-subtitle">{{ t('settings.imageGen.subtitle') }}</span>
      </div>
      <el-button size="small" type="primary" :icon="Plus" @click="handleCreate">
        {{ t('settings.imageGen.add') }}
      </el-button>
    </div>

    <div class="standard-hint">
      <span>image_generate / image_task_status / image_download</span>
    </div>

    <el-scrollbar class="list-scroll" v-loading="imageGenStore.isLoading">
      <div class="config-list">
        <div v-for="row in imageGenStore.configs" :key="row.id" class="config-card">
          <div class="card-head">
            <div class="name-block">
              <span class="config-name">{{ row.name }}</span>
              <span v-if="row.description" class="config-desc">{{ row.description }}</span>
            </div>
            <el-tag :type="row.isEnabled ? 'success' : 'danger'" effect="dark" size="small">
              {{ row.isEnabled ? 'ON' : 'OFF' }}
            </el-tag>
          </div>

          <div class="meta-row">
            <span class="meta-item">{{ backendLabel(row) }}</span>
          </div>

          <div class="tag-row">
            <el-tag size="small" effect="plain" :type="row.backendType === 'mcp' ? 'info' : 'success'">
              {{ backendTypeLabel(row.backendType) }}
            </el-tag>
            <el-tag v-if="referenceEnabled(row)" size="small" effect="plain" type="warning">
              {{ t('settings.imageGen.reference.supported') }}
            </el-tag>
            <el-tag size="small" effect="plain">{{ t('settings.imageGen.count', { n: row.defaultCount }) }}</el-tag>
            <el-tag size="small" effect="plain" type="success">{{ row.defaultResolution }}</el-tag>
            <el-tag size="small" effect="plain" type="info">{{ row.defaultSync ? 'sync' : 'async' }}</el-tag>
            <el-tag v-if="row.enableStandardTools" size="small" effect="plain">{{ t('settings.imageGen.tools.standard') }}</el-tag>
            <el-tag v-if="row.enableGenerateShow" size="small" effect="plain" type="warning">{{ t('settings.imageGen.tools.generateShow') }}</el-tag>
          </div>

          <div class="card-actions">
            <el-button size="small" link type="primary" :loading="checkingIds.has(row.id)" @click="handleCheck(row)">
              {{ t('settings.imageGen.check') }}
            </el-button>
            <el-button size="small" link type="primary" @click="handleEdit(row)">
              {{ t('common.action.edit') }}
            </el-button>
            <el-button size="small" link type="danger" @click="handleDelete(row)">
              {{ t('common.action.delete') }}
            </el-button>
          </div>
        </div>

        <el-empty v-if="imageGenStore.configs.length === 0" :description="t('common.msg.noData')" :image-size="60" />
      </div>
    </el-scrollbar>

    <!-- 底部表单 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="sheetVisible" class="sheet-overlay" @click="sheetVisible = false">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ isEditing ? t('settings.imageGen.editTitle') : t('settings.imageGen.createTitle') }}</span>
              <button class="sheet-close" @click="sheetVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>

            <div class="sheet-body">
              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.name') }} *</label>
                <input v-model="form.name" class="native-input" maxlength="100" />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.description') }}</label>
                <textarea v-model="form.description" class="native-textarea" rows="2"></textarea>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.backend') }} *</label>
                <el-radio-group v-model="form.backendType" size="small" @change="onBackendTypeChange">
                  <el-radio-button value="mcp">{{ t('settings.imageGen.backend.mcp') }}</el-radio-button>
                  <el-radio-button value="model">{{ t('settings.imageGen.backend.model') }}</el-radio-button>
                  <el-radio-button value="image_api">{{ t('settings.imageGen.backend.imageApi') }}</el-radio-button>
                </el-radio-group>
                <span class="field-hint">{{ t('settings.imageGen.form.backendHint') }}</span>
              </div>

              <div v-if="form.backendType === 'mcp'" class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.mcpServer') }} *</label>
                <el-select v-model="form.mcpServerId" :placeholder="t('settings.imageGen.form.mcpServerPlaceholder')" style="width: 100%">
                  <el-option v-for="server in selectableServers" :key="server.id" :label="server.name" :value="server.id" />
                </el-select>
              </div>

              <div v-else class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.aiModel') }} *</label>
                <el-select v-model="form.aiModelId" filterable :placeholder="t('settings.imageGen.form.aiModelPlaceholder')" style="width: 100%" @change="onModelChange">
                  <el-option-group v-for="group in modelOptions" :key="group.label" :label="group.label">
                    <el-option v-for="model in group.options" :key="model.id" :label="model.name" :value="model.id" />
                  </el-option-group>
                </el-select>
                <el-checkbox v-if="form.backendType === 'model'" v-model="showAllModels" size="small">{{ t('settings.imageGen.form.showAllModels') }}</el-checkbox>
                <span class="field-hint">
                  {{ form.backendType === 'image_api' ? imageApiHint : t('settings.imageGen.form.aiModelHint') }}
                </span>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.reference') }}</label>
                <el-select v-model="referenceCapabilityModel" style="width: 100%">
                  <el-option :label="t('settings.imageGen.reference.auto')" value="auto" />
                  <el-option :label="t('settings.imageGen.reference.supported')" value="supported" />
                  <el-option :label="t('settings.imageGen.reference.unsupported')" value="unsupported" />
                </el-select>
                <span class="field-hint">
                  {{
                    form.backendType !== 'mcp'
                      ? t('settings.imageGen.form.referenceModelHint')
                      : t('settings.imageGen.form.referenceHint')
                  }}
                </span>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.count') }}</label>
                <el-input-number v-model="form.defaultCount" :min="1" :max="8" controls-position="right" style="width: 100%" />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.resolution') }}</label>
                <el-select v-model="form.defaultResolution" allow-create filterable style="width: 100%">
                  <el-option v-for="option in resolutionPresets" :key="option" :label="option" :value="option" />
                </el-select>
                <span class="field-hint">{{ t('settings.imageGen.form.resolutionHint') }}</span>
              </div>

              <div class="field-row">
                <span class="field-label" style="margin-bottom:0">{{ t('settings.imageGen.form.sync') }}</span>
                <el-switch v-model="form.defaultSync" size="small" />
              </div>
              <span class="field-hint">{{ t('settings.imageGen.form.syncHint') }}</span>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.waitTimeout') }}</label>
                <el-input-number v-model="form.defaultWaitTimeout" :min="0" :max="300" controls-position="right" style="width: 100%" />
                <span class="field-hint">{{ t('settings.imageGen.form.waitTimeoutHint') }}</span>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.timeout') }}</label>
                <el-input-number v-model="form.timeout" :min="1" :controls="false" controls-position="right" style="width: 100%" />
                <span class="field-hint">{{ t('settings.imageGen.form.timeoutHint') }}</span>
              </div>

              <div class="field-row">
                <span class="field-label" style="margin-bottom:0">{{ t('settings.imageGen.form.enabled') }}</span>
                <el-switch v-model="form.isEnabled" size="small" />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.imageGen.form.tools') }} *</label>
                <el-checkbox v-model="form.enableStandardTools">{{ t('settings.imageGen.tools.standard') }}</el-checkbox>
                <el-checkbox v-model="form.enableGenerateShow">{{ t('settings.imageGen.tools.generateShow') }}</el-checkbox>
                <span class="field-hint">{{ t('settings.imageGen.form.toolsHint') }}</span>
              </div>
            </div>

            <div class="sheet-footer">
              <button class="footer-btn" @click="sheetVisible = false">{{ t('common.action.cancel') }}</button>
              <button class="footer-btn primary" :disabled="saving" @click="handleSave">
                {{ saving ? t('common.status.saving') : t('common.action.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Close } from '@element-plus/icons-vue'
import { useImageGenStore } from '@/stores/imageGenStore'
import { useMcpStore } from '@/stores/mcpStore'
import { useProviderStore } from '@/stores/providerStore'
import type { ImageGenBackendType, ImageGenConfig } from '@/api/types'

const { t } = useI18n()
const imageGenStore = useImageGenStore()
const mcpStore = useMcpStore()
const providerStore = useProviderStore()

const sheetVisible = ref(false)
const isEditing = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const checkingIds = ref<Set<string>>(new Set())
const showAllModels = ref(false)

const resolutionPresets = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024', '768x1344', '1344x768']

const form = reactive({
  name: '',
  description: '',
  backendType: 'mcp' as ImageGenBackendType,
  mcpServerId: '',
  aiModelId: '',
  supportsReferenceImages: null as boolean | null,
  defaultCount: 1,
  defaultResolution: '1024x1024',
  defaultSync: true,
  defaultWaitTimeout: 0,
  timeout: undefined as number | undefined,
  enableStandardTools: true,
  enableGenerateShow: true,
  isEnabled: true,
})

const selectableServers = computed(() => mcpStore.availableServices.filter(s => s.isEnabled))

/** 能出图的模型优先（meta_config.output_modalities 含 image） */
function isImageOutputModel(model: any): boolean {
  const modalities = model?.meta_config?.output_modalities
  return Array.isArray(modalities) && modalities.map((m: string) => String(m).toLowerCase()).includes('image')
}

const modelOptions = computed(() => {
  const backend = form.backendType
  return providerStore.providers
    .map(provider => ({
      label: provider.name,
      options: provider.models.filter(model => {
        if (backend === 'image_api') return model.model_type === 'image'
        if (model.model_type === 'image') return false
        return showAllModels.value || isImageOutputModel(model)
      }),
    }))
    .filter(group => group.options.length > 0)
})

function serverName(id: string | null): string {
  if (!id) return '-'
  return mcpStore.availableServices.find(s => s.id === id)?.name || id.slice(0, 8)
}

function modelName(id: string | null): string {
  if (!id) return '-'
  return providerStore.allModels.find(m => m.id === id)?.name || id.slice(0, 8)
}

/** 生图模型的执行器（由所属服务商的 worker_type 决定） */
function executorOfModel(modelId: string | null): { label: string; endpoint: string } | null {
  if (!modelId) return null
  const model = providerStore.allModels.find(m => m.id === modelId)
  if (!model) return null
  const provider = providerStore.providers.find(p => p.id === model.providerId)
  const worker = provider?.worker_type || ''
  if (worker === 'openrouter_images') return { label: 'OpenRouter Images API', endpoint: '/images' }
  if (worker === 'openai_images') return { label: 'OpenAI Images API', endpoint: '/images/generations' }
  const host = (provider?.apiHost || '').toLowerCase()
  if (host.includes('openrouter')) return { label: 'OpenRouter Images API', endpoint: '/images' }
  if (!worker || worker === 'openai' || worker === 'deepseek') {
    return { label: 'OpenAI Images API', endpoint: '/images/generations' }
  }
  return null
}

const imageApiHint = computed(() => {
  if (!form.aiModelId) return t('settings.imageGen.form.imageApiHintEmpty')
  const executor = executorOfModel(form.aiModelId)
  if (!executor) return t('settings.imageGen.form.imageApiHintNoExecutor')
  return t('settings.imageGen.form.imageApiHint', {
    executor: executor.label,
    endpoint: executor.endpoint,
  })
})

function backendTypeLabel(backend: string): string {
  if (backend === 'model') return t('settings.imageGen.backend.model')
  if (backend === 'image_api') return t('settings.imageGen.backend.imageApi')
  return t('settings.imageGen.backend.mcp')
}

function backendLabel(row: ImageGenConfig): string {
  if (row.backendType === 'mcp') return serverName(row.mcpServerId)
  const name = modelName(row.aiModelId)
  if (row.backendType !== 'image_api') return name
  const executor = executorOfModel(row.aiModelId)
  return executor ? `${name} · ${executor.label}` : name
}

/** 列表标签用：显式 true，或模型后端的「自动」（= 按支持处理） */
function referenceEnabled(row: ImageGenConfig): boolean {
  if (row.supportsReferenceImages === true) return true
  return row.supportsReferenceImages === null && row.backendType !== 'mcp'
}

/**
 * 按模型能力推断参考图能力：模型声明了 input_modalities 时据此判断能否吃图，
 * 未声明则返回 null（= 自动，后端对模型后端默认按支持处理）。
 */
function modelCapability(modelId: string): boolean | null {
  const modalities = providerStore.allModels.find(m => m.id === modelId)?.meta_config?.input_modalities
  if (!Array.isArray(modalities) || modalities.length === 0) return null
  return modalities.map(m => String(m).toLowerCase()).includes('image')
}

/** 用户换模型时按能力初始化，之后仍可手动改 */
function onModelChange(modelId: string) {
  if (!modelId) return
  form.supportsReferenceImages = form.backendType === 'image_api' ? null : modelCapability(modelId)
}

/** 切换后端类型时重置为对应默认：MCP 走探测，模型按已选模型能力 */
function onBackendTypeChange(value: string | number | boolean | undefined) {
  form.aiModelId = ''
  form.supportsReferenceImages = null
  if (value === 'model') showAllModels.value = false
}

/** 参考图能力三态（null=自动）：el-select 取值不接受 null，用字符串哨兵中转 */
const referenceCapabilityModel = computed<'auto' | 'supported' | 'unsupported'>({
  get: () => {
    if (form.supportsReferenceImages == null) return 'auto'
    return form.supportsReferenceImages ? 'supported' : 'unsupported'
  },
  set: (value) => {
    form.supportsReferenceImages = value === 'auto' ? null : value === 'supported'
  },
})

function resetForm() {
  form.name = ''
  form.description = ''
  form.backendType = 'mcp'
  form.mcpServerId = ''
  form.aiModelId = ''
  form.supportsReferenceImages = null
  form.defaultCount = 1
  form.defaultResolution = '1024x1024'
  form.defaultSync = true
  form.defaultWaitTimeout = 0
  form.timeout = undefined
  form.enableStandardTools = true
  form.enableGenerateShow = true
  form.isEnabled = true
  showAllModels.value = false
}

function handleCreate() {
  isEditing.value = false
  editingId.value = null
  resetForm()
  sheetVisible.value = true
}

function handleEdit(row: ImageGenConfig) {
  isEditing.value = true
  editingId.value = row.id
  form.name = row.name
  form.description = row.description || ''
  form.backendType = row.backendType === 'model'
    ? 'model'
    : (row.backendType === 'image_api' ? 'image_api' : 'mcp')
  form.mcpServerId = row.mcpServerId || ''
  form.aiModelId = row.aiModelId || ''
  form.supportsReferenceImages = row.supportsReferenceImages ?? null
  form.defaultCount = row.defaultCount
  form.defaultResolution = row.defaultResolution || '1024x1024'
  form.defaultSync = row.defaultSync
  form.defaultWaitTimeout = row.defaultWaitTimeout ?? 0
  form.timeout = row.timeout ?? undefined
  form.enableStandardTools = row.enableStandardTools !== false
  form.enableGenerateShow = row.enableGenerateShow === true
  form.isEnabled = row.isEnabled
  sheetVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning(t('settings.imageGen.form.requiredHint'))
    return
  }
  if (form.backendType === 'mcp' && !form.mcpServerId) {
    ElMessage.warning(t('settings.imageGen.form.mcpServerRequired'))
    return
  }
  if (form.backendType !== 'mcp' && !form.aiModelId) {
    ElMessage.warning(t('settings.imageGen.form.aiModelRequired'))
    return
  }
  if (!form.enableStandardTools && !form.enableGenerateShow) {
    ElMessage.warning(t('settings.imageGen.form.toolsRequired'))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description || null,
      backendType: form.backendType,
      mcpServerId: form.backendType === 'mcp' ? form.mcpServerId : null,
      aiModelId: form.backendType === 'mcp' ? null : form.aiModelId,
      supportsReferenceImages: form.supportsReferenceImages ?? null,
      defaultCount: form.defaultCount || 1,
      defaultResolution: form.defaultResolution || '1024x1024',
      defaultSync: form.defaultSync,
      defaultWaitTimeout: form.defaultWaitTimeout ?? 0,
      timeout: form.timeout ?? null,
      enableStandardTools: form.enableStandardTools,
      enableGenerateShow: form.enableGenerateShow,
      isEnabled: form.isEnabled,
    }
    if (isEditing.value && editingId.value) {
      await imageGenStore.updateConfig(editingId.value, payload)
    } else {
      await imageGenStore.createConfig(payload)
    }
    ElMessage.success(t('common.status.saved'))
    sheetVisible.value = false
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('common.status.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: ImageGenConfig) {
  try {
    await ElMessageBox.confirm(t('settings.imageGen.deleteConfirm'), t('common.action.delete'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await imageGenStore.removeConfig(row.id)
    ElMessage.success(t('common.status.deleted'))
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('common.status.deleteFailed'))
  }
}

async function handleCheck(row: ImageGenConfig) {
  checkingIds.value = new Set(checkingIds.value).add(row.id)
  try {
    const result = await imageGenStore.checkConfig(row.id)
    const referenceNote = result.supports_reference_images
      ? t('settings.imageGen.checkReferenceOn')
      : t('settings.imageGen.checkReferenceOff')
    const executorNote = result.executor
      ? ` · ${t('settings.imageGen.checkExecutor', { executor: result.executor })}`
      : ''
    if (result.status === 'healthy') {
      ElMessage.success(`${result.message || t('settings.imageGen.checkPassed')} · ${referenceNote}${executorNote}`)
    } else if (result.missing_tools && result.missing_tools.length > 0) {
      ElMessage.error(t('settings.imageGen.checkMissing', { tools: result.missing_tools.join(', ') }))
    } else {
      ElMessage.error(result.error || t('settings.imageGen.checkFailed'))
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('settings.imageGen.checkFailed'))
  } finally {
    const next = new Set(checkingIds.value)
    next.delete(row.id)
    checkingIds.value = next
  }
}

onMounted(async () => {
  await imageGenStore.fetchConfigs()
  if (mcpStore.availableServices.length === 0) await mcpStore.fetchAvailableServices()
  if (providerStore.providers.length === 0) await providerStore.fetchProviders()
})
</script>

<style scoped>
.mobile-image-gen { height: 100%; display: flex; flex-direction: column; background: var(--color-background); }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px; }
.title-block { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.page-title { font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.page-subtitle { font-size: 12px; color: var(--el-text-color-secondary); }
.standard-hint { margin: 0 12px 8px; padding: 8px 10px; border-radius: 8px; background: var(--el-color-info-light-9); font-size: 11px; color: var(--el-text-color-secondary); word-break: break-all; }
.list-scroll { flex: 1; min-height: 0; }
.config-list { display: flex; flex-direction: column; gap: 10px; padding: 0 12px 16px; }
.config-card { padding: 10px 12px; border-radius: 10px; background: var(--el-fill-color-blank); border: 1px solid var(--el-border-color-lighter); display: flex; flex-direction: column; gap: 6px; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.name-block { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.config-name { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.config-desc { font-size: 12px; color: var(--el-text-color-secondary); }
.meta-row { font-size: 12px; color: var(--el-text-color-secondary); }
.tag-row { display: flex; flex-wrap: wrap; gap: 4px; }
.card-actions { display: flex; justify-content: flex-end; gap: 8px; }

.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0, 0, 0, 0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 560px; max-height: 90vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0, 0, 0, 0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); }
.sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 16px 8px; }
.field-item { margin-bottom: 12px; }
.field-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.field-hint { display: block; margin-top: 4px; margin-bottom: 6px; font-size: 12px; line-height: 1.4; color: var(--el-text-color-secondary); }
.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; }
.native-textarea { width: 100%; padding: 10px 12px; font-size: 14px; font-family: inherit; line-height: 1.5; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; resize: vertical; box-sizing: border-box; }
.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid var(--el-border-color-lighter); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.footer-btn.primary { background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); color: #fff; }
.footer-btn:disabled { opacity: 0.5; }
.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
</style>
