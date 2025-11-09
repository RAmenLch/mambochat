<template>
  <div class="provider-model-manager">
    <!-- 1. 服务商管理区域 -->
    <div class="header">
      <h2>服务商 (Providers)</h2>
      <el-button type="primary" :icon="Plus" @click="openAddProviderDialog">
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
      :row-key="(row: AIProviderWithModels) => row.id"
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
      <el-button type="primary" :icon="Plus" @click="openAddModelDialog" :disabled="!selectedProvider">
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
    <ProviderFormDialog
      ref="providerFormDialogRef"
      v-model:visible="providerDialog.visible"
      :provider-data="providerDialog.data"
      @submitted="onDialogSubmitted"
      @fetch-models="onProviderFetchModels"
    />

    <ModelFormDialog
      v-model:visible="modelDialog.visible"
      :model-data="modelDialog.data"
      :provider-id="selectedProvider?.id ?? null"
      :is-fetching="isFetchingModels"
      @submitted="onDialogSubmitted"
      @fetch-models="handleFetchModelsForProvider"
    />

    <FetchModelsDialog
      v-model:visible="fetchModelsDialog.visible"
      :fetched-models="fetchModelsDialog.data"
      :existing-model-ids="fetchModelsDialog.existingIds"
      @confirm="onConfirmAddFetchedModels"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, nextTick } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox, type ElTable } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import type { AIProviderWithModels, AIModel, AIModelBase } from '@/api/types';

import ProviderFormDialog from './dialogs/ProviderFormDialog.vue';
import ModelFormDialog from './dialogs/ModelFormDialog.vue';
import FetchModelsDialog from './dialogs/FetchModelsDialog.vue';

const providerStore = useProviderStore();
const settingsStore = useSettingsStore();

const { providers, isLoading } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);


const providerTableRef = ref<InstanceType<typeof ElTable>>();
const providerFormDialogRef = ref<InstanceType<typeof ProviderFormDialog>>();
const selectedProvider = ref<AIProviderWithModels | null>(null);
const isFetchingModels = ref(false);

const providerDialog = reactive<{ visible: boolean; data: AIProviderWithModels | null }>({ visible: false, data: null });
const modelDialog = reactive<{ visible: boolean; data: AIModel | null }>({ visible: false, data: null });
const fetchModelsDialog = reactive<{ visible: boolean; data: AIModelBase[]; existingIds: string[] }>({ visible: false, data: [], existingIds: [] });

// Lifecycle and Watchers
onMounted(async () => {
  await settingsStore.fetchGlobalSettings();
  await providerStore.fetchProviders();
});

watch(providers, (newProviders) => {
  if (newProviders.length > 0) {
    const providerToSelect = newProviders.find(p => p.id === selectedProvider.value?.id)
      ?? newProviders.find(p => p.id === globalSettings.value.last_selected_provider_id)
      ?? newProviders[0];

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

// Provider Handlers
const handleRowClick = (row: AIProviderWithModels) => {
  selectedProvider.value = row;
};

const openAddProviderDialog = () => {
  providerDialog.data = null;
  providerDialog.visible = true;
};

const openEditProviderDialog = (provider: AIProviderWithModels) => {
  providerDialog.data = provider;
  providerDialog.visible = true;
};

const handleDeleteProvider = async (provider: AIProviderWithModels) => {
    await ElMessageBox.confirm(`确定删除服务商 "${provider.name}" 吗？其下所有模型也将被删除。`, '警告', { type: 'warning' });
    await providerStore.removeProvider(provider.id);
    if (selectedProvider.value?.id === provider.id) {
      selectedProvider.value = null;
    }
    ElMessage.success('删除成功！');
};

// Model Handlers
const openAddModelDialog = () => {
  modelDialog.data = null;
  modelDialog.visible = true;
};

const openEditModelDialog = (model: AIModel) => {
  modelDialog.data = model;
  modelDialog.visible = true;
};

const handleDeleteModel = async (model: AIModel) => {
    await ElMessageBox.confirm(`确定删除模型 "${model.name}" 吗？`, '警告', { type: 'warning' });
    await providerStore.removeModel(model.id);
    ElMessage.success('删除模型成功！');
};

// Dialog Event Handlers
const onDialogSubmitted = () => {
  providerStore.fetchProviders();
};

const onProviderFetchModels = (models: AIModelBase[]) => {
  fetchModelsDialog.data = models;
  fetchModelsDialog.existingIds = providerDialog.data?.models.map(m => m.modelId) || [];
  fetchModelsDialog.visible = true;
};

const handleFetchModelsForProvider = async () => {
  if (!selectedProvider.value) return;
  isFetchingModels.value = true;
  try {
    const models = await providerStore.fetchModelsForProvider(selectedProvider.value.id,selectedProvider.value.use_proxy);
    fetchModelsDialog.data = models;
    fetchModelsDialog.existingIds = selectedProvider.value.models.map(m => m.modelId);
    fetchModelsDialog.visible = true;
  } catch (error) {
    console.error('Failed to fetch models for provider:', error);
  } finally {
    isFetchingModels.value = false;
  }
};

const onConfirmAddFetchedModels = (selectedIds: string[]) => {
  if (providerDialog.visible) {
    providerFormDialogRef.value?.addFetchedModels(selectedIds, fetchModelsDialog.data);
  } else if (modelDialog.visible && selectedProvider.value) {
    const modelsToAdd = selectedIds
      .filter(id => !selectedProvider.value!.models.some(m => m.modelId === id))
      .map(id => {
        const modelInfo = fetchModelsDialog.data.find(m => m.modelId === id);
        return { name: modelInfo?.name || id, modelId: id, providerId: selectedProvider.value!.id };
      });

    Promise.all(modelsToAdd.map(m => providerStore.addModel(m)))
      .then(() => ElMessage.success(`已批量添加 ${modelsToAdd.length} 个模型。`))
      .catch((error) => {
          console.error('Failed to batch add models:', error);
        }
      );
  }
};
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h2 { margin: 0; font-size: 20px; }
.provider-info { margin-bottom: 16px; font-size: 14px; color: #606266; }
</style>
