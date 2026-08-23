<!-- MobileProviderModelManager.vue — 移动端服务商/模型管理（P2 重构） -->
<template>
  <div class="mobile-pm-manager">
    <!-- 视图1: 服务商列表 -->
    <transition name="slide-left">
      <div v-if="!selectedProvider" class="view-container">
        <div class="list-header">
          <span class="header-title">{{ t('provider.list.title') }}</span>
          <button class="header-add-btn" @click="openProviderDialog(null)">
            <el-icon :size="16"><Plus /></el-icon>
          </button>
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
              <button class="action-btn" @click="openProviderDialog(provider)">
                <el-icon :size="16"><Edit /></el-icon>
              </button>
              <button class="action-btn action-danger" @click="handleDeleteProvider(provider)">
                <el-icon :size="16"><Delete /></el-icon>
              </button>
            </div>
            <el-icon class="card-arrow"><ArrowRight /></el-icon>
          </div>
          <el-empty v-if="!isLoading && providers.length === 0" :description="t('provider.list.empty')" />
        </div>
      </div>
    </transition>

    <!-- 视图2: 模型列表 (服务商详情) -->
    <transition name="slide-right">
      <div v-if="selectedProvider" class="view-container">
        <div class="detail-header">
          <button class="back-btn" @click="selectedProvider = null">
            <el-icon :size="20"><ArrowLeft /></el-icon>
          </button>
          <span class="title">{{ selectedProvider.name }}</span>
          <el-dropdown trigger="click" @command="handleProviderCommand" popper-class="mobile-popper">
            <button class="more-btn">
              <el-icon :size="18"><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit" :icon="Edit">{{ t('common.action.edit') }}</el-dropdown-item>
                <el-dropdown-item command="delete" :icon="Delete" divided>{{ t('common.action.delete') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="model-actions-bar">
          <button class="action-chip" @click="openModelDialog(null)">
            <el-icon :size="14"><Plus /></el-icon>
            <span>{{ t('model.list.add') }}</span>
          </button>
          <button class="action-chip action-chip-download" @click="handleFetchModels" :disabled="isFetchingModels">
            <el-icon :size="14" :class="{ 'is-loading': isFetchingModels }"><Download /></el-icon>
            <span>{{ t('model.list.fetch') }}</span>
          </button>
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
                <span class="model-type-tag">{{ model.model_type }}</span>
              </div>
              <div class="card-desc">{{ model.modelId }}</div>
            </div>
            <button class="action-btn action-danger" @click.stop="handleDeleteModel(model)">
              <el-icon :size="16"><Delete /></el-icon>
            </button>
            <button class="star-btn" :class="{ starred: model.starred }" @click.stop="handleToggleStar(model)">
              <el-icon :size="16"><Star /></el-icon>
            </button>
          </div>
          <el-empty v-if="selectedProvider.models.length === 0" :description="t('model.list.empty')" />
        </div>
      </div>
    </transition>

    <!-- Bottom Sheet: 服务商表单 -->
    <MobileProviderFormDialog
      v-model:visible="providerDialogVisible"
      :provider-data="currentProviderData"
      @submitted="onDialogSubmitted"
    />

    <!-- Bottom Sheet: 模型表单 -->
    <MobileModelFormDialog
      v-model:visible="modelDialogVisible"
      :model-data="currentModelData"
      :provider-id="selectedProvider?.id ?? null"
      @submitted="onDialogSubmitted"
    />

    <!-- Bottom Sheet: 获取模型 -->
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
import { useSystemConfigStore } from '@/stores/systemConfigStore';

import MobileProviderFormDialog from './dialogs/MobileProviderFormDialog.vue';
import MobileModelFormDialog from './dialogs/MobileModelFormDialog.vue';
import MobileFetchModelsDialog from './dialogs/MobileFetchModelsDialog.vue';

const { t } = useI18n();
const providerStore = useProviderStore();
const { providers, isLoading } = storeToRefs(providerStore);

const selectedProvider = ref<AIProviderWithModels | null>(null);
const isFetchingModels = ref(false);

const providerDialogVisible = ref(false);
const currentProviderData = ref<AIProviderWithModels | null>(null);

const modelDialogVisible = ref(false);
const currentModelData = ref<AIModel | null>(null);

const fetchDialogVisible = ref(false);
const fetchedModels = ref<AIModelBase[]>([]);
const existingModelIds = ref<string[]>([]);
const systemConfigStore = useSystemConfigStore();

onMounted(async () => {
  await systemConfigStore.fetchSystemConfig();
  await providerStore.fetchProviders();
});

watch(providers, (newPros) => {
  if (selectedProvider.value) {
    const exists = newPros.find(p => p.id === selectedProvider.value!.id);
    if (!exists) { selectedProvider.value = null; }
    else { selectedProvider.value = exists; }
  }
}, { deep: true });

const selectProvider = (provider: AIProviderWithModels) => { selectedProvider.value = provider; };
const openProviderDialog = (provider: AIProviderWithModels | null) => { currentProviderData.value = provider; providerDialogVisible.value = true; };

const handleProviderCommand = (command: string) => {
  if (!selectedProvider.value) return;
  if (command === 'edit') openProviderDialog(selectedProvider.value);
  else if (command === 'delete') handleDeleteProvider(selectedProvider.value);
};

const handleDeleteProvider = async (provider: AIProviderWithModels) => {
  try {
    await ElMessageBox.confirm(t('provider.list.deleteConfirm', { name: provider.name }), t('common.action.delete'), { type: 'warning' });
    await providerStore.removeProvider(provider.id);
    if (selectedProvider.value?.id === provider.id) selectedProvider.value = null;
    ElMessage.success(t('provider.list.deleteSuccess'));
  } catch {}
};

const openModelDialog = (model: AIModel | null) => { currentModelData.value = model; modelDialogVisible.value = true; };

const handleDeleteModel = async (model: AIModel) => {
  try {
    await ElMessageBox.confirm(t('model.list.deleteConfirm', { name: model.name }), t('common.action.delete'), { type: 'warning' });
    await providerStore.removeModel(model.id);
    ElMessage.success(t('model.list.deleteSuccess'));
  } catch {}
};

const handleToggleStar = async (model: AIModel) => {
  await providerStore.updateModel(model.id, { starred: !model.starred });
};

const handleFetchModels = async () => {
  if (!selectedProvider.value) return;
  isFetchingModels.value = true;
  try {
    const models = await providerStore.fetchModelsForProvider(selectedProvider.value.id, selectedProvider.value.use_proxy);
    fetchedModels.value = models;
    existingModelIds.value = selectedProvider.value.models.map(m => m.modelId);
    fetchDialogVisible.value = true;
  } catch { ElMessage.error(t('model.list.fetchFailed')); }
  finally { isFetchingModels.value = false; }
};

const onConfirmFetchModels = (selectedIds: string[]) => {
  if (!selectedProvider.value) return;
  const modelsToAdd = selectedIds
    .filter(id => !existingModelIds.value.includes(id))
    .map(id => {
      const info = fetchedModels.value.find(m => m.modelId === id);
      return { name: info?.name || id, modelId: id, model_type: info?.model_type || 'chat', providerId: selectedProvider.value!.id, meta_config: info?.meta_config || null };
    });
  if (modelsToAdd.length > 0) {
    Promise.all(modelsToAdd.map(m => providerStore.addModel(m)))
      .then(() => ElMessage.success(t('model.list.batchAddSuccess', { count: modelsToAdd.length })))
      .catch(() => ElMessage.error(t('common.error.operationFailed')));
  }
  fetchDialogVisible.value = false;
};

const onDialogSubmitted = () => { providerStore.fetchProviders(); };
</script>

<style scoped>
.mobile-pm-manager { height: 100%; background: var(--color-background); position: relative; overflow: hidden; }

.view-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; background: var(--color-background); }

/* ===== List Header ===== */
.list-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255,255,255,0.72); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; z-index: 5;
}
.header-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.header-add-btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; border-radius: 50%;
  background: var(--el-color-primary); color: #fff; cursor: pointer;
}

/* ===== List Cards ===== */
.provider-list, .model-list { flex: 1; overflow-y: auto; padding: 8px 12px; -webkit-overflow-scrolling: touch; }

.list-card {
  display: flex; align-items: center; padding: 14px 12px; margin-bottom: 8px;
  background: var(--color-background-soft); border-radius: 12px;
  border: 0.5px solid rgba(0,0,0,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}
.list-card:active { background: var(--el-fill-color); }

.card-main { flex: 1; min-width: 0; }
.card-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 6px; }
.card-desc { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.model-type-tag { font-size: 11px; font-weight: 500; color: var(--el-color-info); background: var(--el-color-info-light-9); padding: 1px 6px; border-radius: 4px; }

.card-actions { display: flex; gap: 4px; margin-right: 6px; flex-shrink: 0; }
.action-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border: none; border-radius: 50%;
  background: transparent; color: var(--el-text-color-secondary); cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.action-btn:active { background: rgba(0,0,0,0.05); }
.action-danger:active { color: var(--el-color-danger); background: var(--el-color-danger-light-9); }

.card-arrow { color: var(--el-text-color-placeholder); flex-shrink: 0; }

.star-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border: none; border-radius: 50%;
  background: transparent; color: var(--el-text-color-disabled); cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.star-btn.starred { color: var(--el-color-warning); }
.star-btn:active { background: rgba(0,0,0,0.05); }

/* ===== Detail Header ===== */
.detail-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px; flex-shrink: 0;
  background: rgba(255,255,255,0.72); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0,0,0,0.08); z-index: 5;
}
.back-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border: none; border-radius: 50%;
  background: transparent; color: var(--el-text-color-primary); cursor: pointer;
  flex-shrink: 0;
}
.back-btn:active { background: rgba(0,0,0,0.06); }
.title { flex: 1; font-size: 16px; font-weight: 700; color: var(--el-text-color-primary); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.more-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border: none; border-radius: 50%;
  background: transparent; color: var(--el-text-color-secondary); cursor: pointer;
  flex-shrink: 0;
}
.more-btn:active { background: rgba(0,0,0,0.06); }

/* ===== Model Actions Bar ===== */
.model-actions-bar { display: flex; gap: 8px; padding: 10px 14px; flex-shrink: 0; }
.action-chip {
  display: inline-flex; align-items: center; gap: 4px; height: 30px; padding: 0 12px;
  font-size: 13px; font-weight: 500; color: var(--el-color-primary);
  background: var(--el-color-primary-light-9); border: none; border-radius: 15px;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.action-chip:active { background: var(--el-color-primary-light-7); }
.action-chip-download { color: var(--el-color-success-dark-2); background: var(--el-color-success-light-9); }
.action-chip-download:active { background: var(--el-color-success-light-7); }

/* ===== Transitions ===== */
.slide-left-enter-active, .slide-left-leave-active,
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.3s ease; }
.slide-left-leave-to { transform: translateX(-100%); }
.slide-right-enter-from { transform: translateX(100%); }

/* ===== Dark Mode ===== */
@media (prefers-color-scheme: dark) {
  .list-header, .detail-header {
    background: rgba(30,30,30,0.72); border-bottom-color: rgba(255,255,255,0.08);
  }
  .list-card { border-color: rgba(255,255,255,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
  .action-btn:active { background: rgba(255,255,255,0.08); }
  .back-btn:active, .more-btn:active { background: rgba(255,255,255,0.08); }
  .star-btn:active { background: rgba(255,255,255,0.08); }
}
</style>
