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
          <el-input v-model.trim="providerForm.name" placeholder="例如：OpenAI" />
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
import { Plus, Delete, Download } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import type {
  AIProviderWithModels,
  ProviderWithModelsCreate,
  AIProviderUpdate,
  AIModelBase,
  AIModel,
  AIModelCreate
} from '@/api/types';
import { AxiosError } from "axios";

// 为表单的内部数据结构定义清晰的类型
interface ModelFormData extends Omit<AIModelBase, 'id'> { // Omit 'id' for new models in form
  id?: string; // id is optional, only present for existing models
}
interface ProviderFormData {
  name: string;
  apiHost: string;
  apiKey: string;
  models: ModelFormData[];
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
const providerFormRef = ref<FormInstance>();
const internalVisible = ref(false);
const isTestingConnection = ref(false);
const isFetchingModels = ref(false);
// initialModels 用于跟踪编辑状态下模型列表的变化，以便进行增删改操作
let initialModels: AIModel[] = [];

const providerForm = reactive<ProviderFormData>({
  name: '',
  apiHost: '',
  apiKey: '',
  models: [],
});

const isEditing = computed(() => !!props.providerData);

const providerFormRules = reactive<FormRules<ProviderFormData>>({
  name: [{ required: true, message: '请输入服务商名称', trigger: 'blur' }],
  apiHost: [{ required: true, message: '请输入 API Host', trigger: 'blur' }],
  apiKey: [{
    validator: (rule, value: string, callback: (error?: Error) => void) => {
      // 在新增模式下，apiKey 必须填写。在编辑模式下，如果 apiKey 是占位符，说明用户没有修改，允许通过。
      // 如果不是占位符，且为空，则提示填写。
      if (!isEditing.value && !value) {
        callback(new Error('请输入 API Key'));
      } else if (isEditing.value && value === API_KEY_PLACEHOLDER) {
        callback(); // 编辑模式下，占位符是合法的，表示未修改
      } else if (value === '') {
        callback(new Error('请输入 API Key')); // 编辑模式下，如果用户清空了字段，则需要填写
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

// 当 modelId 变化时，如果 name 未设置或与旧 modelId 相同，则更新 name 为新 modelId
watch(() => providerForm.models, (newModels, oldModels) => {
  if (!oldModels || newModels.length !== oldModels.length) return; // Only process when array length same (i.e. modelId might have changed)
  for (let i = 0; i < newModels.length; i++) {
    const newModel = newModels[i];
    const oldModel = oldModels[i];
    // console.log("newModel.modelId", newModel.modelId, "oldModel.modelId", oldModel.modelId)
    // console.log("newModel.name", newModel.name, "oldModel.name", oldModel.name)
    if (newModel && oldModel && newModel.modelId !== oldModel.modelId) {
      if (!oldModel.name || oldModel.name === oldModel.modelId || oldModel.name === '') {
        newModel.name = newModel.modelId;
      }
    }
  }
}, { deep: true });

/**
 * 重置并根据传入的 providerData 初始化表单数据。
 */
function resetAndInitializeForm() {
  providerFormRef.value?.resetFields();
  if (props.providerData) { // 编辑模式
    // Deep copy models to ensure reactivity and independence from store data
    Object.assign(providerForm, {
      name: props.providerData.name,
      apiHost: props.providerData.apiHost,
      apiKey: API_KEY_PLACEHOLDER, // API Key always displayed as placeholder in edit mode initially
      models: JSON.parse(JSON.stringify(props.providerData.models)),
    });
    initialModels = JSON.parse(JSON.stringify(props.providerData.models)); // Store initial models for diff
  } else { // 新增模式
    Object.assign(providerForm, { name: '', apiHost: '', apiKey: '', models: [] });
    initialModels = [];
  }
}

/**
 * 处理连接测试按钮点击事件。
 * 根据编辑状态和 apiKey 是否为占位符来调用不同的 API。
 */
async function handleTestConnection() {
  if (!providerForm.apiHost) {
    ElMessage.warning('请填写 API Host 以进行测试');
    return;
  }
  // 如果是新增模式，或者编辑模式下用户输入了新的 key，则 apiKey 必须存在
  if (!isEditing.value || providerForm.apiKey !== API_KEY_PLACEHOLDER) {
    if (!providerForm.apiKey) {
      ElMessage.warning('请填写 API Key 以进行测试');
      return;
    }
  }

  isTestingConnection.value = true;
  try {
    let res;
    // 如果是编辑模式，并且 apiKey 是占位符，则调用新的接口，后端从数据库获取 key
    if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      res = await providerStore.testConnectionForProvider(props.providerData.id, providerForm.apiHost);
    } else {
      // 否则 (新增模式或编辑模式下用户输入了新的 key)，使用包含 apiKey 的旧接口
      res = await providerStore.testConnection({ apiHost: providerForm.apiHost, apiKey: providerForm.apiKey });
    }
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: res.message });
  } catch (error) {
    if(error instanceof AxiosError){ // Type guard for AxiosError
      ElMessage.error(error?.response?.data?.detail || '连接测试失败'); // Access data safely
    } else {
      ElMessage.error("未知错误");
    }
  } finally {
    isTestingConnection.value = false;
  }
}

/**
 * 处理从API获取模型按钮点击事件。
 */
async function handleFetchModels() {
  isFetchingModels.value = true;
  try {
    let models: AIModelBase[];
    // 如果是编辑模式，并且 apiKey 是占位符，则调用为现有服务商获取模型的接口
    if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      models = await providerStore.fetchModelsForProvider(props.providerData.id);
    } else {
      if (!providerForm.apiHost || !providerForm.apiKey) {
        ElMessage.warning('请填写 API Host 和 API Key 以获取模型列表');
        return;
      }
      // 否则，调用通用获取外部模型列表的接口
      models = await providerStore.fetchExternalModels({ apiHost: providerForm.apiHost, apiKey: providerForm.apiKey });
    }
    emit('fetch-models', models);
  } catch (error) {
    if(error instanceof AxiosError){ // Type guard for AxiosError
      ElMessage.error(error?.response?.data?.detail || '获取模型列表失败'); // Access data safely
    } else {
      ElMessage.error("未知错误");
    }
  } finally {
    isFetchingModels.value = false;
  }
}

/**
 * 处理 API Key 输入框获得焦点事件。
 * 如果是占位符，则清空以便用户输入。
 */
function handleApiKeyFocus() {
  if (isEditing.value && providerForm.apiKey === API_KEY_PLACEHOLDER) {
    providerForm.apiKey = '';
  }
}

/**
 * 处理 API Key 输入框失去焦点事件。
 * 如果编辑模式下输入框为空，则恢复占位符。
 */
function handleApiKeyBlur() {
  if (isEditing.value && providerForm.apiKey === '') {
    providerForm.apiKey = API_KEY_PLACEHOLDER;
  }
}

/**
 * 向模型列表手动添加一个空条目。
 */
function addModelEntryToForm() {
  providerForm.models.push({ name: '', modelId: '' });
}

/**
 * 从模型列表中移除指定索引的条目。
 * @param index 要移除的模型索引。
 */
function removeModelEntryFromForm(index: number) {
  providerForm.models.splice(index, 1);
}

/**
 * 处理对话框关闭事件。
 */
function handleClose() {
  emit('update:visible', false);
}

/**
 * 提交表单。根据编辑模式调用创建或更新服务商的逻辑。
 */
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
      } catch (error) {
        if(error instanceof AxiosError){ // Type guard for AxiosError
          ElMessage.error(error?.response?.data?.detail || '操作失败'); // Access data safely
        } else {
          ElMessage.error("未知错误");
        }
      }
    }
  });
}

/**
 * 处理创建新服务商的逻辑。
 */
async function handleCreateProvider() {
  const createData: ProviderWithModelsCreate = {
    name: providerForm.name,
    apiHost: providerForm.apiHost,
    apiKey: providerForm.apiKey,
    models: providerForm.models.map(({ name, modelId }) => ({ name, modelId })), // Ensure correct type for models
  };
  await providerStore.addProviderWithModels(createData);
  ElMessage.success('新增服务商成功！');
}

/**
 * 处理更新现有服务商的逻辑。
 * 包括服务商基本信息更新和模型列表的增删改。
 */
async function handleUpdateProvider() {
  if (!props.providerData?.id) { // Ensure providerId exists for update
    ElMessage.error('服务商ID缺失，无法更新。');
    return;
  }

  const providerUpdateData: AIProviderUpdate = {
    name: providerForm.name,
    apiHost: providerForm.apiHost
  };
  // 只有当 API Key 被修改时才提交
  if (providerForm.apiKey !== API_KEY_PLACEHOLDER) {
    providerUpdateData.apiKey = providerForm.apiKey;
  }

  // --- 模型列表的增删改逻辑 ---
  const currentProviderId = props.providerData.id;
  const currentModelIdsInForm = new Set(providerForm.models.filter(m => m.id).map(m => m.id!));

  // 新增的模型 (没有 id 字段)
  const modelsToAdd = providerForm.models
    .filter(m => !m.id)
    .map(m => ({
      name: m.name,
      modelId: m.modelId,
      providerId: currentProviderId
    }) as AIModelCreate); // Cast to AIModelCreate

  // 删除的模型 (在 initialModels 中存在，但不在当前表单的已存在模型中)
  const modelsToDelete = initialModels.filter(m => !currentModelIdsInForm.has(m.id));

  // 更新的模型 (id 存在，且 name 或 modelId 发生变化)
  const modelsToUpdatePromises = providerForm.models
    .filter((currentModel: ModelFormData): currentModel is AIModel => !!currentModel.id) // Filter for existing models
    .map(currentModel => {
      const initialModel = initialModels.find(m => m.id === currentModel.id);
      if (initialModel && (initialModel.name !== currentModel.name || initialModel.modelId !== currentModel.modelId)) {
        // Only update 'name' as per AIModelUpdate schema, modelId is generally immutable for existing models
        return providerStore.updateModel(currentModel.id, { name: currentModel.name });
      }
      return null;
    })
    .filter(Boolean); // Remove null entries

  // 执行所有异步操作
  const updatePromises = [
    providerStore.updateProvider(currentProviderId, providerUpdateData),
    ...modelsToAdd.map(m => providerStore.addModel(m)),
    ...modelsToDelete.map(m => providerStore.removeModel(m.id)),
    ...modelsToUpdatePromises,
  ];

  await Promise.all(updatePromises);
  ElMessage.success('更新服务商及模型成功！');
}

// 供父组件调用的方法，用于批量添加从API获取的模型
defineExpose({
  addFetchedModels(selectedIds: string[], fetchedModels: AIModelBase[]) {
    selectedIds.forEach(modelId => {
      const modelExists = providerForm.models.some(m => m.modelId === modelId);
      if (!modelExists) {
        const fullModel = fetchedModels.find(m => m.modelId === modelId);
        if (fullModel) { // Ensure fullModel is found before adding
          providerForm.models.push({
            name: fullModel.name,
            modelId: fullModel.modelId,
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
</style>

