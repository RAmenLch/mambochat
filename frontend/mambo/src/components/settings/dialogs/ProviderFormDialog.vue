<template>
  <el-dialog
    v-model="internalVisible"
    :title="isEditing ? '编辑 AI 服务商' : '新增 AI 服务商'"
    width="700px"
    :close-on-click-modal="false"
    class="provider-dialog"
    @close="handleClose"
  >
    <div class="dialog-body-wrapper">
      <el-form ref="providerFormRef" :model="providerForm" :rules="providerFormRules" label-width="100px" class="form-section">
        <el-form-item label="服务商名称" prop="name">
          <el-autocomplete
            v-model="providerForm.name"
            :fetch-suggestions="querySearchProviders"
            placeholder="选择或输入服务商名称"
            style="width: 100%"
            @select="(item:Record<string,any>) => handleProviderSelect(item as AutocompleteSuggestion)"
            :trigger-on-focus="true"
          />
        </el-form-item>
        <el-form-item label="API Host" prop="apiHost">
          <el-input v-model.trim="providerForm.apiHost" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" prop="apiKey">
          <el-input
            v-model="providerForm.apiKey"
            type="password"
            show-password
            placeholder="请输入您的 API Key"
            @focus="handleApiKeyFocus"
            @blur="handleApiKeyBlur"
          >
            <template #append>
              <el-button @click="handleTestConnection" :loading="isTestingConnection">测试连接</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用代理">
           <el-switch
             v-model="providerForm.use_proxy"
             :disabled="!isProxyGloballyEnabled"
           />
           <el-tooltip
              v-if="!isProxyGloballyEnabled"
              effect="dark"
              content="请先在“全局配置”中启用代理功能"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
        </el-form-item>
      </el-form>
      <div class="scrollable-content">
        <el-divider>模型列表</el-divider>
        <div v-if="providerForm.models.length > 0" class="model-form-header">
          <span class="header-item">模型ID</span>
          <span class="header-item">模型显示名称</span>
        </div>
        <div v-for="(model, index) in providerForm.models" :key="index" class="model-form-item">
          <el-input v-model.trim="model.modelId" placeholder="模型ID (e.g. gpt-4o)" style="width: 45%; margin-right: 10px;" />
          <el-input v-model.trim="model.name" placeholder="模型显示名称 (e.g. GPT-4o)" style="width: 45%;" />
          <el-button link type="danger" :icon="Delete" @click="removeModelEntryFromForm(index)" class="delete-model-btn" />
        </div>
        <el-button @click="addModelEntryToForm" style="margin-right: 10px;">
          <el-icon><Plus /></el-icon>手动添加
        </el-button>
        <el-button @click="handleFetchModels" :loading="isFetchingModels">
          <el-icon><Download /></el-icon>从API获取
        </el-button>
      </div>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="submitForm">确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
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
  AIModelCreate
} from '@/api/types';
import { isAxiosError } from "axios";

// 此处模型数据包含了可选的 meta_config
interface ModelFormData extends AIModelBase {
  id?: string;
}
interface ProviderFormData {
  name: string;
  apiHost: string;
  apiKey: string;
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
  use_proxy: false,
  models: [],
});

const isEditing = computed(() => !!props.providerData);
const isProxyGloballyEnabled = computed(() => globalSettings.value.proxy_enabled === true);

const providerFormRules = reactive<FormRules<ProviderFormData>>({
  name: [{ required: true, message: '请输入服务商名称', trigger: 'blur' }],
  apiHost: [{ required: true, message: '请输入 API Host', trigger: 'blur' }],
  apiKey: [{
    validator: (rule, value: string, callback: (error?: Error) => void) => {
      if (!isEditing.value && !value) {
        callback(new Error('请输入 API Key'));
      } else if (isEditing.value && value === API_KEY_PLACEHOLDER) {
        callback();
      } else if (value === '') {
        callback(new Error('请输入 API Key'));
      } else {
        callback();
      }
    },
    trigger: 'blur',
  }],
});

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
      use_proxy: props.providerData.use_proxy,
      models: JSON.parse(JSON.stringify(props.providerData.models)), // 深拷贝
    });
    initialModels = JSON.parse(JSON.stringify(props.providerData.models)); // 深拷贝
  } else { // 新增模式
    Object.assign(providerForm, { name: '', apiHost: '', apiKey: '', use_proxy: false, models: [] });
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
  }
}

async function handleTestConnection() {
  if (!providerForm.apiHost) {
    ElMessage.warning('请填写 API Host 以进行测试');
    return;
  }
  if (!isEditing.value || providerForm.apiKey !== API_KEY_PLACEHOLDER) {
    if (!providerForm.apiKey) {
      ElMessage.warning('请填写 API Key 以进行测试');
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
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: res.message });
  } catch (error: unknown) {
    if(isAxiosError(error)){
      ElMessage.error(error?.response?.data?.detail || '连接测试失败');
    } else {
      ElMessage.error("未知错误");
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
        ElMessage.warning('请填写 API Host 和 API Key 以获取模型列表');
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
  providerForm.models.push({ name: '', modelId: '', meta_config: null });
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
    use_proxy: providerForm.use_proxy,
    models: providerForm.models.map(({ name, modelId, meta_config }) => ({ name, modelId, meta_config })),
  };
  await providerStore.addProviderWithModels(createData);
  ElMessage.success('新增服务商成功！');
}

async function handleUpdateProvider() {
  if (!props.providerData?.id) {
    ElMessage.error('服务商ID缺失，无法更新。');
    return;
  }

  const providerUpdateData: AIProviderUpdate = {
    name: providerForm.name,
    apiHost: providerForm.apiHost,
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
      providerId: currentProviderId,
      meta_config: m.meta_config
    }) as AIModelCreate);

  const modelsToDelete = initialModels.filter(m => !currentModelIdsInForm.has(m.id));

  const modelsToUpdatePromises = providerForm.models
    .filter((currentModel: ModelFormData): currentModel is AIModel => !!currentModel.id)
    .map(currentModel => {
      const initialModel = initialModels.find(m => m.id === currentModel.id);
      if (initialModel && (initialModel.name !== currentModel.name || initialModel.modelId !== currentModel.modelId)) {
        return providerStore.updateModel(currentModel.id, { name: currentModel.name });
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
  ElMessage.success('更新服务商及模型成功！');
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
.header-item { width: 45%; }
.header-item:first-of-type { margin-right: 10px; }
.model-form-item { display: flex; align-items: center; margin-bottom: 10px; }
.delete-model-btn { margin-left: 10px; }
.label-icon { margin-left: 4px; color: var(--el-text-color-secondary); cursor: help; }
.el-form-item .el-switch { margin-right: 8px; }
</style>
