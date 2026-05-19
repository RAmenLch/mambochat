<template>
  <el-dialog
    v-model="internalVisible"
    :title="isEditing ? t('model.form.editTitle') : t('model.form.addTitle')"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form ref="modelFormRef" :model="modelForm" :rules="modelFormRules" label-width="140px">
      <!-- 基本信息 -->
      <el-form-item :label="t('model.form.id')" prop="modelId">
        <el-input v-model.trim="modelForm.modelId" :placeholder="t('model.form.idPlaceholder')" :disabled="isEditing" />
      </el-form-item>
      <el-form-item :label="t('model.form.name')" prop="name">
        <el-input v-model.trim="modelForm.name" :placeholder="t('model.form.namePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('model.form.type')" prop="model_type">
        <el-radio-group v-model="modelForm.model_type">
          <el-radio-button value="chat">{{ t('model.form.typeChat') }}</el-radio-button>
          <el-radio-button value="embedding">{{ t('model.form.typeEmbedding') }}</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-divider>{{ t('model.form.metaConfig') }}</el-divider>

      <!-- 通用配置 -->
      <el-form-item :label="t('model.form.contextLength')">
        <el-input-number
          v-model="modelForm.meta_config.context_length"
          :min="0"
          :controls="false"
          placeholder="例如: 128000"
          style="width: 100%"
        />
      </el-form-item>

      <!-- Chat 模型专用配置 -->
      <template v-if="isChatModel">
<!--        <el-form-item label="分词器 (Tokenizer)">-->
<!--          <el-select-->
<!--            v-model="modelForm.meta_config.tokenizer"-->
<!--            placeholder="请选择分词器"-->
<!--            clearable-->
<!--            style="width: 100%"-->
<!--          >-->
<!--            <el-option v-for="item in tokenizerOptions" :key="item" :label="item" :value="item" />-->
<!--          </el-select>-->
<!--        </el-form-item>-->
        <el-form-item :label="t('model.form.maxOutput')">
          <el-input-number
            v-model="modelForm.meta_config.max_output_tokens"
            :min="0"
            :controls="false"
            placeholder="例如: 4096"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('model.form.inputModalities')">
          <el-select
            v-model="modelForm.meta_config.input_modalities"
            multiple
            placeholder="Select input modalities"
            clearable
            style="width: 100%"
          >
            <el-option v-for="item in inputModalitiesOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('model.form.outputModalities')">
          <el-select
            v-model="modelForm.meta_config.output_modalities"
            multiple
            placeholder="Select output modalities"
            clearable
            style="width: 100%"
          >
            <el-option v-for="item in outputModalitiesOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
      </template>

      <!-- Embedding 模型专用配置 -->
      <template v-if="isEmbeddingModel">
        <el-form-item :label="t('model.form.embeddingDimension')">
          <el-select
            v-model="modelForm.meta_config.embedding_dimension"
            filterable
            allow-create
            default-first-option
            :placeholder="t('model.form.embeddingDimensionPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="dim in embeddingDimensionOptions" :key="dim" :label="String(dim)" :value="dim" />
          </el-select>
        </el-form-item>
      </template>

      <!-- 通用配置 -->
      <el-form-item :label="t('model.form.maxRetries')">
        <div class="slider-row">
          <el-slider
            :model-value="modelForm.meta_config.max_retries ?? 0"
            @update:model-value="modelForm.meta_config!.max_retries = Number($event)"
            :min="0"
            :max="20"
            :step="1"
            :show-tooltip="false"
            style="flex: 1; margin-right: 12px;"
          />
          <span v-if="(modelForm.meta_config.max_retries ?? 0) === 0" class="slider-tag">{{ t('model.form.useGlobal') }}</span>
          <span v-else class="slider-tag slider-tag--value">{{ modelForm.meta_config.max_retries }}</span>
        </div>
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>{{ t('model.form.timeout') }}</span>
          <el-tooltip :content="t('model.form.timeoutTip')" placement="top">
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <div class="slider-row">
          <el-input-number
            :model-value="modelForm.meta_config.timeout ?? null"
            @update:model-value="(val: number | null | undefined) => (modelForm.meta_config!.timeout = val ?? null)"
            :min="10"
            :max="600"
            :step="10"
            :controls="false"
            placeholder="60"
            style="flex: 1; margin-right: 12px;"
          />
          <span v-if="!modelForm.meta_config.timeout" class="slider-tag">{{ t('model.form.useGlobal') }}</span>
          <span v-else class="slider-tag slider-tag--value">{{ modelForm.meta_config.timeout }}s</span>
        </div>
      </el-form-item>

      <!-- 通用配置 -->
      <el-form-item :label="t('model.form.supportedParams')">
        <el-select
          v-model="modelForm.meta_config.supported_parameters"
          multiple
          filterable
          placeholder="Select supported parameters"
          clearable
          style="width: 100%"
        >
          <el-option v-for="item in systemConfigStore.parameterOptions" :key="item.key" :label="item.label" :value="item.key" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitForm">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { QuestionFilled } from '@element-plus/icons-vue';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import type { AIModel, AIModelCreate, AIModelMetaConfig, AIModelUpdate, ModelType } from '@/api/types';
import {
  inputModalitiesOptions,
  outputModalitiesOptions,
} from '@/constants/metaConfigOptions';

const embeddingDimensionOptions = [384, 768, 1024, 1536, 2560, 3072, 4096];

interface ModelFormData {
  name: string;
  modelId: string;
  model_type: ModelType;
  meta_config: AIModelMetaConfig;
}

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
const systemConfigStore = useSystemConfigStore();
const internalVisible = ref(false);
const modelFormRef = ref<FormInstance>();

const getInitialMetaConfig = (): AIModelMetaConfig => ({
  context_length: null,
  max_output_tokens: null,
  embedding_dimension: null,
  tokenizer: null,
  input_modalities: [],
  output_modalities: [],
  supported_parameters: [],
  max_retries: 0,
  timeout: null,
});

const modelForm = reactive<ModelFormData>({
  name: '',
  modelId: '',
  model_type: 'chat',
  meta_config: getInitialMetaConfig(),
});

const isEditing = computed(() => !!props.modelData);
const isChatModel = computed(() => modelForm.model_type === 'chat');
const isEmbeddingModel = computed(() => modelForm.model_type === 'embedding');

const modelFormRules = computed<FormRules<Partial<ModelFormData>>>(() => ({
  name: [{ required: true, message: t('model.form.namePlaceholder'), trigger: 'blur' }],
  modelId: [{ required: true, message: t('model.form.idPlaceholder'), trigger: 'blur' }],
  model_type: [{ required: true, message: t('model.form.type'), trigger: 'change' }],
}));

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    modelFormRef.value?.resetFields();
    if (props.modelData) { // 编辑
      modelForm.name = props.modelData.name;
      modelForm.modelId = props.modelData.modelId;
      modelForm.model_type = props.modelData.model_type || 'chat';
      // 深拷贝 meta_config，防止直接修改 prop
      modelForm.meta_config = JSON.parse(JSON.stringify(props.modelData.meta_config || getInitialMetaConfig()));
    } else { // 新增
      modelForm.name = '';
      modelForm.modelId = '';
      modelForm.model_type = 'chat';
      modelForm.meta_config = getInitialMetaConfig();
    }
  }
});

watch(() => modelForm.modelId, (newId, oldId) => {
  if (!modelForm.name || modelForm.name === oldId) {
    modelForm.name = newId;
  }
});

function handleClose() {
  emit('update:visible', false);
}

function getSanitizedMetaConfig(): AIModelMetaConfig {
    const config = modelForm.meta_config;
    const baseConfig: AIModelMetaConfig = {
      context_length: config.context_length || null,
      supported_parameters: config.supported_parameters || [],
      max_retries: config.max_retries || 0,
      timeout: config.timeout || null,
    };

    if (isChatModel.value) {
      return {
        ...baseConfig,
        max_output_tokens: config.max_output_tokens || null,
        tokenizer: config.tokenizer || null,
        input_modalities: config.input_modalities || [],
        output_modalities: config.output_modalities || [],
        embedding_dimension: null,
      };
    } else {
      // Embedding 模型清除不相关的 Chat 配置
      return {
        ...baseConfig,
        embedding_dimension: config.embedding_dimension || null,
        max_output_tokens: null,
        tokenizer: null,
        input_modalities: [],
        output_modalities: [],
      };
    }
}

async function submitForm() {
  if (!modelFormRef.value) return;
  await modelFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const sanitizedMetaConfig = getSanitizedMetaConfig();

        if (isEditing.value && props.modelData) {
          const updateData: AIModelUpdate = {
            name: modelForm.name,
            model_type: modelForm.model_type,
            meta_config: sanitizedMetaConfig
          };
          await providerStore.updateModel(props.modelData.id, updateData);
          ElMessage.success(t('model.form.updateSuccess'));
        } else if (props.providerId) {
          const createData: AIModelCreate = {
            name: modelForm.name,
            modelId: modelForm.modelId,
            model_type: modelForm.model_type,
            providerId: props.providerId,
            meta_config: sanitizedMetaConfig
          };
          await providerStore.addModel(createData);
          ElMessage.success(t('model.form.createSuccess'));
        }
        emit('submitted');
        handleClose();
      } catch (error) {
        console.error('Failed to submit model form:', error);
      }
    }
  });
}
</script>

<style scoped>
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
.label-icon { margin-left: 4px; color: var(--el-text-color-secondary); cursor: help; }
</style>
