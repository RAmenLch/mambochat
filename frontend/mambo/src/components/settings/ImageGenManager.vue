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

      <el-table-column :label="t('settings.imageGen.columns.mcpServer')" min-width="140">
        <template #default="{ row }">
          <span>{{ serverName(row.mcpServerId) }}</span>
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

        <el-form-item :label="t('settings.imageGen.form.mcpServer')" required>
          <el-select v-model="form.mcpServerId" :placeholder="t('settings.imageGen.form.mcpServerPlaceholder')" style="width: 100%">
            <el-option
              v-for="server in selectableServers"
              :key="server.id"
              :label="server.name"
              :value="server.id"
            />
          </el-select>
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
import type { ImageGenConfig } from '@/api/types';

const { t } = useI18n();
const imageGenStore = useImageGenStore();
const mcpStore = useMcpStore();

const dialogVisible = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const editingId = ref<string | null>(null);
const checkingIds = ref<Set<string>>(new Set());

const resolutionPresets = ['512x512', '768x768', '1024x1024', '1024x1536', '1536x1024', '768x1344', '1344x768'];

const form = reactive({
  name: '',
  description: '',
  mcpServerId: '',
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

function serverName(id: string): string {
  return mcpStore.availableServices.find(s => s.id === id)?.name || id.slice(0, 8);
}

function resetForm() {
  form.name = '';
  form.description = '';
  form.mcpServerId = '';
  form.defaultCount = 1;
  form.defaultResolution = '1024x1024';
  form.defaultSync = true;
  form.defaultWaitTimeout = 0;
  form.timeout = undefined;
  form.enableStandardTools = true;
  form.enableGenerateShow = true;
  form.isEnabled = true;
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
  form.mcpServerId = row.mcpServerId;
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
  if (!form.name.trim() || !form.mcpServerId) {
    ElMessage.warning(t('settings.imageGen.form.requiredHint'));
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
      mcpServerId: form.mcpServerId,
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
    if (result.status === 'healthy') {
      ElMessage.success(t('settings.imageGen.checkPassed'));
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
  await Promise.all([imageGenStore.fetchConfigs(), mcpStore.fetchAvailableServices()]);
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
