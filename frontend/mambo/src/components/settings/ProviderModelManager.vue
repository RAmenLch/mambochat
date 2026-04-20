<template>
  <div class="provider-model-manager">
    <!-- 1. 服务商管理区域 -->
    <div class="header">
      <h2>{{ t('provider.list.title') }}</h2>
      <el-button type="primary" :icon="Plus" @click="openAddProviderDialog">
        {{ t('provider.list.add') }}
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
      <el-table-column prop="name" :label="t('provider.list.name')" width="220" />
<!--      <el-table-column prop="worker_type" label="后端类型" width="160">-->
<!--        <template #default="{ row }">-->
<!--          <el-tag :type="getWorkerTypeTag(row.worker_type)">-->
<!--            {{ row.worker_type }}-->
<!--          </el-tag>-->
<!--        </template>-->
<!--      </el-table-column>-->
      <el-table-column prop="apiHost" :label="t('provider.list.apiHost')" />
      <el-table-column :label="t('provider.list.action')" width="180" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openEditProviderDialog(row)">{{ t('common.action.edit') }}</el-button>
          <el-button link type="danger" @click.stop="handleDeleteProvider(row)">{{ t('common.action.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />

    <!-- 2. 模型管理区域 -->
    <div class="header">
      <h2>{{ t('model.list.title') }}</h2>
      <div>
        <el-button type="primary" :icon="Plus" @click="openAddModelDialog" :disabled="!selectedProvider">
          {{ t('model.list.add') }}
        </el-button>
        <el-button @click="handleFetchModelsForProvider" :loading="isFetchingModels" :disabled="!selectedProvider">
          <el-icon><Download /></el-icon>
          {{ t('model.list.fetch') }}
        </el-button>
      </div>
    </div>
    <div v-if="selectedProvider">
      <p class="provider-info">
        {{ t('provider.list.currentProvider') }}: <strong>{{ selectedProvider.name }}</strong>
      </p>
      <el-table :data="selectedProvider.models" border style="width: 100%">
        <el-table-column :label="t('model.table.star')" width="50" align="center">
          <template #default="{ row }">
            <el-icon
              class="star-icon"
              :class="{ starred: row.starred }"
              @click="handleToggleStar(row)"
            >
              <Star />
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column prop="modelId" :label="t('model.table.id')" width="220" />
        <el-table-column prop="name" :label="t('model.table.name')" width="200" />
        <el-table-column prop="model_type" :label="t('model.table.type')" width="50" align="center">
          <template #default="{ row }">
            <el-tooltip :content="row.model_type === 'embedding' ? t('model.table.typeEmbedding') : t('model.table.typeChat')" placement="top">
              <el-icon size="18">
                <component :is="row.model_type === 'embedding' ? Connection : ChatDotRound" />
              </el-icon>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="t('model.table.context')" width="180" align="center">
          <template #default="{ row }">
            <div v-if="row.meta_config">
              <span>{{ row.meta_config.context_length || '-' }}</span>
              <span class="separator">/</span>
              <span v-if="row.model_type === 'embedding'">
                {{ row.meta_config.embedding_dimension ? row.meta_config.embedding_dimension + ' dim' : '-' }}
              </span>
              <span v-else>
                {{ row.meta_config.max_output_tokens || '-' }}
              </span>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
<!--        <el-table-column label="分词器" width="120" align="center">-->
<!--          <template #default="{ row }">-->
<!--            <span>{{ row.meta_config?.tokenizer || '-' }}</span>-->
<!--          </template>-->
<!--        </el-table-column>-->
        <el-table-column :label="t('model.table.modality')" width="200" align="center">
          <template #default="{ row }">
            <div class="modality-cell" v-if="row.meta_config && row.model_type !== 'embedding'">
              <div class="modality-group">
                <el-tooltip v-for="mod in row.meta_config.input_modalities" :key="mod" :content="mod" placement="top">
                  <el-icon class="modality-icon"><component :is="modalityIcons[mod]" /></el-icon>
                </el-tooltip>
              </div>
              <el-icon v-if="row.meta_config.input_modalities?.length && row.meta_config.output_modalities?.length" class="arrow-icon"><ArrowRight /></el-icon>
              <div class="modality-group">
                <el-tooltip v-for="mod in row.meta_config.output_modalities" :key="mod" :content="mod" placement="top">
                  <el-icon class="modality-icon"><component :is="modalityIcons[mod]" /></el-icon>
                </el-tooltip>
              </div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('model.table.params')" align="center" width="100">
          <template #default="{ row }">
            <el-popover v-if="row.meta_config?.supported_parameters?.length" placement="top" :width="200" trigger="hover">
              <template #reference>
                <el-button link type="primary">{{ t('model.table.viewParams') }}</el-button>
              </template>
              <div class="parameter-list">
                <el-tag v-for="param in row.meta_config.supported_parameters" :key="param" size="small" type="info">{{ param }}</el-tag>
              </div>
            </el-popover>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('provider.list.action')" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditModelDialog(row)">{{ t('common.action.edit') }}</el-button>
            <el-button link type="danger" @click="handleDeleteModel(row)">{{ t('common.action.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-empty v-else :description="t('provider.list.empty')" />

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
      @submitted="onDialogSubmitted"
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
import { ref, reactive, watch, onMounted, nextTick, shallowRef, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox, type ElTable } from 'element-plus';
import {
  Plus, Document, Picture, Headset, VideoCamera, Folder, ArrowRight, Download,
  ChatDotRound, Connection, Star
} from '@element-plus/icons-vue';
import type { AIProviderWithModels, AIModel, AIModelBase, AIModelCreate, ProviderWorkerType } from '@/api/types';

import ProviderFormDialog from './dialogs/ProviderFormDialog.vue';
import ModelFormDialog from './dialogs/ModelFormDialog.vue';
import FetchModelsDialog from './dialogs/FetchModelsDialog.vue';

const { t } = useI18n();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const systemConfigStore = useSystemConfigStore();

const { providers, isLoading } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);

const providerTableRef = ref<InstanceType<typeof ElTable>>();
const providerFormDialogRef = ref<InstanceType<typeof ProviderFormDialog>>();
const selectedProvider = ref<AIProviderWithModels | null>(null);
const isFetchingModels = ref(false);

const providerDialog = reactive<{ visible: boolean; data: AIProviderWithModels | null }>({ visible: false, data: null });
const modelDialog = reactive<{ visible: boolean; data: AIModel | null }>({ visible: false, data: null });
const fetchModelsDialog = reactive<{ visible: boolean; data: AIModelBase[]; existingIds: string[] }>({ visible: false, data: [], existingIds: [] });

// 映射模态字符串到图标组件
const modalityIcons = shallowRef<Record<string, Component>>({
  text: Document,
  image: Picture,
  audio: Headset,
  video: VideoCamera,
  file: Folder,
});

// Lifecycle and Watchers
onMounted(async () => {
  await systemConfigStore.fetchSystemConfig();
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

// Helper
const getWorkerTypeTag = (type: ProviderWorkerType) => {
  switch (type) {
    case 'openai': return 'success';
    case 'google': return 'warning';
    case 'deepseek': return 'primary';
    default: return 'info';
  }
};

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
    await ElMessageBox.confirm(
      t('provider.list.deleteConfirm', { name: provider.name }),
      t('common.action.delete'), // Title: Warning or Delete
      { type: 'warning', confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') }
    );
    await providerStore.removeProvider(provider.id);
    if (selectedProvider.value?.id === provider.id) {
      selectedProvider.value = null;
    }
    ElMessage.success(t('provider.list.deleteSuccess'));
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
    await ElMessageBox.confirm(
      t('model.list.deleteConfirm', { name: model.name }),
      t('common.action.delete'),
      { type: 'warning', confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') }
    );
    await providerStore.removeModel(model.id);
    ElMessage.success(t('model.list.deleteSuccess'));
};

const handleToggleStar = async (model: AIModel) => {
  await providerStore.updateModel(model.id, { starred: !model.starred });
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
    const models = await providerStore.fetchModelsForProvider(selectedProvider.value.id, selectedProvider.value.use_proxy);
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
  // 场景1: 在“新增/编辑服务商”弹窗中获取模型后确认
  if (providerDialog.visible) {
    providerFormDialogRef.value?.addFetchedModels(selectedIds, fetchModelsDialog.data);
  // 场景2: 在主界面点击“从API获取”后确认
  } else if (selectedProvider.value) {
    const modelsToAdd: AIModelCreate[] = selectedIds
      .filter(id => !selectedProvider.value!.models.some(m => m.modelId === id))
      .map(id => {
        const modelInfo = fetchModelsDialog.data.find(m => m.modelId === id);
        // 传递完整的模型信息，包括 meta_config 和 model_type
        return {
          name: modelInfo?.name || id,
          modelId: id,
          model_type: modelInfo?.model_type || 'chat',
          providerId: selectedProvider.value!.id,
          meta_config: modelInfo?.meta_config || null
        };
      });

    if (modelsToAdd.length > 0) {
      Promise.all(modelsToAdd.map(m => providerStore.addModel(m)))
        .then(() => ElMessage.success(t('model.list.batchAddSuccess', { count: modelsToAdd.length })))
        .catch((error) => {
            console.error('Failed to batch add models:', error);
          }
        );
    }
  }
};
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h2 { margin: 0; font-size: 20px; }
.provider-info { margin-bottom: 16px; font-size: 14px; color: #606266; }
.modality-cell { display: flex; align-items: center; justify-content: center; gap: 4px; }
.modality-group { display: flex; align-items: center; gap: 4px; }
.modality-icon { font-size: 16px; color: var(--el-text-color-regular); }
.arrow-icon { color: var(--el-text-color-secondary); }
.parameter-list { display: flex; flex-wrap: wrap; gap: 4px; }
.separator { margin: 0 4px; color: var(--el-text-color-secondary); }
.star-icon { cursor: pointer; font-size: 18px; color: var(--el-text-color-disabled); transition: color 0.2s; }
.star-icon.starred { color: var(--el-color-warning); }
.star-icon:hover { color: var(--el-color-warning-light-5); }
</style>
