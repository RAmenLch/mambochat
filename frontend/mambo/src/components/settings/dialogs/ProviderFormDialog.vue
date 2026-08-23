<template>
  <el-dialog
    v-model="internalVisible"
    :title="isEditing ? t('provider.form.editTitle') : t('provider.form.addTitle')"
    width="750px"
    :close-on-click-modal="false"
    class="provider-dialog"
    @close="handleClose"
  >
    <div class="dialog-body-wrapper">
      <el-form ref="providerFormRef" :model="providerForm" :rules="providerFormRules" label-width="120px" class="form-section">
        <el-form-item :label="t('provider.form.name')" prop="name">
          <el-autocomplete
            v-model="providerForm.name"
            :fetch-suggestions="querySearchProviders"
            :placeholder="t('provider.form.namePlaceholder')"
            style="width: 100%"
            @select="(item: Record<string, any>) => handleProviderSelect(item as AutocompleteSuggestion)"
            :trigger-on-focus="true"
          />
        </el-form-item>

        <el-form-item :label="t('provider.form.workerType')" prop="worker_type">
          <el-select v-model="providerForm.worker_type" :placeholder="t('provider.form.workerTypePlaceholder')" style="width: 100%">
            <el-option label="OpenAI Compatible" value="openai" />
            <el-option label="Google Gemini Native" value="google" />
            <el-option label="DeepSeek Native" value="deepseek" />
             <el-option label="Anthropic Native" value="anthropic" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('provider.form.apiHost')" prop="apiHost">
          <el-input v-model.trim="providerForm.apiHost" :placeholder="t('provider.form.apiHostPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('provider.form.apiKey')" prop="apiKey">
          <el-input
            v-model="providerForm.apiKey"
            type="password"
            show-password
            :placeholder="t('provider.form.apiKeyPlaceholder')"
            @focus="handleApiKeyFocus"
            @blur="handleApiKeyBlur"
          >
            <template #append>
              <el-button @click="handleTestConnection" :loading="isTestingConnection">{{ t('provider.form.testConnection') }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('provider.form.enableProxy')">
           <el-switch
             v-model="providerForm.use_proxy"
             :disabled="!isProxyGloballyEnabled"
           />
           <el-tooltip
              v-if="!isProxyGloballyEnabled"
              effect="dark"
              :content="t('provider.form.proxyTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
        </el-form-item>
      </el-form>
      <div class="scrollable-content">
        <el-divider>{{ t('provider.form.modelList') }}</el-divider>
        <div v-if="providerForm.models.length > 0" class="model-form-header">
          <span class="header-item id-col">{{ t('model.table.id') }}</span>
          <span class="header-item name-col">{{ t('model.table.name') }}</span>
          <span class="header-item type-col">{{ t('model.table.type') }}</span>
        </div>
        <div v-for="(model, index) in providerForm.models" :key="index" class="model-form-item">
          <el-input v-model.trim="model.modelId" :placeholder="t('model.form.idPlaceholder')" class="id-input" />
          <el-input v-model.trim="model.name" :placeholder="t('model.form.namePlaceholder')" class="name-input" />
          <el-select v-model="model.model_type" placeholder="Type" class="type-select">
            <el-option :label="t('model.table.typeChat')" value="chat" />
            <el-option :label="t('model.table.typeEmbedding')" value="embedding" />
          </el-select>
          <el-button link type="danger" :icon="Delete" @click="removeModelEntryFromForm(index)" class="delete-model-btn" />
        </div>
        <el-button @click="addModelEntryToForm" style="margin-right: 10px;">
          <el-icon><Plus /></el-icon>{{ t('provider.form.manualAdd') }}
        </el-button>
        <el-button @click="handleFetchModels" :loading="isFetchingModels">
          <el-icon><Download /></el-icon>{{ t('provider.form.fetchModels') }}
        </el-button>
      </div>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm">{{ t('common.action.confirm') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Delete, Download, QuestionFilled } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { storeToRefs } from 'pinia';
import type {
  AIProviderWithModels,
  ProviderWithModelsCreate,
  AIProviderUpdate,
  AIModelBase,
  AIModel,
  AIModelCreate,
  ProviderWorkerType
} from '@/api/types';
import { isAxiosError } from "axios";
import { localizeProviderTestMessage } from '@/utils/providerTestMessage';

// 此处模型数据包含了可选的 meta_config
interface ModelFormData extends AIModelBase {
  id?: string;
}
interface ProviderFormData {
  name: string;
  apiHost: string;
  apiKey: string;
  worker_type: ProviderWorkerType;
  use_proxy: boolean;
  models: ModelFormData[];
}
// Autocomplete 组件建议项的类型
interface AutocompleteSuggestion {
  value: string;
}

const props = defineProps<{
  visible: boolean;
  providerData: AIProviderWithModels | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'submitted'): void;
  (e: 'fetch-models', models: AIModelBase[]): void;
}>();

const API_KEY_PLACEHOLDER = '********';

const { t } = useI18n();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const systemConfigStore = useSystemConfigStore();
const { globalSettings } = storeToRefs(settingsStore);

const providerFormRef = ref<FormInstance>();
const internalVisible = ref(false);
const isTestingConnection = ref(false);
const isFetchingModels = ref(false);
let initialModels: AIModel[] = [];

const providerForm = reactive<ProviderFormData>({
  name: '',
  apiHost: '',
  apiKey: '',
  worker_type: 'openai',
  use_proxy: false,
  models: [],
});

const isEditing = computed(() => !!props.providerData);
const isProxyGloballyEnabled = computed(() => globalSettings.value.proxy_enabled === true);

const providerFormRules = computed<FormRules<ProviderFormData>>(() => ({
  name: [{ required: true, message: t('provider.form.namePlaceholder'), trigger: 'blur' }],
  worker_type: [{ required: true, message: t('provider.form.workerTypePlaceholder'), trigger: 'change' }],
  apiHost: [{ required: true, message: t('provider.form.apiHostPlaceholder'), trigger: 'blur' }],
  apiKey: [{
    validator: (rule, value: string, callback: (error?: Error) => void) => {
      if (!isEditing.value && !value) {
        callback(new Error(t('provider.form.apiKeyPlaceholder')));
      } else if (isEditing.value && value === API_KEY_PLACEHOLDER) {
        callback();
      } else if (value === '') {
        callback(new Error(t('provider.form.apiKeyPlaceholder')));
      } else {
        callback();
      }
    },
    trigger: 'blur',
  }],
}));

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    resetAndInitializeForm();
  }
});

watch(() => providerForm.models, (newModels, oldModels) => {
  if (!oldModels || newModels.length !== oldModels.length) return;
  for (let i = 0; i < newModels.length; i++) {
    const newModel = newModels[i];
    const oldModel = oldModels[i];
    if (newModel && oldModel && newModel.modelId !== oldModel.modelId) {
      if (!oldModel.name || oldModel.name === oldModel.modelId || oldModel.name === '') {
        newModel.name = newModel.modelId;
      }
    }
  }
}, { deep: true });

function resetAndInitializeForm() {
  providerFormRef.value?.resetFields();
  if (props.providerData) { // 编辑模式
    Object.assign(providerForm, {
      name: props.providerData.name,
      apiHost: props.providerData.apiHost,
      apiKey: API_KEY_PLACEHOLDER,
      worker_type: props.providerData.worker_type,
      use_proxy: props.providerData.use_proxy,
      models: JSON.parse(JSON.stringify(props.providerData.models)), // 深拷贝
    });
    initialModels = JSON.parse(JSON.stringify(props.providerData.models)); // 深拷贝
  } else { // 新增模式
    Object.assign(providerForm, {
      name: '',
      apiHost: '',
      apiKey: '',
      worker_type: 'openai',
      use_proxy: false,
      models: []
    });
    initialModels = [];
  }
}

const querySearchProviders = (queryString: string, cb: (results: AutocompleteSuggestion[]) => void) => {
  const allProviders = systemConfigStore.defaultProviders;
  const results = queryString
    ? allProviders.filter(p =>
        p.name.toLowerCase().includes(queryString.toLowerCase())
      )
    : allProviders;
  cb(results.map(p => ({ value: p.name })));
};

function handleProviderSelect(item: AutocompleteSuggestion) {
  const selectedProvider = systemConfigStore.defaultProviders.find(p => p.name === item.value);
  if (selectedProvider) {
    providerForm.apiHost = selectedProvider.apiHost;
    providerForm.worker_type = selectedProvider.worker_type;
  }
}

async function handleTestConnection() {
  if (!providerForm.apiHost) {
    ElMessage.warning(t('provider.form.testWarningHost'));
    return;
  }
  if (!isEditing.value || providerForm.apiKey !== API_KEY_PLACEHOLDER) {
    if (!providerForm.apiKey) {
      ElMessage.warning(t('provider.form.testWarningKey'));
      return;
    }
  }

  isTestingConnection.value = true;
  try {
    let res;
    if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      res = await providerStore.testConnectionForProvider(props.providerData.id, providerForm.apiHost, providerForm.use_proxy);
    } else {
      res = await providerStore.testConnection({ apiHost: providerForm.apiHost, apiKey: providerForm.apiKey }, providerForm.use_proxy);
    }
    const msg = res.status === 'success'
      ? t('provider.form.testSuccess')
      : (localizeProviderTestMessage(res.code) || res.message || t('provider.form.testFailed'));
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: msg });
  } catch (error: unknown) {
    if(isAxiosError(error)){
      ElMessage.error(error?.response?.data?.detail || t('provider.form.testFailed'));
    } else {
      ElMessage.error(t('common.error.unknown')); // Fallback if key missing
    }
  } finally {
    isTestingConnection.value = false;
  }
}

async function handleFetchModels() {
  isFetchingModels.value = true;
  try {
    let models: AIModelBase[];
    if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      models = await providerStore.fetchModelsForProvider(props.providerData.id, providerForm.use_proxy);
    } else {
      if (!providerForm.apiHost || !providerForm.apiKey) {
        ElMessage.warning(t('provider.form.fetchWarning'));
        isFetchingModels.value = false;
        return;
      }
      models = await providerStore.fetchExternalModels({ apiHost: providerForm.apiHost, apiKey: providerForm.apiKey }, providerForm.use_proxy);
    }
    emit('fetch-models', models);
  } catch (error: unknown) {
    if(isAxiosError(error)){
      ElMessage.error(error?.response?.data?.detail || '获取模型列表失败');
    } else {
      ElMessage.error("未知错误");
    }
  } finally {
    isFetchingModels.value = false;
  }
}

function handleApiKeyFocus() {
  if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER) {
    providerForm.apiKey = '';
  }
}

function handleApiKeyBlur() {
  if (isEditing.value && providerForm.apiKey === '') {
    providerForm.apiKey = API_KEY_PLACEHOLDER;
  }
}

function addModelEntryToForm() {
  providerForm.models.push({ name: '', modelId: '', model_type: 'chat', meta_config: null });
}

function removeModelEntryFromForm(index: number) {
  providerForm.models.splice(index, 1);
}

function handleClose() {
  emit('update:visible', false);
}

async function submitForm() {
  if (!providerFormRef.value) return;
  await providerFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        if (isEditing.value && props.providerData) {
          await handleUpdateProvider();
        } else {
          await handleCreateProvider();
        }
        emit('submitted');
        handleClose();
      } catch (error: unknown) {
        if(isAxiosError(error)){
          ElMessage.error(error?.response?.data?.detail || '操作失败');
        } else {
          ElMessage.error("未知错误");
        }
      }
    }
  });
}

async function handleCreateProvider() {
  const createData: ProviderWithModelsCreate = {
    name: providerForm.name,
    apiHost: providerForm.apiHost,
    apiKey: providerForm.apiKey,
    worker_type: providerForm.worker_type,
    use_proxy: providerForm.use_proxy,
    models: providerForm.models.map(({ name, modelId, model_type, meta_config }) => ({
      name,
      modelId,
      model_type,
      meta_config
    })),
  };
  await providerStore.addProviderWithModels(createData);
  ElMessage.success(t('provider.form.createSuccess'));
}

async function handleUpdateProvider() {
  if (!props.providerData?.id) {
    ElMessage.error('服务商ID缺失，无法更新。');
    return;
  }

  const providerUpdateData: AIProviderUpdate = {
    name: providerForm.name,
    apiHost: providerForm.apiHost,
    worker_type: providerForm.worker_type,
    use_proxy: providerForm.use_proxy,
  };
  if (providerForm.apiKey !== API_KEY_PLACEHOLDER) {
    providerUpdateData.apiKey = providerForm.apiKey;
  }

  const currentProviderId = props.providerData.id;
  const currentModelIdsInForm = new Set(providerForm.models.filter(m => m.id).map(m => m.id!));

  const modelsToAdd = providerForm.models
    .filter(m => !m.id)
    .map(m => ({
      name: m.name,
      modelId: m.modelId,
      model_type: m.model_type,
      providerId: currentProviderId,
      meta_config: m.meta_config
    }) as AIModelCreate);

  const modelsToDelete = initialModels.filter(m => !currentModelIdsInForm.has(m.id));

  const modelsToUpdatePromises = providerForm.models
    .filter((currentModel: ModelFormData): currentModel is AIModel => !!currentModel.id)
    .map(currentModel => {
      const initialModel = initialModels.find(m => m.id === currentModel.id);
      if (initialModel) {
        // 检查是否有任何字段发生变化
        const hasChanged =
          initialModel.name !== currentModel.name ||
          initialModel.modelId !== currentModel.modelId ||
          initialModel.model_type !== currentModel.model_type;

        if (hasChanged) {
          return providerStore.updateModel(currentModel.id, {
            name: currentModel.name,
            model_type: currentModel.model_type
          });
        }
      }
      return null;
    })
    .filter((promise): promise is Promise<void> => promise !== null);

  const updatePromises = [
    providerStore.updateProvider(currentProviderId, providerUpdateData),
    ...modelsToAdd.map(m => providerStore.addModel(m)),
    ...modelsToDelete.map(m => providerStore.removeModel(m.id)),
    ...modelsToUpdatePromises,
  ];

  await Promise.all(updatePromises);
  ElMessage.success(t('provider.form.updateSuccess'));
}

defineExpose({
  addFetchedModels(selectedIds: string[], fetchedModels: AIModelBase[]) {
    selectedIds.forEach(modelId => {
      const modelExists = providerForm.models.some(m => m.modelId === modelId);
      if (!modelExists) {
        const fullModel = fetchedModels.find(m => m.modelId === modelId);
        if (fullModel) {
          providerForm.models.push({
            name: fullModel.name,
            modelId: fullModel.modelId,
            model_type: fullModel.model_type || 'chat',
            meta_config: fullModel.meta_config,
          });
        }
      }
    });
  },
});
</script>

<style>
.provider-dialog .el-dialog__body {
  padding-top: 10px;
  padding-bottom: 10px;
}
</style>

<style scoped>
.dialog-body-wrapper { display: flex; flex-direction: column; max-height: 65vh; }
.form-section { flex-shrink: 0; }
.scrollable-content { flex-grow: 1; overflow-y: auto; padding: 0 10px; margin: 0 -10px; }
.model-form-header { display: flex; align-items: center; margin-bottom: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.header-item { display: inline-block; }
.id-col { width: 35%; margin-right: 10px; }
.name-col { width: 35%; margin-right: 10px; }
.type-col { width: 20%; }

.model-form-item { display: flex; align-items: center; margin-bottom: 10px; }
.id-input { width: 35%; margin-right: 10px; }
.name-input { width: 35%; margin-right: 10px; }
.type-select { width: 20%; }
.delete-model-btn { margin-left: 10px; }
.label-icon { margin-left: 4px; color: var(--el-text-color-secondary); cursor: help; }
.el-form-item .el-switch { margin-right: 8px; }
</style>
