<!-- frontend/mambo/src/mobile/components/settings/dialogs/MobileModelFormDialog.vue -->
<template>
  <el-drawer
    v-model="internalVisible"
    :title="isEditing ? t('model.form.editTitle') : t('model.form.addTitle')"
    direction="rtl"
    size="85%"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="mobile-form"
    >
      <el-form-item :label="t('model.form.id')" prop="modelId">
        <el-input
          v-model="form.modelId"
          :placeholder="t('model.form.idPlaceholder')"
          :disabled="isEditing"
        />
      </el-form-item>

      <el-form-item :label="t('model.form.name')" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="t('model.form.namePlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('model.form.type')" prop="model_type">
        <el-radio-group v-model="form.model_type">
          <el-radio-button value="chat">{{ t('model.form.typeChat') }}</el-radio-button>
          <el-radio-button value="embedding">{{ t('model.form.typeEmbedding') }}</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-divider content-position="left">{{ t('model.form.metaConfig') }}</el-divider>

      <el-form-item :label="t('model.form.contextLength')">
        <el-input-number
          v-model="form.meta_config.context_length"
          :min="0"
          controls-position="right"
          style="width: 100%;"
        />
      </el-form-item>

      <!-- Chat 模型专用配置 -->
      <template v-if="form.model_type === 'chat'">
        <el-form-item :label="t('model.form.maxOutput')">
          <el-input-number
            v-model="form.meta_config.max_output_tokens"
            :min="0"
            controls-position="right"
            style="width: 100%;"
          />
        </el-form-item>

        <el-form-item :label="t('model.form.inputModalities')">
          <el-select
            v-model="form.meta_config.input_modalities"
            multiple
            style="width: 100%;"
            :placeholder="t('model.form.inputModalities')"
          >
            <el-option v-for="item in inputOpts" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
      </template>

      <!-- Embedding 模型专用配置 -->
      <template v-else>
        <el-form-item :label="t('model.form.embeddingDimension')">
          <el-input-number
            v-model="form.meta_config.embedding_dimension"
            :min="1"
            controls-position="right"
            style="width: 100%;"
          />
        </el-form-item>
      </template>

      <!-- 通用配置: max_retries -->
      <el-form-item :label="t('model.form.maxRetries')">
        <div class="slider-row">
          <el-slider
            :model-value="form.meta_config.max_retries ?? 0"
            @update:model-value="form.meta_config!.max_retries = Number($event)"
            :min="0"
            :max="20"
            :step="1"
            :show-tooltip="false"
            style="flex: 1; margin-right: 12px;"
          />
          <span v-if="(form.meta_config.max_retries ?? 0) === 0" class="slider-tag">{{ t('model.form.useGlobal') }}</span>
          <span v-else class="slider-tag slider-tag--value">{{ form.meta_config.max_retries }}</span>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="internalVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitForm" :loading="isSubmitting">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
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

// 计算属性处理 v-model
const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const isEditing = computed(() => !!props.modelData);

// 默认 MetaConfig
const defaultMeta = (): AIModelMetaConfig => ({
  context_length: null,
  max_output_tokens: null,
  embedding_dimension: null,
  tokenizer: null,
  input_modalities: [],
  output_modalities: [],
  supported_parameters: [],
  max_retries: 0,
});

// 表单数据
const form = reactive({
  name: '',
  modelId: '',
  model_type: 'chat' as ModelType,
  meta_config: defaultMeta()
});

// 验证规则
const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('model.form.namePlaceholder'), trigger: 'blur' }],
  modelId: [{ required: true, message: t('model.form.idPlaceholder'), trigger: 'blur' }],
  model_type: [{ required: true, message: t('model.form.type'), trigger: 'change' }]
}));

// 监听 visible 变化，初始化表单
watch(() => props.visible, (val) => {
  if (val) {
    if (props.modelData) {
      // 编辑模式：填充数据
      form.name = props.modelData.name;
      form.modelId = props.modelData.modelId;
      form.model_type = props.modelData.model_type || 'chat';
      // 深拷贝 meta_config
      form.meta_config = props.modelData.meta_config
        ? JSON.parse(JSON.stringify(props.modelData.meta_config))
        : defaultMeta();
    } else {
      // 新增模式：重置表单
      formRef.value?.resetFields();
      Object.assign(form, {
        name: '',
        modelId: '',
        model_type: 'chat',
        meta_config: defaultMeta()
      });
    }
  }
});

// 提交表单
const submitForm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSubmitting.value = true;
      try {
        // 清理 meta_config (根据类型移除不相关字段)
        const cleanMeta = { ...form.meta_config };
        if (form.model_type === 'chat') {
          cleanMeta.embedding_dimension = null;
        } else {
          cleanMeta.max_output_tokens = null;
          cleanMeta.input_modalities = [];
          cleanMeta.output_modalities = [];
        }

        if (isEditing.value && props.modelData) {
          // 更新
          const updateData: AIModelUpdate = {
            name: form.name,
            model_type: form.model_type,
            meta_config: cleanMeta
          };
          await providerStore.updateModel(props.modelData.id, updateData);
          ElMessage.success(t('model.form.updateSuccess'));
        } else if (props.providerId) {
          // 新增
          const createData: AIModelCreate = {
            name: form.name,
            modelId: form.modelId,
            model_type: form.model_type,
            providerId: props.providerId,
            meta_config: cleanMeta
          };
          await providerStore.addModel(createData);
          ElMessage.success(t('model.form.createSuccess'));
        }

        emit('submitted');
        internalVisible.value = false;
      } catch (error) {
        ElMessage.error(t('common.error.operationFailed'));
        console.error(error);
      } finally {
        isSubmitting.value = false;
      }
    }
  });
};
</script>

<style scoped>
.mobile-form {
  padding: 0 10px;
}
.slider-row {
  display: flex;
  align-items: center;
  width: 100%;
}
.slider-tag {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.slider-tag--value {
  font-weight: 600;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
</style>
