<!-- MobileModelFormDialog.vue — 移动端模型表单（Bottom Sheet） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="internalVisible" class="sheet-overlay" @click="internalVisible = false">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>
          <div class="sheet-header">
            <span class="sheet-title">{{ isEditing ? t('model.form.editTitle') : t('model.form.addTitle') }}</span>
            <button class="sheet-close" @click="internalVisible = false">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="sheet-form">
              <div class="field-item">
                <label class="field-label">{{ t('model.form.id') }}</label>
                <input
                  v-model="form.modelId"
                  class="native-input"
                  :placeholder="t('model.form.idPlaceholder')"
                  :disabled="isEditing"
                />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('model.form.name') }}</label>
                <input
                  v-model="form.name"
                  class="native-input"
                  :placeholder="t('model.form.namePlaceholder')"
                />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('model.form.type') }}</label>
                <el-radio-group v-model="form.model_type">
                  <el-radio-button value="chat">{{ t('model.form.typeChat') }}</el-radio-button>
                  <el-radio-button value="embedding">{{ t('model.form.typeEmbedding') }}</el-radio-button>
                </el-radio-group>
              </div>

              <div class="sheet-divider">{{ t('model.form.metaConfig') }}</div>

              <div class="field-item">
                <label class="field-label">{{ t('model.form.contextLength') }}</label>
                <el-input-number v-model="form.meta_config.context_length" :min="0" controls-position="right" style="width: 100%" />
              </div>

              <template v-if="form.model_type === 'chat'">
                <div class="field-item">
                  <label class="field-label">{{ t('model.form.maxOutput') }}</label>
                  <el-input-number v-model="form.meta_config.max_output_tokens" :min="0" controls-position="right" style="width: 100%" />
                </div>
                <div class="field-item">
                  <label class="field-label">{{ t('model.form.inputModalities') }}</label>
                  <el-select v-model="form.meta_config.input_modalities" multiple style="width: 100%" popper-class="mobile-popper">
                    <el-option v-for="item in inputOpts" :key="item" :label="item" :value="item" />
                  </el-select>
                </div>
              </template>

              <template v-else>
                <div class="field-item">
                  <label class="field-label">{{ t('model.form.embeddingDimension') }}</label>
                  <el-input-number v-model="form.meta_config.embedding_dimension" :min="1" controls-position="right" style="width: 100%" />
                </div>
              </template>

              <div class="field-item">
                <label class="field-label">{{ t('model.form.maxRetries') }}</label>
                <el-input-number v-model="form.meta_config.max_retries" :min="0" :max="20" controls-position="right" style="width: 100%" />
              </div>
            </el-form>
          </div>

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
import { Close } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import type { AIModel, AIModelMetaConfig, AIModelCreate, AIModelUpdate, ModelType } from '@/api/types';
import { inputModalitiesOptions } from '@/constants/metaConfigOptions';

const props = defineProps<{
  visible: boolean;
  modelData: AIModel | null;
  providerId: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'submitted'): void;
}>();

const { t } = useI18n();
const providerStore = useProviderStore();

const formRef = ref<FormInstance>();
const isSubmitting = ref(false);
const inputOpts = inputModalitiesOptions;

const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const isEditing = computed(() => !!props.modelData);

const defaultMeta = (): AIModelMetaConfig => ({
  context_length: null, max_output_tokens: null, embedding_dimension: null,
  tokenizer: null, input_modalities: [], output_modalities: [],
  supported_parameters: [], max_retries: 0,
});

const form = reactive({
  name: '', modelId: '', model_type: 'chat' as ModelType,
  meta_config: defaultMeta()
});

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('model.form.namePlaceholder'), trigger: 'blur' }],
  modelId: [{ required: true, message: t('model.form.idPlaceholder'), trigger: 'blur' }],
}));

watch(() => props.visible, (val) => {
  if (val) {
    if (props.modelData) {
      form.name = props.modelData.name;
      form.modelId = props.modelData.modelId;
      form.model_type = props.modelData.model_type || 'chat';
      form.meta_config = props.modelData.meta_config
        ? JSON.parse(JSON.stringify(props.modelData.meta_config))
        : defaultMeta();
    } else {
      formRef.value?.resetFields();
      Object.assign(form, { name: '', modelId: '', model_type: 'chat', meta_config: defaultMeta() });
    }
  }
});

const submitForm = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSubmitting.value = true;
      try {
        const cleanMeta = { ...form.meta_config };
        if (form.model_type === 'chat') { cleanMeta.embedding_dimension = null; }
        else { cleanMeta.max_output_tokens = null; cleanMeta.input_modalities = []; cleanMeta.output_modalities = []; }

        if (isEditing.value && props.modelData) {
          await providerStore.updateModel(props.modelData.id, {
            name: form.name, model_type: form.model_type, meta_config: cleanMeta
          });
          ElMessage.success(t('model.form.updateSuccess'));
        } else if (props.providerId) {
          await providerStore.addModel({
            name: form.name, modelId: form.modelId, model_type: form.model_type,
            providerId: props.providerId, meta_config: cleanMeta
          });
          ElMessage.success(t('model.form.createSuccess'));
        }
        emit('submitted');
        internalVisible.value = false;
      } catch {
        ElMessage.error(t('common.error.operationFailed'));
      } finally { isSubmitting.value = false; }
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
.sheet-divider { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); padding: 8px 0 4px; }
.sheet-form { padding: 0; }
.field-item { margin-bottom: 12px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.native-input:disabled { opacity: 0.5; background: var(--el-fill-color-light); }
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
