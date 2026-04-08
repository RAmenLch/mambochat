<!-- frontend/mambo/src/mobile/components/settings/MobileProviderModelManager.vue -->
<template>
  <div class="mobile-pm-manager">
    <!-- 视图1: 服务商列表 -->
    <div v-if="!selectedProvider" class="view-container">
      <div class="list-header">
        <span>{{ t('provider.list.title') }}</span>
        <el-button type="primary" :icon="Plus" size="small" @click="openProviderDialog(null)">
          {{ t('provider.list.add') }}
        </el-button>
      </div>

      <div class="provider-list" v-loading="isLoading">
        <div
          v-for="provider in providers"
          :key="provider.id"
          class="list-card"
          @click="selectProvider(provider)"
        >
          <div class="card-main">
            <div class="card-title">{{ provider.name }}</div>
            <div class="card-desc">{{ provider.apiHost }}</div>
          </div>
          <div class="card-actions" @click.stop>
             <el-button link type="primary" :icon="Edit" @click="openProviderDialog(provider)"></el-button>
             <el-button link type="danger" :icon="Delete" @click="handleDeleteProvider(provider)"></el-button>
          </div>
          <el-icon class="card-arrow"><ArrowRight /></el-icon>
        </div>
        <el-empty v-if="!isLoading && providers.length === 0" :description="t('provider.list.empty')" />
      </div>
    </div>

    <!-- 视图2: 模型列表 (服务商详情) -->
    <div v-else class="view-container">
      <div class="detail-header">
        <el-button link :icon="ArrowLeft" @click="selectedProvider = null" class="back-btn">
          {{ t('common.action.back') }}
        </el-button>
        <span class="title">{{ selectedProvider.name }}</span>
        <el-dropdown trigger="click" @command="handleProviderCommand">
          <el-button link :icon="MoreFilled"></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="edit" :icon="Edit">{{ t('common.action.edit') }}</el-dropdown-item>
              <el-dropdown-item command="delete" :icon="Delete" divided>{{ t('common.action.delete') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div class="model-actions-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openModelDialog(null)">
          {{ t('model.list.add') }}
        </el-button>
        <el-button size="small" :icon="Download" @click="handleFetchModels" :loading="isFetchingModels">
          {{ t('model.list.fetch') }}
        </el-button>
      </div>

      <div class="model-list">
        <div
          v-for="model in selectedProvider.models"
          :key="model.id"
          class="list-card is-model"
          @click="openModelDialog(model)"
        >
          <div class="card-main">
            <div class="card-title">
              {{ model.name }}
              <el-tag size="small" type="info" class="model-type-tag">{{ model.model_type }}</el-tag>
            </div>
            <div class="card-desc">{{ model.modelId }}</div>
          </div>
          <el-button
            link
            type="danger"
            :icon="Delete"
            class="delete-model-btn"
            @click.stop="handleDeleteModel(model)"
          ></el-button>
          <el-icon
            class="star-icon"
            :class="{ starred: model.starred }"
            @click.stop="handleToggleStar(model)"
          >
            <Star />
          </el-icon>
        </div>
        <el-empty v-if="selectedProvider.models.length === 0" :description="t('model.list.empty')" />
      </div>
    </div>

    <!-- 弹窗: 服务商表单 -->
    <MobileProviderFormDialog
      v-model:visible="providerDialogVisible"
      :provider-data="currentProviderData"
      @submitted="onDialogSubmitted"
    />

    <!-- 弹窗: 模型表单 -->
    <MobileModelFormDialog
      v-model:visible="modelDialogVisible"
      :model-data="currentModelData"
      :provider-id="selectedProvider?.id ?? null"
      @submitted="onDialogSubmitted"
    />

    <!-- 弹窗: 获取模型 -->
    <MobileFetchModelsDialog
      v-model:visible="fetchDialogVisible"
      :fetched-models="fetchedModels"
      :existing-model-ids="existingModelIds"
      @confirm="onConfirmFetchModels"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Edit, Delete, ArrowRight, ArrowLeft, Download, MoreFilled, Star } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import type { AIProviderWithModels, AIModel, AIModelBase } from '@/api/types';
import { useSystemConfigStore } from '@/stores/systemConfigStore'; // 引入

// 引入移动端专用子组件
import MobileProviderFormDialog from './dialogs/MobileProviderFormDialog.vue';
import MobileModelFormDialog from './dialogs/MobileModelFormDialog.vue';
import MobileFetchModelsDialog from './dialogs/MobileFetchModelsDialog.vue';

const { t } = useI18n();
const providerStore = useProviderStore();
const { providers, isLoading } = storeToRefs(providerStore);

// 视图状态
const selectedProvider = ref<AIProviderWithModels | null>(null);
const isFetchingModels = ref(false);

// 弹窗状态
const providerDialogVisible = ref(false);
const currentProviderData = ref<AIProviderWithModels | null>(null);

const modelDialogVisible = ref(false);
const currentModelData = ref<AIModel | null>(null);

const fetchDialogVisible = ref(false);
const fetchedModels = ref<AIModelBase[]>([]);
const existingModelIds = ref<string[]>([]);
const systemConfigStore = useSystemConfigStore(); // 初始化


onMounted(async () => {
  await systemConfigStore.fetchSystemConfig();
  await providerStore.fetchProviders();
});

// 监听 providers 变化，如果当前选中的服务商被删除，则返回列表
watch(providers, (newPros) => {
  if (selectedProvider.value) {
    const exists = newPros.find(p => p.id === selectedProvider.value!.id);
    if (!exists) {
      selectedProvider.value = null;
    } else {
      // 更新引用以保持响应式
      selectedProvider.value = exists;
    }
  }
}, { deep: true });

// --- Provider Logic ---
const selectProvider = (provider: AIProviderWithModels) => {
  selectedProvider.value = provider;
};

const openProviderDialog = (provider: AIProviderWithModels | null) => {
  currentProviderData.value = provider;
  providerDialogVisible.value = true;
};

const handleProviderCommand = (command: string) => {
  if (!selectedProvider.value) return;
  if (command === 'edit') {
    openProviderDialog(selectedProvider.value);
  } else if (command === 'delete') {
    handleDeleteProvider(selectedProvider.value);
  }
};

const handleDeleteProvider = async (provider: AIProviderWithModels) => {
  try {
    await ElMessageBox.confirm(
      t('provider.list.deleteConfirm', { name: provider.name }),
      t('common.action.delete'),
      { type: 'warning' }
    );
    await providerStore.removeProvider(provider.id);
    if (selectedProvider.value?.id === provider.id) {
      selectedProvider.value = null;
    }
    ElMessage.success(t('provider.list.deleteSuccess'));
  } catch (error) {
    // User cancelled
  }
};

// --- Model Logic ---
const openModelDialog = (model: AIModel | null) => {
  currentModelData.value = model;
  modelDialogVisible.value = true;
};

const handleDeleteModel = async (model: AIModel) => {
  try {
    await ElMessageBox.confirm(
      t('model.list.deleteConfirm', { name: model.name }),
      t('common.action.delete'),
      { type: 'warning' }
    );
    await providerStore.removeModel(model.id);
    ElMessage.success(t('model.list.deleteSuccess'));
  } catch (error) {
    // User cancelled
  }
};

const handleToggleStar = async (model: AIModel) => {
  await providerStore.updateModel(model.id, { starred: !model.starred });
};

const handleFetchModels = async () => {
  if (!selectedProvider.value) return;
  isFetchingModels.value = true;
  try {
    const models = await providerStore.fetchModelsForProvider(
      selectedProvider.value.id,
      selectedProvider.value.use_proxy
    );
    fetchedModels.value = models;
    existingModelIds.value = selectedProvider.value.models.map(m => m.modelId);
    fetchDialogVisible.value = true;
  } catch (error) {
    ElMessage.error(t('model.list.fetchFailed'));
  } finally {
    isFetchingModels.value = false;
  }
};

const onConfirmFetchModels = (selectedIds: string[]) => {
  if (!selectedProvider.value) return;

  const modelsToAdd = selectedIds
    .filter(id => !existingModelIds.value.includes(id))
    .map(id => {
      const info = fetchedModels.value.find(m => m.modelId === id);
      return {
        name: info?.name || id,
        modelId: id,
        model_type: info?.model_type || 'chat',
        providerId: selectedProvider.value!.id,
        meta_config: info?.meta_config || null
      };
    });

  if (modelsToAdd.length > 0) {
    Promise.all(modelsToAdd.map(m => providerStore.addModel(m)))
      .then(() => ElMessage.success(t('model.list.batchAddSuccess', { count: modelsToAdd.length })))
      .catch(() => ElMessage.error(t('common.error.operationFailed')));
  }
  fetchDialogVisible.value = false;
};

const onDialogSubmitted = () => {
  providerStore.fetchProviders();
};
</script>

<style scoped>
.mobile-pm-manager {
  height: 100%;
  background: var(--color-background);
}

.view-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.list-header {
  padding: 15px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-background-soft);
}

.provider-list, .model-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.list-card {
  background: var(--color-background-soft);
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  position: relative;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.card-main {
  flex: 1;
  overflow: hidden;
}

.card-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-type-tag {
  transform: scale(0.9);
}

.card-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-actions {
  display: flex;
  gap: 5px;
  margin-right: 10px;
}

.card-arrow {
  color: var(--el-text-color-placeholder);
}

/* Detail View Styles */
.detail-header {
  height: 50px;
  padding: 0 15px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-background-soft);
}

.back-btn {
  margin-right: 10px;
}

.title {
  flex: 1;
  font-size: 17px;
  font-weight: 600;
  text-align: center;
  margin-right: 30px; /* Offset for back button width roughly */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-actions-bar {
  padding: 10px 15px;
  display: flex;
  gap: 10px;
  border-bottom: 1px solid var(--color-border);
}

.is-model {
  padding: 12px 15px;
}

.delete-model-btn {
  margin-left: auto;
  padding: 8px;
}

.star-icon {
  cursor: pointer;
  font-size: 18px;
  color: var(--el-text-color-disabled);
  transition: color 0.2s;
  margin-left: 4px;
}

.star-icon.starred {
  color: var(--el-color-warning);
}

.star-icon:active {
  color: var(--el-color-warning-light-5);
}
</style>
