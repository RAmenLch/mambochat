<template>
  <el-dialog
    v-model="internalVisible"
    :title="isEditing ? '编辑 AI 模型' : '新增 AI 模型'"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form ref="modelFormRef" :model="modelForm" :rules="modelFormRules" label-width="140px">
      <!-- 基本信息 -->
      <el-form-item label="模型 ID" prop="modelId">
        <el-input v-model.trim="modelForm.modelId" placeholder="例如：gpt-4o" :disabled="isEditing" />
      </el-form-item>
      <el-form-item label="模型显示名称" prop="name">
        <el-input v-model.trim="modelForm.name" placeholder="例如：GPT-4o" />
      </el-form-item>
      <el-form-item label="模型类型" prop="model_type">
        <el-radio-group v-model="modelForm.model_type">
          <el-radio-button value="chat">对话模型</el-radio-button>
          <el-radio-button value="embedding">向量模型</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-divider>元配置 (Meta Config)</el-divider>

      <!-- 通用配置 -->
      <el-form-item label="上下文长度">
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
        <el-form-item label="分词器 (Tokenizer)">
          <el-select
            v-model="modelForm.meta_config.tokenizer"
            placeholder="请选择分词器"
            clearable
            style="width: 100%"
          >
            <el-option v-for="item in tokenizerOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="最大输出Token数">
          <el-input-number
            v-model="modelForm.meta_config.max_output_tokens"
            :min="0"
            :controls="false"
            placeholder="例如: 4096"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="输入模态">
          <el-select
            v-model="modelForm.meta_config.input_modalities"
            multiple
            placeholder="请选择支持的输入模态"
            clearable
            style="width: 100%"
          >
            <el-option v-for="item in inputModalitiesOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="输出模态">
          <el-select
            v-model="modelForm.meta_config.output_modalities"
            multiple
            placeholder="请选择支持的输出模态"
            clearable
            style="width: 100%"
          >
            <el-option v-for="item in outputModalitiesOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
      </template>

      <!-- Embedding 模型专用配置 -->
      <template v-if="isEmbeddingModel">
        <el-form-item label="向量维度">
          <el-input-number
            v-model="modelForm.meta_config.embedding_dimension"
            :min="1"
            :controls="false"
            placeholder="例如: 1536"
            style="width: 100%"
          />
        </el-form-item>
      </template>

      <!-- 通用配置 -->
      <el-form-item label="支持的参数">
        <el-select
          v-model="modelForm.meta_config.supported_parameters"
          multiple
          filterable
          placeholder="请选择支持的参数"
          clearable
          style="width: 100%"
        >
          <el-option v-for="item in systemConfigStore.parameterOptions" :key="item.key" :label="item.label" :value="item.key" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="submitForm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import type { AIModel, AIModelCreate, AIModelMetaConfig, AIModelUpdate, ModelType } from '@/api/types';
import {
  tokenizerOptions,
  inputModalitiesOptions,
  outputModalitiesOptions,
} from '@/constants/metaConfigOptions';

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

const modelFormRules = reactive<FormRules<Partial<ModelFormData>>>({
  name: [{ required: true, message: '请输入模型显示名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
  model_type: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
});

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
          ElMessage.success('更新模型成功！');
        } else if (props.providerId) {
          const createData: AIModelCreate = {
            name: modelForm.name,
            modelId: modelForm.modelId,
            model_type: modelForm.model_type,
            providerId: props.providerId,
            meta_config: sanitizedMetaConfig
          };
          await providerStore.addModel(createData);
          ElMessage.success('新增模型成功！');
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
/* 样式可以保持不变，以备将来使用，或根据需要删除 */
</style>
