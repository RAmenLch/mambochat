<template>
  <div class="image-gen-manager">
    <div class="header">
      <div class="title-section">
        <h2>{{ t('settings.imageGen.title') }}</h2>
        <span class="subtitle">{{ t('settings.imageGen.subtitle') }}</span>
      </div>
      <el-button type="primary" :icon="Plus" @click="handleCreate">
        {{ t('settings.imageGen.add') }}
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="standard-hint"
      :title="t('settings.imageGen.standardHint')"
    >
      <template #default>
        <code>image_generate</code> / <code>image_task_status</code> / <code>image_download</code>
      </template>
    </el-alert>

    <el-table :data="imageGenStore.configs" style="width: 100%" v-loading="imageGenStore.isLoading">
      <el-table-column :label="t('settings.imageGen.columns.name')" min-width="160">
        <template #default="{ row }">
          <div class="name-text">{{ row.name }}</div>
          <div class="description-text" v-if="row.description">{{ row.description }}</div>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.imageGen.columns.backend')" min-width="180">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" :type="row.backendType === 'mcp' ? 'info' : 'success'">
            {{ backendTypeLabel(row.backendType) }}
          </el-tag>
          <span class="backend-name">{{ backendLabel(row) }}</span>
          <el-tag
            v-if="referenceEnabled(row)"
            size="small"
            effect="plain"
            type="warning"
            class="ml-4"
          >
            {{ t('settings.imageGen.reference.supported') }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.imageGen.columns.defaults')" width="220">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ t('settings.imageGen.count', { n: row.defaultCount }) }}</el-tag>
          <el-tag size="small" effect="plain" type="success" class="ml-4">
            {{ row.defaultResolution }}
          </el-tag>
          <el-tag size="small" effect="plain" type="info" class="ml-4">
            {{ row.defaultSync ? 'sync' : 'async' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.imageGen.columns.tools')" width="200">
        <template #default="{ row }">
          <el-tag v-if="row.enableStandardTools" size="small" effect="plain">
            {{ t('settings.imageGen.tools.standard') }}
          </el-tag>
          <el-tag v-if="row.enableGenerateShow" size="small" effect="plain" type="warning" class="ml-4">
            {{ t('settings.imageGen.tools.generateShow') }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('settings.imageGen.columns.enabled')" width="80">
        <template #default="{ row }">
          <el-tag :type="row.isEnabled ? 'success' : 'danger'" effect="dark" size="small">
            {{ row.isEnabled ? 'ON' : 'OFF' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('provider.list.action')" width="200" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :loading="checkingIds.has(row.id)"
            @click="handleCheck(row)"
          >
            {{ t('settings.imageGen.check') }}
          </el-button>
          <el-button link type="primary" @click="handleEdit(row)">
            {{ t('common.action.edit') }}
          </el-button>
          <el-popconfirm
            :title="t('settings.imageGen.deleteConfirm')"
            :confirm-button-text="t('common.action.delete')"
            :cancel-button-text="t('common.action.cancel')"
            @confirm="handleDelete(row)"
          >
            <template #reference>
              <el-button link type="danger">{{ t('common.action.delete') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? t('settings.imageGen.editTitle') : t('settings.imageGen.createTitle')"
      width="560px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" v-loading="saving" class="image-gen-form">
        <el-form-item :label="t('settings.imageGen.form.name')" required>
          <el-input v-model="form.name" maxlength="100" />
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.backend')" required class="has-hint">
          <el-radio-group v-model="form.backendType" @change="onBackendTypeChange">
            <el-radio value="mcp">{{ t('settings.imageGen.backend.mcp') }}</el-radio>
            <el-radio value="model">{{ t('settings.imageGen.backend.model') }}</el-radio>
            <el-radio value="image_api">{{ t('settings.imageGen.backend.imageApi') }}</el-radio>
          </el-radio-group>
          <div class="form-hint">{{ t('settings.imageGen.form.backendHint') }}</div>
        </el-form-item>

        <el-form-item
          v-if="form.backendType === 'mcp'"
          :label="t('settings.imageGen.form.mcpServer')"
          required
        >
          <el-select v-model="form.mcpServerId" :placeholder="t('settings.imageGen.form.mcpServerPlaceholder')" style="width: 100%">
            <el-option
              v-for="server in selectableServers"
              :key="server.id"
              :label="server.name"
              :value="server.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-else :label="t('settings.imageGen.form.aiModel')" required class="has-hint">
          <el-select
            v-model="form.aiModelId"
            filterable
            :placeholder="t('settings.imageGen.form.aiModelPlaceholder')"
            style="width: 100%"
            @change="onModelChange"
          >
            <el-option-group
              v-for="group in modelOptions"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="model in group.options"
                :key="model.id"
                :label="model.name"
                :value="model.id"
              />
            </el-option-group>
          </el-select>
          <el-checkbox v-if="form.backendType === 'model'" v-model="showAllModels" class="ml-4">
            {{ t('settings.imageGen.form.showAllModels') }}
          </el-checkbox>
          <div class="form-hint">
            {{ form.backendType === 'image_api' ? imageApiHint : t('settings.imageGen.form.aiModelHint') }}
          </div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.reference')" class="has-hint">
          <el-select v-model="referenceCapabilityModel" style="width: 200px">
            <el-option :label="t('settings.imageGen.reference.auto')" value="auto" />
            <el-option :label="t('settings.imageGen.reference.supported')" value="supported" />
            <el-option :label="t('settings.imageGen.reference.unsupported')" value="unsupported" />
          </el-select>
          <div class="form-hint">
            {{
              form.backendType !== 'mcp'
                ? t('settings.imageGen.form.referenceModelHint')
                : t('settings.imageGen.form.referenceHint')
            }}
          </div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.count')">
          <el-input-number v-model="form.defaultCount" :min="1" :max="8" />
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.resolution')" class="has-hint">
          <el-select v-model="form.defaultResolution" allow-create filterable style="width: 180px">
            <el-option
              v-for="option in resolutionPresets"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-select>
          <div class="form-hint">{{ t('settings.imageGen.form.resolutionHint') }}</div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.sync')" class="has-hint">
          <el-switch v-model="form.defaultSync" />
          <div class="form-hint">{{ t('settings.imageGen.form.syncHint') }}</div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.waitTimeout')" class="has-hint">
          <el-input-number v-model="form.defaultWaitTimeout" :min="0" :max="300" style="width: 180px" />
          <div class="form-hint">{{ t('settings.imageGen.form.waitTimeoutHint') }}</div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.timeout')" class="has-hint">
          <el-input-number v-model="form.timeout" :min="1" :controls="false" style="width: 180px" />
          <div class="form-hint">{{ t('settings.imageGen.form.timeoutHint') }}</div>
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.enabled')">
          <el-switch v-model="form.isEnabled" />
        </el-form-item>

        <el-form-item :label="t('settings.imageGen.form.tools')" required class="has-hint">
          <el-checkbox v-model="form.enableStandardTools">
            {{ t('settings.imageGen.tools.standard') }}
          </el-checkbox>
          <el-checkbox v-model="form.enableGenerateShow" class="ml-4">
            {{ t('settings.imageGen.tools.generateShow') }}
          </el-checkbox>
          <div class="form-hint">{{ t('settings.imageGen.form.toolsHint') }}</div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';

import { useImageGenStore } from '@/stores/imageGenStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useProviderStore } from '@/stores/providerStore';
import type { ImageGenBackendType, ImageGenConfig } from '@/api/types';

const { t } = useI18n();
const imageGenStore = useImageGenStore();
const mcpStore = useMcpStore();
const providerStore = useProviderStore();

const dialogVisible = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const editingId = ref<string | null>(null);
const checkingIds = ref<Set<string>>(new Set());
const showAllModels = ref(false);

const resolutionPresets = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024', '768x1344', '1344x768'];

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
});

const selectableServers = computed(() => mcpStore.availableServices.filter(s => s.isEnabled));

/** 能出图的模型优先（meta_config.output_modalities 含 image） */
function isImageOutputModel(model: any): boolean {
  const modalities = model?.meta_config?.output_modalities;
  return Array.isArray(modalities) && modalities.map((m: string) => String(m).toLowerCase()).includes('image');
}

const modelOptions = computed(() => {
  const backend = form.backendType;
  return providerStore.providers
    .map(provider => ({
      label: provider.name,
      options: provider.models.filter(model => {
        if (backend === 'image_api') return model.model_type === 'image';
        if (model.model_type === 'image') return false;
        return showAllModels.value || isImageOutputModel(model);
      }),
    }))
    .filter(group => group.options.length > 0);
});

/** 生图模型的执行器（由所属服务商的 worker_type 决定） */
function executorOfModel(modelId: string): { label: string; endpoint: string } | null {
  const model = providerStore.allModels.find(m => m.id === modelId);
  if (!model) return null;
  const provider = providerStore.providers.find(p => p.id === model.providerId);
  const worker = provider?.worker_type || '';
  if (worker === 'openrouter_images') return { label: 'OpenRouter Images API', endpoint: '/images' };
  if (worker === 'openai_images') return { label: 'OpenAI Images API', endpoint: '/images/generations' };
  const host = (provider?.apiHost || '').toLowerCase();
  if (host.includes('openrouter')) return { label: 'OpenRouter Images API（自动推导）', endpoint: '/images' };
  if (!worker || worker === 'openai' || worker === 'deepseek') {
    return { label: 'OpenAI Images API（自动推导）', endpoint: '/images/generations' };
  }
  return null;
}

const imageApiHint = computed(() => {
  if (!form.aiModelId) return t('settings.imageGen.form.imageApiHintEmpty');
  const executor = executorOfModel(form.aiModelId);
  if (!executor) return t('settings.imageGen.form.imageApiHintNoExecutor');
  return t('settings.imageGen.form.imageApiHint', {
    executor: executor.label,
    endpoint: executor.endpoint,
  });
});

function serverName(id: string | null): string {
  if (!id) return '-';
  return mcpStore.availableServices.find(s => s.id === id)?.name || id.slice(0, 8);
}

function modelName(id: string | null): string {
  if (!id) return '-';
  return providerStore.allModels.find(m => m.id === id)?.name || id.slice(0, 8);
}

function backendTypeLabel(backend: string): string {
  if (backend === 'model') return t('settings.imageGen.backend.model');
  if (backend === 'image_api') return t('settings.imageGen.backend.imageApi');
  return t('settings.imageGen.backend.mcp');
}

function backendLabel(row: ImageGenConfig): string {
  if (row.backendType === 'mcp') return serverName(row.mcpServerId);
  const name = modelName(row.aiModelId);
  if (row.backendType !== 'image_api') return name;
  const executor = executorOfModel(row.aiModelId || '');
  return executor ? `${name} · ${executor.label}` : name;
}

/** 列表标签用：显式 true，或模型后端的「自动」（= 按支持处理） */
function referenceEnabled(row: ImageGenConfig): boolean {
  if (row.supportsReferenceImages === true) return true;
  return row.supportsReferenceImages === null && row.backendType !== 'mcp';
}

/**
 * 按模型能力推断参考图能力：模型声明了 input_modalities 时据此判断能否吃图，
 * 未声明则返回 null（= 自动，后端对模型后端默认按支持处理）。
 */
function modelCapability(modelId: string): boolean | null {
  const modalities = providerStore.allModels.find(m => m.id === modelId)?.meta_config?.input_modalities;
  if (!Array.isArray(modalities) || modalities.length === 0) return null;
  return modalities.map(m => String(m).toLowerCase()).includes('image');
}

/** 用户换模型时按能力初始化，之后仍可手动改 */
function onModelChange(modelId: string) {
  if (!modelId) return;
  // 生图模型的参考图能力由执行器决定（默认按支持，仍可手动钉住）
  form.supportsReferenceImages = form.backendType === 'image_api' ? null : modelCapability(modelId);
}

/** 切换后端类型时重置为对应默认：MCP 走探测，模型按已选模型能力 */
function onBackendTypeChange(value: string | number | boolean | undefined) {
  form.aiModelId = '';
  form.supportsReferenceImages = null;
  if (value === 'model') {
    showAllModels.value = false;
  }
}

/** 参考图能力三态（null=自动）：el-select 取值不接受 null，用字符串哨兵中转 */
const referenceCapabilityModel = computed<'auto' | 'supported' | 'unsupported'>({
  get: () => {
    if (form.supportsReferenceImages == null) return 'auto';
    return form.supportsReferenceImages ? 'supported' : 'unsupported';
  },
  set: (value) => {
    form.supportsReferenceImages = value === 'auto' ? null : value === 'supported';
  },
});

function resetForm() {
  form.name = '';
  form.description = '';
  form.backendType = 'mcp';
  form.mcpServerId = '';
  form.aiModelId = '';
  form.supportsReferenceImages = null;
  form.defaultCount = 1;
  form.defaultResolution = '1024x1024';
  form.defaultSync = true;
  form.defaultWaitTimeout = 0;
  form.timeout = undefined;
  form.enableStandardTools = true;
  form.enableGenerateShow = true;
  form.isEnabled = true;
  showAllModels.value = false;
}

function handleCreate() {
  isEditing.value = false;
  editingId.value = null;
  resetForm();
  dialogVisible.value = true;
}

function handleEdit(row: ImageGenConfig) {
  isEditing.value = true;
  editingId.value = row.id;
  form.name = row.name;
  form.description = row.description || '';
  form.backendType = row.backendType === 'model'
    ? 'model'
    : (row.backendType === 'image_api' ? 'image_api' : 'mcp');
  form.mcpServerId = row.mcpServerId || '';
  form.aiModelId = row.aiModelId || '';
  form.supportsReferenceImages = row.supportsReferenceImages ?? null;
  form.defaultCount = row.defaultCount;
  form.defaultResolution = row.defaultResolution || '1024x1024';
  form.defaultSync = row.defaultSync;
  form.defaultWaitTimeout = row.defaultWaitTimeout ?? 0;
  form.timeout = row.timeout ?? undefined;
  form.enableStandardTools = row.enableStandardTools !== false;
  form.enableGenerateShow = row.enableGenerateShow === true;
  form.isEnabled = row.isEnabled;
  dialogVisible.value = true;
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning(t('settings.imageGen.form.requiredHint'));
    return;
  }
  if (form.backendType === 'mcp' && !form.mcpServerId) {
    ElMessage.warning(t('settings.imageGen.form.mcpServerRequired'));
    return;
  }
  if (form.backendType !== 'mcp' && !form.aiModelId) {
    ElMessage.warning(t('settings.imageGen.form.aiModelRequired'));
    return;
  }
  if (!form.enableStandardTools && !form.enableGenerateShow) {
    ElMessage.warning(t('settings.imageGen.form.toolsRequired'));
    return;
  }
  saving.value = true;
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
    };
    if (isEditing.value && editingId.value) {
      await imageGenStore.updateConfig(editingId.value, payload);
    } else {
      await imageGenStore.createConfig(payload);
    }
    ElMessage.success(t('common.status.saved'));
    dialogVisible.value = false;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('common.status.saveFailed'));
  } finally {
    saving.value = false;
  }
}

async function handleDelete(row: ImageGenConfig) {
  try {
    await imageGenStore.removeConfig(row.id);
    ElMessage.success(t('common.status.deleted'));
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('common.status.deleteFailed'));
  }
}

async function handleCheck(row: ImageGenConfig) {
  checkingIds.value = new Set(checkingIds.value).add(row.id);
  try {
    const result = await imageGenStore.checkConfig(row.id);
    const referenceNote = result.supports_reference_images
      ? t('settings.imageGen.checkReferenceOn')
      : t('settings.imageGen.checkReferenceOff');
    const executorNote = result.executor
      ? ` · ${t('settings.imageGen.checkExecutor', { executor: result.executor })}`
      : '';
    if (result.status === 'healthy') {
      ElMessage.success(`${result.message || t('settings.imageGen.checkPassed')} · ${referenceNote}${executorNote}`);
    } else if (result.missing_tools.length) {
      ElMessage.warning(t('settings.imageGen.checkMissing', { tools: result.missing_tools.join(', ') }));
    } else {
      ElMessage.error(result.error || result.message);
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('settings.imageGen.checkFailed'));
  } finally {
    const next = new Set(checkingIds.value);
    next.delete(row.id);
    checkingIds.value = next;
  }
}

onMounted(async () => {
  await Promise.all([
    imageGenStore.fetchConfigs(),
    mcpStore.fetchAvailableServices(),
    providerStore.providers.length ? Promise.resolve() : providerStore.fetchProviders(),
  ]);
});
</script>

<style scoped>
.image-gen-manager {
  padding: 8px;
}

/* 弹窗留白：标题与正文拉开、正文与 footer 收紧 */
.image-gen-manager :deep(.el-dialog__header) {
  padding-bottom: 12px;
  margin-right: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.image-gen-manager :deep(.el-dialog__body) {
  padding-top: 18px;
  padding-bottom: 6px;
}

.image-gen-manager :deep(.el-dialog__footer) {
  padding-top: 10px;
}

.image-gen-form :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.title-section h2 {
  margin: 0;
  font-size: 18px;
}

.subtitle {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.standard-hint {
  margin-bottom: 12px;
}

.standard-hint code {
  background: var(--el-fill-color-light);
  padding: 1px 4px;
  border-radius: 3px;
}

.name-text {
  font-weight: 500;
}

.backend-name {
  margin-left: 6px;
}

.description-text {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.form-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

/* 带说明的字段：控件在上、说明独占一行，避免与控件挤在同一行 */
.image-gen-form :deep(.el-form-item.has-hint .el-form-item__content) {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.image-gen-form :deep(.el-form-item.has-hint .form-hint) {
  margin: 0;
  white-space: normal;
}

.ml-4 {
  margin-left: 4px;
}
</style>
