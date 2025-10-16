<template>
  <div class="provider-model-manager">
    <!-- 1. 服务商管理区域 -->
    <div class="header">
      <h2>服务商 (Providers)</h2>
      <el-button type="primary" @click="openAddProviderDialog">
        <el-icon><Plus /></el-icon>
        新增服务商
      </el-button>
    </div>
    <el-table
      :data="providers"
      v-loading="isLoading"
      border
      style="width: 100%"
      highlight-current-row
      @row-click="handleRowClick"
      :row-key="row => row.id"
      ref="providerTableRef"
    >
      <el-table-column prop="name" label="服务商名称" width="220" />
      <el-table-column prop="apiHost" label="API Host" />
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openEditProviderDialog(row)">编辑</el-button>
          <el-button link type="danger" @click.stop="handleDeleteProvider(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />

    <!-- 2. 模型管理区域 -->
    <div class="header">
      <h2>模型 (Models)</h2>
      <el-button type="primary" @click="openAddModelDialog" :disabled="!selectedProvider">
        <el-icon><Plus /></el-icon>
        新增模型
      </el-button>
    </div>
    <div v-if="selectedProvider">
      <p class="provider-info">
        当前服务商: <strong>{{ selectedProvider.name }}</strong>
      </p>
      <el-table :data="selectedProvider.models" border style="width: 100%">
        <el-table-column prop="modelId" label="模型 ID" />
        <el-table-column prop="name" label="模型显示名称" width="220" />
        <el-table-column label="操作" width="180" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditModelDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDeleteModel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-empty v-else description="请先在上方表格中点击选择一个服务商" />

    <!-- 3. Dialogs -->
    <!-- 新增/编辑服务商 Dialog -->
    <el-dialog
      v-model="providerDialogVisible"
      :title="isEditingProvider ? '编辑 AI 服务商' : '新增 AI 服务商'"
      width="700px"
      :close-on-click-modal="false"
      class="provider-dialog"
    >
      <div class="dialog-body-wrapper">
        <el-form ref="providerFormRef" :model="providerForm" :rules="providerFormRules" label-width="100px" class="form-section">
          <el-form-item label="服务商名称" prop="name">
            <el-input v-model="providerForm.name" placeholder="例如：OpenAI" />
          </el-form-item>
          <el-form-item label="API Host" prop="apiHost">
            <el-input v-model="providerForm.apiHost" placeholder="例如：https://api.openai.com/v1" />
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
            <el-input v-model="model.modelId" placeholder="模型ID (e.g. gpt-4o)" style="width: 45%; margin-right: 10px;" />
            <el-input v-model="model.name" placeholder="模型显示名称 (e.g. GPT-4o)" style="width: 45%;" />
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
          <el-button @click="providerDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSaveProvider">确认</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 从API获取模型选择 Dialog -->
    <el-dialog v-model="fetchModelsDialogVisible" title="选择要添加的模型" width="500px">
      <el-input v-model="modelSearchQuery" placeholder="搜索模型" clearable class="model-search-input" />
      <el-scrollbar height="300px">
        <el-checkbox-group v-model="selectedFetchedModels" class="fetched-model-group">
          <el-checkbox v-for="model in filteredFetchedModels" :key="model.modelId" :label="model.modelId" border class="fetched-model-checkbox">
            {{ model.name }}
          </el-checkbox>
        </el-checkbox-group>
      </el-scrollbar>
      <template #footer>
        <el-button @click="fetchModelsDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddFetchedModels">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑模型 Dialog -->
    <el-dialog v-model="modelDialogVisible" :title="isEditingModel ? '编辑 AI 模型' : '新增 AI 模型'" width="600px" :close-on-click-modal="false">
      <el-form ref="modelFormRef" :model="modelForm" :rules="modelFormRules" label-width="120px">
        <el-form-item label="模型 ID" prop="modelId">
          <el-input v-model="modelForm.modelId" placeholder="例如：gpt-4o" />
        </el-form-item>
        <el-form-item label="模型显示名称" prop="name">
          <el-input v-model="modelForm.name" placeholder="例如：GPT-4o" />
        </el-form-item>
      </el-form>
      <div v-if="!isEditingModel" class="add-model-actions">
        <el-button @click="handleFetchModelsForProvider" :loading="isFetchingModels">
          <el-icon><Download /></el-icon>从API获取并选择
        </el-button>
      </div>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveModel">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, nextTick, computed } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type ElTable } from 'element-plus';
import { Plus, Delete, Download } from '@element-plus/icons-vue';
import type { AIProviderWithModels, AIModel, AIModelCreate, AIModelBase, AIProviderUpdate, ProviderWithModelsCreate } from '@/api/types';

// 为表单数据定义一个清晰、准确的接口
interface ProviderFormData {
  name: string;
  apiHost: string;
  apiKey: string;
  models: (AIModelBase & { id?: string })[]; // 模型可能包含id(已存在)或不包含(新添加)
}

// 定义一个类型来安全地处理API错误
type ApiError = {
  response?: {
    data?: {
      detail?: string;
    };
  };
};

const API_KEY_PLACEHOLDER = '********';

// Store setup
const providerStore = useProviderStore();
const { providers, isLoading, globalSettings } = storeToRefs(providerStore);

// Component State
const providerTableRef = ref<InstanceType<typeof ElTable>>();
const selectedProvider = ref<AIProviderWithModels | null>(null);
const providerDialogVisible = ref(false);
const modelDialogVisible = ref(false);
const fetchModelsDialogVisible = ref(false);
const isTestingConnection = ref(false);
const isFetchingModels = ref(false);
const isEditingProvider = ref(false);
const editingProviderId = ref<string | null>(null);
const isEditingModel = ref(false);
const editingModelId = ref<string | null>(null);

// Forms and temporary state
const providerFormRef = ref<FormInstance>();
const modelFormRef = ref<FormInstance>();
const providerForm = reactive<ProviderFormData>({ name: '', apiHost: '', apiKey: '', models: [] });
const modelForm = reactive<Omit<AIModelCreate, 'providerId'>>({ name: '', modelId: '' });
const fetchedModels = ref<AIModelBase[]>([]);
const selectedFetchedModels = ref<string[]>([]);
const modelSearchQuery = ref('');
// 用于存储编辑时模型的初始状态，以便比较变更
let initialModels: AIModel[] = [];

// 表单验证规则
const providerFormRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入服务商名称', trigger: 'blur' }],
  apiHost: [{ required: true, message: '请输入 API Host', trigger: 'blur' }],
  apiKey: [{
    validator: (rule, value, callback) => {
      if (!isEditingProvider.value && !value) {
        callback(new Error('请输入 API Key'));
      } else if (isEditingProvider.value && !value) {
        // 在编辑模式下，如果 apiKey 为空，将其重置为占位符，表示不更新
        providerForm.apiKey = API_KEY_PLACEHOLDER;
        callback();
      } else {
        callback();
      }
    },
    trigger: 'blur'
  }],
});
const modelFormRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入模型显示名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
});

// Computed
const filteredFetchedModels = computed(() => {
  if (!modelSearchQuery.value) {
    return fetchedModels.value;
  }
  return fetchedModels.value.filter(model =>
    model.name.toLowerCase().includes(modelSearchQuery.value.toLowerCase())
  );
});

// Lifecycle and Watchers
onMounted(async () => {
  await Promise.all([
    providerStore.fetchGlobalSettings(),
    providerStore.fetchProviders(),
  ]);
});

watch(providers, (newProviders) => {
  if (newProviders.length > 0) {
    let providerToSelect: AIProviderWithModels | null = null;
    const lastSelectedId = globalSettings.value.last_selected_provider_id;

    if (selectedProvider.value) {
      providerToSelect = newProviders.find(p => p.id === selectedProvider.value!.id) ?? null;
    }

    if (!providerToSelect && lastSelectedId) {
      providerToSelect = newProviders.find(p => p.id === lastSelectedId) ?? null;
    }

    if (!providerToSelect) {
      providerToSelect = newProviders[0];
    }

    if (providerToSelect) {
       nextTick(() => {
        handleRowClick(providerToSelect!);
        providerTableRef.value?.setCurrentRow(providerToSelect);
      });
    }

  } else {
    selectedProvider.value = null;
  }
}, { deep: true, immediate: true });


watch(() => modelForm.modelId, (newId, oldId) => {
  if (!modelForm.name || modelForm.name === oldId) {
    modelForm.name = newId;
  }
});

watch(() => providerForm.models, (newModels, oldModels) => {
  if (!oldModels || newModels.length !== oldModels.length) return;

  for (let i = 0; i < newModels.length; i++) {
    const newModel = newModels[i];
    const oldModel = oldModels[i];
    if (newModel && oldModel && newModel.modelId !== oldModel.modelId) {
      if (!oldModel.name || oldModel.name === oldModel.modelId) {
        newModel.name = newModel.modelId;
      }
    }
  }
}, { deep: true });


// Provider Handlers
const handleRowClick = (row: AIProviderWithModels) => {
  selectedProvider.value = row;
};

const openAddProviderDialog = () => {
  isEditingProvider.value = false;
  editingProviderId.value = null;
  providerFormRef.value?.resetFields();
  Object.assign(providerForm, { name: '', apiHost: '', apiKey: '', models: [] });
  initialModels = [];
  providerDialogVisible.value = true;
};

const openEditProviderDialog = (provider: AIProviderWithModels) => {
  isEditingProvider.value = true;
  editingProviderId.value = provider.id;
  Object.assign(providerForm, {
    name: provider.name,
    apiHost: provider.apiHost,
    apiKey: API_KEY_PLACEHOLDER
  });
  // 深拷贝模型数据以避免直接修改store
  providerForm.models = JSON.parse(JSON.stringify(provider.models));
  initialModels = JSON.parse(JSON.stringify(provider.models)); // 保存初始状态用于对比
  providerDialogVisible.value = true;
};

const handleSaveProvider = async () => {
  if (!providerFormRef.value) return;
  await providerFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        if (isEditingProvider.value && editingProviderId.value) {
          // --- 逻辑分支：编辑现有服务商 ---

          // 1. 更新服务商自身信息
          const providerUpdateData: AIProviderUpdate = {
            name: providerForm.name,
            apiHost: providerForm.apiHost,
          };
          if (providerForm.apiKey && providerForm.apiKey !== API_KEY_PLACEHOLDER) {
            providerUpdateData.apiKey = providerForm.apiKey;
          }
          const providerUpdatePromise = providerStore.updateProvider(editingProviderId.value, providerUpdateData);

          // 2. 识别出需要 新增、删除、更新 的模型
          const currentModelIdsInForm = new Set(providerForm.models.filter(m => m.id).map(m => m.id!));

          const modelsToAdd = providerForm.models.filter(m => !m.id);
          const modelsToDelete = initialModels.filter(m => !currentModelIdsInForm.has(m.id));
          const modelsToUpdate = providerForm.models.filter(currentModel => {
            if (!currentModel.id) return false;
            const initialModel = initialModels.find(m => m.id === currentModel.id);
            return initialModel && initialModel.name !== currentModel.name;
          });

          // 3. 为所有模型操作创建 API 请求的 Promise
          const addPromises = modelsToAdd.map(m => providerStore.addModel({
            modelId: m.modelId, name: m.name, providerId: editingProviderId.value!,
          }));
          const deletePromises = modelsToDelete.map(m => providerStore.removeModel(m.id));
          const updatePromises = modelsToUpdate.map(m => providerStore.updateModel(m.id!, { name: m.name }));

          // 4. 并发执行所有数据库操作
          await Promise.all([ providerUpdatePromise, ...addPromises, ...deletePromises, ...updatePromises ]);

          ElMessage.success('更新服务商及模型成功！');

        } else {
          // --- 逻辑分支：创建新服务商 ---
          const createData: ProviderWithModelsCreate = {
              name: providerForm.name,
              apiHost: providerForm.apiHost,
              apiKey: providerForm.apiKey,
              models: providerForm.models,
          };
          await providerStore.addProviderWithModels(createData);
          ElMessage.success('新增服务商成功！');
        }

        providerDialogVisible.value = false;

      } catch (error) {
        const apiError = error as ApiError;
        const message = apiError?.response?.data?.detail || '操作失败，请检查控制台。';
        ElMessage.error(message);
      }
    }
  });
};


const handleDeleteProvider = async (provider: AIProviderWithModels) => {
  try {
    await ElMessageBox.confirm(`确定删除服务商 "${provider.name}" 吗？其下所有模型也将被删除。`, '警告', { type: 'warning' });
    await providerStore.removeProvider(provider.id);
    if (selectedProvider.value?.id === provider.id) {
      selectedProvider.value = null;
    }
    ElMessage.success('删除成功！');
  } catch (error) {
    if (error === 'cancel') return; // User cancelled the dialog, do nothing.
    const apiError = error as ApiError;
    const message = apiError?.response?.data?.detail || '删除失败，请检查控制台。';
    ElMessage.error(message);
  }
};

// Model Handlers
const openAddModelDialog = () => {
  isEditingModel.value = false;
  editingModelId.value = null;
  modelFormRef.value?.resetFields();
  Object.assign(modelForm, { name: '', modelId: '' });
  modelDialogVisible.value = true;
};

const openEditModelDialog = (model: AIModel) => {
  isEditingModel.value = true;
  editingModelId.value = model.id;
  Object.assign(modelForm, { name: model.name, modelId: model.modelId });
  modelDialogVisible.value = true;
};

const handleSaveModel = async () => {
  if (!modelFormRef.value || !selectedProvider.value) return;
  await modelFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        if (isEditingModel.value && editingModelId.value) {
          await providerStore.updateModel(editingModelId.value, { name: modelForm.name });
          ElMessage.success('更新模型成功！');
        } else {
          await providerStore.addModel({ ...modelForm, providerId: selectedProvider.value!.id });
          ElMessage.success('新增模型成功！');
        }
        modelDialogVisible.value = false;
      } catch (error) {
        const apiError = error as ApiError;
        const message = apiError?.response?.data?.detail || '操作失败，请检查控制台。';
        ElMessage.error(message);
      }
    }
  });
};

const handleDeleteModel = async (model: AIModel) => {
  try {
    await ElMessageBox.confirm(`确定删除模型 "${model.name}" 吗？`, '警告', { type: 'warning' });
    await providerStore.removeModel(model.id);
    ElMessage.success('删除模型成功！');
  } catch (error) {
    if (error === 'cancel') return; // User cancelled the dialog, do nothing.
    const apiError = error as ApiError;
    const message = apiError?.response?.data?.detail || '删除模型失败';
    ElMessage.error(message);
  }
};

// Dialog-specific Handlers
const handleApiKeyFocus = () => {
  if (providerForm.apiKey === API_KEY_PLACEHOLDER) {
    providerForm.apiKey = '';
  }
};

const handleApiKeyBlur = () => {
  if (isEditingProvider.value && providerForm.apiKey === '') {
    providerForm.apiKey = API_KEY_PLACEHOLDER;
  }
};

const handleTestConnection = async () => {
  if (!providerForm.apiHost || !providerForm.apiKey) {
    ElMessage.warning('请填写 API Host 和 API Key 以进行测试');
    return;
  }
  if (isEditingProvider.value && providerForm.apiKey === API_KEY_PLACEHOLDER) {
    ElMessage.warning('请输入一个新的 API Key 进行测试，或直接保存以继续使用旧的 Key。');
    return;
  }

  isTestingConnection.value = true;
  try {
    const res = await providerStore.testConnection({
      apiHost: providerForm.apiHost,
      apiKey: providerForm.apiKey
    });
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: res.message });
  } catch (error) {
    const apiError = error as ApiError;
    const message = apiError?.response?.data?.detail || '连接测试失败';
    ElMessage.error(message);
  } finally {
    isTestingConnection.value = false;
  }
};

const handleFetchModels = async () => {
  isFetchingModels.value = true;
  try {
    let models: AIModelBase[] = [];
    if (isEditingProvider.value && providerForm.apiKey === API_KEY_PLACEHOLDER) {
      models = await providerStore.fetchModelsForProvider(editingProviderId.value!);
    } else {
      if (!providerForm.apiHost || !providerForm.apiKey) {
        ElMessage.warning('请填写 API Host 和 API Key 以获取模型列表');
        isFetchingModels.value = false;
        return;
      }
      models = await providerStore.fetchExternalModels({ apiHost: providerForm.apiHost, apiKey: providerForm.apiKey });
    }

    fetchedModels.value = models;
    selectedFetchedModels.value = providerForm.models.map(m => m.modelId);
    modelSearchQuery.value = '';
    fetchModelsDialogVisible.value = true;
  } catch (error) {
    const apiError = error as ApiError;
    const message = apiError?.response?.data?.detail || '获取模型列表失败';
    ElMessage.error(message);
  } finally {
    isFetchingModels.value = false;
  }
};

const handleFetchModelsForProvider = async () => {
  if (!selectedProvider.value) return;
  isFetchingModels.value = true;
  try {
    const models = await providerStore.fetchModelsForProvider(selectedProvider.value.id);
    fetchedModels.value = models;
    selectedFetchedModels.value = [];
    modelSearchQuery.value = '';
    fetchModelsDialogVisible.value = true;
  } catch (error) {
    const apiError = error as ApiError;
    const message = apiError?.response?.data?.detail || '获取模型列表失败';
    ElMessage.error(message);
  } finally {
    isFetchingModels.value = false;
  }
};

const confirmAddFetchedModels = () => {
  const targetModelList = providerDialogVisible.value ? providerForm.models : [];

  selectedFetchedModels.value.forEach(modelId => {
    const modelExists = targetModelList.some(m => m.modelId === modelId);
    if (!modelExists) {
      const newModel = { name: modelId, modelId: modelId };
      targetModelList.push(newModel);
    }
  });

  if (modelDialogVisible.value && selectedProvider.value) {
    const modelsToAdd = selectedFetchedModels.value
      .filter(modelId => !selectedProvider.value!.models.some(m => m.modelId === modelId))
      .map(modelId => ({ name: modelId, modelId: modelId, providerId: selectedProvider.value!.id }));

    Promise.all(modelsToAdd.map(m => providerStore.addModel(m))).then(() => {
      ElMessage.success(`已批量添加 ${modelsToAdd.length} 个模型。`);
    });
  }

  fetchModelsDialogVisible.value = false;
};

const addModelEntryToForm = () => {
  providerForm.models.push({ name: '', modelId: '' });
};

const removeModelEntryFromForm = (index: number) => {
  providerForm.models.splice(index, 1);
};
</script>

<style>
.provider-dialog .el-dialog__body {
  padding-top: 10px;
  padding-bottom: 10px;
}
</style>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header h2 {
  margin: 0;
  font-size: 20px;
}
.provider-info {
  margin-bottom: 16px;
  font-size: 14px;
  color: #606266;
}
.dialog-body-wrapper {
  display: flex;
  flex-direction: column;
  max-height: 65vh;
}
.form-section {
  flex-shrink: 0;
}
.scrollable-content {
  flex-grow: 1;
  overflow-y: auto;
  padding: 0 10px;
  margin: 0 -10px;
}
.model-form-header {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.header-item {
  width: 45%;
}
.header-item:first-of-type {
  margin-right: 10px;
}
.model-form-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.delete-model-btn {
  margin-left: 10px;
}
.model-search-input {
  margin-bottom: 15px;
}
.fetched-model-group {
  display: flex;
  flex-direction: column;
}
.fetched-model-checkbox {
  width: 100%;
  margin-bottom: 8px;
  margin-left: 0 !important;
}
.add-model-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 20px;
}
</style>
