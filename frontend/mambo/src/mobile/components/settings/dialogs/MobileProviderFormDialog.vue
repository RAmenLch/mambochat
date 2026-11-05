<!-- MobileProviderFormDialog.vue — 服务商表单（Bottom Sheet） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="internalVisible" class="sheet-overlay" @click="internalVisible = false">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>
          <div class="sheet-header">
            <span class="sheet-title">{{ isEditing ? t('provider.form.editTitle') : t('provider.form.addTitle') }}</span>
            <button class="sheet-close" @click="internalVisible = false">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="sheet-form">
              <div class="field-item">
                <label class="field-label">{{ t('provider.form.name') }}</label>
                <el-autocomplete
                  v-model="form.name"
                  :fetch-suggestions="querySearchProviders"
                  :placeholder="t('provider.form.namePlaceholder')"
                  style="width: 100%"
                  @select="handleProviderSelect"
                  :trigger-on-focus="true"
                  popper-class="mobile-popper"
                />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('provider.form.workerType') }}</label>
                <el-select v-model="form.worker_type" style="width: 100%" popper-class="mobile-popper">
                  <el-option-group :label="t('provider.form.workerGroupChat')">
                    <el-option label="OpenAI Compatible" value="openai" />
                    <el-option label="Google Gemini" value="google" />
                    <el-option label="DeepSeek" value="deepseek" />
                    <el-option label="Anthropic" value="anthropic" />
                  </el-option-group>
                  <el-option-group :label="t('provider.form.workerGroupImage')">
                    <el-option :label="t('provider.form.workerOpenaiImages')" value="openai_images" />
                    <el-option :label="t('provider.form.workerOpenrouterImages')" value="openrouter_images" />
                  </el-option-group>
                </el-select>
                <div v-if="isImageWorker" class="field-hint">{{ imageExecutorHint }}</div>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('provider.form.apiHost') }}</label>
                <input v-model="form.apiHost" class="native-input" :placeholder="t('provider.form.apiHostPlaceholder')" />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('provider.form.apiKey') }}</label>
                <div class="password-row">
                  <input
                    :type="showKey ? 'text' : 'password'"
                    v-model="form.apiKey"
                    class="native-input"
                    :placeholder="t('provider.form.apiKeyPlaceholder')"
                  />
                  <button class="toggle-key" @click="showKey = !showKey">
                    <el-icon :size="16"><View v-if="!showKey" /><Hide v-else /></el-icon>
                  </button>
                </div>
              </div>

              <div class="field-item">
                <div class="switch-row">
                  <span class="field-label" style="margin-bottom:0">{{ t('provider.form.enableProxy') }}</span>
                  <el-switch v-model="form.use_proxy" :disabled="!isProxyGloballyEnabled" size="small" />
                </div>
                <div class="hint-text" v-if="!isProxyGloballyEnabled">
                  <el-icon :size="14"><WarningFilled /></el-icon> {{ t('provider.form.proxyTip') }}
                </div>
              </div>

              <!-- 模型清单（表单内维护 + 表单内拉取） -->
              <div class="sheet-divider">{{ t('model.list.title') }}</div>
              <div class="model-rows">
                <div v-for="(row, idx) in form.models" :key="row.modelId" class="model-row">
                  <div class="model-row-main">
                    <span class="model-row-name">{{ row.name || row.modelId }}</span>
                    <span class="model-row-id">{{ row.modelId }}</span>
                  </div>
                  <button class="row-remove" @click="removeModelRow(idx)">
                    <el-icon :size="14"><Minus /></el-icon>
                  </button>
                </div>
                <div v-if="form.models.length === 0" class="hint-text">{{ t('model.list.empty') }}</div>
              </div>
              <div class="model-actions">
                <button class="mini-btn" @click="addEmptyModelRow">+ {{ t('model.list.add') }}</button>
                <button class="mini-btn" :disabled="isFetchingModels" @click="handleFetchIntoForm">
                  <el-icon v-if="isFetchingModels" :size="12" class="is-loading"><Loading /></el-icon>
                  <el-icon v-else :size="12"><Download /></el-icon>
                  {{ t('model.list.fetch') }}
                </button>
              </div>
            </el-form>

            <button class="test-btn" @click="handleTestConnection" :disabled="isTesting">
              <el-icon v-if="isTesting" class="is-loading"><Loading /></el-icon>
              <span v-else>{{ t('provider.form.testConnection') }}</span>
            </button>
          </div>

          <!-- 拉取结果选择 -->
          <Teleport to="body">
            <Transition name="sheet">
              <div v-if="fetchPickerVisible" class="sheet-overlay" @click="fetchPickerVisible = false">
                <div class="sheet-panel" @click.stop>
                  <div class="sheet-handle"></div>
                  <div class="sheet-header">
                    <span class="sheet-title">{{ t('model.fetch.title') }}</span>
                    <button class="sheet-close" @click="fetchPickerVisible = false">
                      <el-icon :size="20"><Close /></el-icon>
                    </button>
                  </div>
                  <div class="sheet-body">
                    <div class="model-chips">
                      <button
                        v-for="m in fetchedModels"
                        :key="m.modelId"
                        class="model-chip"
                        :class="{ selected: pickedIds.includes(m.modelId) }"
                        @click="togglePick(m.modelId)"
                      >
                        <span class="chip-name">{{ m.name || m.modelId }}</span>
                        <span class="chip-id">{{ m.modelId }}</span>
                      </button>
                    </div>
                    <div v-if="fetchedModels.length === 0" class="hint-text">{{ t('model.list.empty') }}</div>
                  </div>
                  <div class="sheet-footer">
                    <button class="footer-btn footer-btn-cancel" @click="fetchPickerVisible = false">{{ t('common.action.cancel') }}</button>
                    <button class="footer-btn footer-btn-confirm" @click="applyFetchedModels">
                      {{ t('model.fetch.confirm') }}
                    </button>
                  </div>
                </div>
              </div>
            </Transition>
          </Teleport>

          <div class="sheet-footer">
            <button class="footer-btn footer-btn-cancel" @click="internalVisible = false">
              {{ t('common.action.cancel') }}
            </button>
            <button class="footer-btn footer-btn-confirm" @click="submitForm" :disabled="isSubmitting">
              {{ t('common.action.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Close, View, Hide, WarningFilled, Loading, Minus, Download } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { storeToRefs } from 'pinia';
import type { AIModelBase, AIProviderWithModels, AIProviderUpdate, ProviderWorkerType, ProviderWithModelsCreate, ModelType } from '@/api/types';
import { isAxiosError } from 'axios';
import { localizeProviderTestMessage } from '@/utils/providerTestMessage';

const API_KEY_PLACEHOLDER = '********';

interface AutocompleteSuggestion { value: string; }

const props = defineProps<{
  visible: boolean;
  providerData: AIProviderWithModels | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'submitted'): void;
}>();

const { t } = useI18n();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const systemConfigStore = useSystemConfigStore();
const { globalSettings } = storeToRefs(settingsStore);

const formRef = ref<FormInstance>();
const isSubmitting = ref(false);
const isTesting = ref(false);
const showKey = ref(false);

const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const isEditing = computed(() => !!props.providerData);
const isProxyGloballyEnabled = computed(() => globalSettings.value.proxy_enabled === true);

const form = reactive({
  name: '', apiHost: '', apiKey: '',
  worker_type: 'openai' as ProviderWorkerType, use_proxy: false,
  models: [] as Array<{ modelId: string; name: string; model_type: ModelType }>,
});

/** 生图执行器服务商：模型只能是生图模型，端点由执行器固定 */
const isImageWorker = computed(
  () => form.worker_type === 'openai_images' || form.worker_type === 'openrouter_images'
);
const imageExecutorHint = computed(() => {
  if (!isImageWorker.value) return '';
  const endpoint = form.worker_type === 'openrouter_images'
    ? '/images'
    : '/images/generations、/images/edits';
  return t('provider.form.imageExecutorHint', { endpoint });
});

// --- 表单内模型清单 / 拉取 ---
const isFetchingModels = ref(false);
const fetchPickerVisible = ref(false);
const fetchedModels = ref<AIModelBase[]>([]);
const pickedIds = ref<string[]>([]);

function addEmptyModelRow() {
  const seq = form.models.length + 1;
  form.models.push({
    modelId: '',
    name: `${t('model.list.add')} ${seq}`,
    model_type: isImageWorker.value ? 'image' : 'chat',
  });
}

function removeModelRow(index: number) {
  form.models.splice(index, 1);
}

function togglePick(modelId: string) {
  pickedIds.value = pickedIds.value.includes(modelId)
    ? pickedIds.value.filter(id => id !== modelId)
    : [...pickedIds.value, modelId];
}

/** 拉取模型：未保存用表单凭证，已保存且 Key 为占位符时用服务商凭证 */
async function handleFetchIntoForm() {
  if (!form.apiHost) { ElMessage.warning(t('provider.form.testWarningHost')); return; }
  if (!isEditing.value && !form.apiKey) { ElMessage.warning(t('provider.form.testWarningKey')); return; }
  isFetchingModels.value = true;
  try {
    const list = (isEditing.value && form.apiKey === API_KEY_PLACEHOLDER && props.providerData)
      ? await providerStore.fetchModelsForProvider(props.providerData.id, form.use_proxy)
      : await providerStore.fetchExternalModels({ apiHost: form.apiHost, apiKey: form.apiKey }, form.use_proxy, form.worker_type);
    fetchedModels.value = list;
    const existing = new Set(form.models.map(m => m.modelId));
    pickedIds.value = list.filter(m => !existing.has(m.modelId)).map(m => m.modelId);
    fetchPickerVisible.value = true;
  } catch (error: unknown) {
    if (isAxiosError(error)) ElMessage.error(error?.response?.data?.detail || t('model.fetchFailed'));
    else ElMessage.error(t('model.fetchFailed'));
  } finally {
    isFetchingModels.value = false;
  }
}

function applyFetchedModels() {
  const chosen = fetchedModels.value.filter(m => pickedIds.value.includes(m.modelId));
  const byId = new Map(form.models.map(m => [m.modelId, m]));
  for (const m of chosen) {
    byId.set(m.modelId, { modelId: m.modelId, name: m.name || m.modelId, model_type: m.model_type || 'chat' });
  }
  form.models = [...byId.values()];
  fetchPickerVisible.value = false;
}

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('provider.form.namePlaceholder'), trigger: 'blur' }],
  apiHost: [{ required: true, message: t('provider.form.apiHostPlaceholder'), trigger: 'blur' }],
  apiKey: [{
    validator: (_rule: any, value: string, callback: any) => {
      if (!isEditing.value && !value) callback(new Error(t('provider.form.apiKeyPlaceholder')));
      else if (isEditing.value && value === API_KEY_PLACEHOLDER) callback();
      else if (!value) callback(new Error(t('provider.form.apiKeyPlaceholder')));
      else callback();
    }, trigger: 'blur',
  }]
}));

watch(() => props.visible, (val) => {
  if (val) {
    showKey.value = false;
    if (props.providerData) {
      form.name = props.providerData.name;
      form.apiHost = props.providerData.apiHost;
      form.apiKey = API_KEY_PLACEHOLDER;
      form.worker_type = props.providerData.worker_type;
      form.use_proxy = props.providerData.use_proxy;
      form.models = (props.providerData.models || []).map(m => ({
        modelId: m.modelId,
        name: m.name || m.modelId,
        model_type: m.model_type || 'chat',
      }));
    } else {
      formRef.value?.resetFields();
      Object.assign(form, { name: '', apiHost: '', apiKey: '', worker_type: 'openai', use_proxy: false, models: [] });
    }
  }
});

const querySearchProviders = (queryString: string, cb: (results: AutocompleteSuggestion[]) => void) => {
  const allProviders = systemConfigStore.defaultProviders;
  const results = queryString
    ? allProviders.filter(p => p.name.toLowerCase().includes(queryString.toLowerCase()))
    : allProviders;
  cb(results.map(p => ({ value: p.name })));
};

const handleProviderSelect = (item: Record<string, any>) => {
  const selected = systemConfigStore.defaultProviders.find(p => p.name === item.value);
  if (selected) {
    form.apiHost = selected.apiHost;
    form.worker_type = selected.worker_type;
  }
};

const handleTestConnection = async () => {
  if (!form.apiHost) { ElMessage.warning(t('provider.form.testWarningHost')); return; }
  isTesting.value = true;
  try {
    let res;
    if (isEditing.value && form.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      res = await providerStore.testConnectionForProvider(props.providerData.id, form.apiHost, form.use_proxy);
    } else {
      if (!form.apiKey) { ElMessage.warning(t('provider.form.testWarningKey')); isTesting.value = false; return; }
      res = await providerStore.testConnection({ apiHost: form.apiHost, apiKey: form.apiKey }, form.use_proxy, form.worker_type);
    }
    const msg = res.status === 'success'
      ? t('provider.form.testSuccess')
      : (localizeProviderTestMessage(res.code) || res.message || t('provider.form.testFailed'));
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: msg });
  } catch (error: unknown) {
    if (isAxiosError(error)) ElMessage.error(error?.response?.data?.detail || t('provider.form.testFailed'));
    else ElMessage.error(t('provider.form.testFailed'));
  } finally { isTesting.value = false; }
};

const submitForm = async () => {
  await formRef.value?.validate(async (valid) => {
    if (valid) {
      isSubmitting.value = true;
      try {
        if (isEditing.value && props.providerData) {
          const updateData: AIProviderUpdate = {
            name: form.name, apiHost: form.apiHost, worker_type: form.worker_type, use_proxy: form.use_proxy
          };
          if (form.apiKey !== API_KEY_PLACEHOLDER) updateData.apiKey = form.apiKey;
          await providerStore.updateProvider(props.providerData.id, updateData);

          // 模型清单差分同步：新增 / 更新 / 删除
          const originals = props.providerData.models || [];
          const originalMap = new Map(originals.map(m => [m.modelId, m]));
          const nextIds = new Set(form.models.map(m => m.modelId).filter(Boolean));

          for (const modelId of originalMap.keys()) {
            if (!nextIds.has(modelId)) {
              const target = originalMap.get(modelId);
              if (target) await providerStore.removeModel(target.id);
            }
          }
          for (const row of form.models) {
            if (!row.modelId.trim()) continue;
            const existing = originalMap.get(row.modelId);
            if (!existing) {
              await providerStore.addModel({
                providerId: props.providerData.id,
                modelId: row.modelId,
                name: row.name || row.modelId,
                model_type: row.model_type || 'chat',
              });
            } else if (existing.name !== row.name) {
              await providerStore.updateModel(existing.id, { name: row.name });
            }
          }

          ElMessage.success(t('provider.form.updateSuccess'));
        } else {
          await providerStore.addProviderWithModels({
            name: form.name, apiHost: form.apiHost, apiKey: form.apiKey,
            worker_type: form.worker_type, use_proxy: form.use_proxy,
            models: form.models.filter(m => m.modelId.trim()),
          });
          ElMessage.success(t('provider.form.createSuccess'));
        }
        emit('submitted');
        internalVisible.value = false;
      } catch { ElMessage.error(t('common.error.operationFailed')); }
      finally { isSubmitting.value = false; }
    }
  });
};
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; max-height: 85vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-body { flex: 1; overflow-y: auto; padding: 4px 16px 8px; -webkit-overflow-scrolling: touch; }
.sheet-form { padding: 0; }
.field-item { margin-bottom: 12px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.field-hint { font-size: 12px; line-height: 1.5; color: var(--el-text-color-secondary); margin-top: 4px; }
.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.password-row { position: relative; display: flex; align-items: center; }
.password-row .native-input { padding-right: 40px; }
.toggle-key { position: absolute; right: 8px; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; background: transparent; color: var(--el-text-color-secondary); cursor: pointer; border-radius: 6px; }
.switch-row { display: flex; align-items: center; justify-content: space-between; }
.hint-text { display: flex; align-items: center; gap: 4px; margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.test-btn { display: flex; align-items: center; justify-content: center; width: 100%; height: 40px; margin-top: 8px; font-size: 14px; font-weight: 500; color: var(--el-color-primary); background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-5); border-radius: 10px; cursor: pointer; transition: background 0.15s; }
.test-btn:active { background: var(--el-color-primary-light-7); }

/* 表单内模型清单 */
.model-rows { display: flex; flex-direction: column; gap: 6px; }
.model-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; background: var(--el-fill-color-light); }
.model-row-main { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.model-row-name { font-size: 13px; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-row-id { font-size: 11px; color: var(--el-text-color-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-remove { flex-shrink: 0; width: 24px; height: 24px; border: none; border-radius: 50%; background: transparent; color: var(--el-text-color-secondary); display: inline-flex; align-items: center; justify-content: center; }
.model-actions { display: flex; gap: 8px; margin-top: 8px; }
.mini-btn { flex: 1; height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; border: 1px dashed var(--el-border-color); border-radius: 8px; background: transparent; font-size: 13px; color: var(--el-color-primary); }
.mini-btn:disabled { opacity: 0.5; }
.model-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.model-chip { display: inline-flex; flex-direction: column; align-items: flex-start; gap: 2px; max-width: 100%; padding: 8px 12px; border-radius: 18px; border: 1.5px solid transparent; background: var(--color-background-soft); font-size: 13px; }
.model-chip.selected { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.chip-name { font-size: 13px; font-weight: 600; }
.chip-id { font-size: 11px; opacity: 0.7; word-break: break-all; }
.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; cursor: pointer; transition: opacity 0.2s, transform 0.1s; }
.footer-btn-cancel { color: var(--el-text-color-primary); background: var(--el-fill-color-light); }
.footer-btn-confirm { color: #fff; background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); box-shadow: 0 4px 12px rgba(64,158,255,0.3); }
.footer-btn-confirm:disabled { opacity: 0.5; }
.footer-btn:active { transform: scale(0.98); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

@media (prefers-color-scheme: dark) {
  .sheet-handle { background: rgba(255,255,255,0.2); }
  .sheet-footer { border-top-color: rgba(255,255,255,0.08); }
  .native-input { box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset; }
  .native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
}
</style>
