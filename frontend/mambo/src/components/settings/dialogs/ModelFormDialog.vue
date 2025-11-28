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

      <el-divider>元配置 (Meta Config)</el-divider>

      <!-- 元配置信息 -->
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
      <el-form-item label="上下文长度">
        <el-input-number
          v-model="modelForm.meta_config.context_length"
          :min="0"
          :controls="false"
          placeholder="例如: 128000"
          style="width: 100%"
        />
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

    <div v-if="!isEditing" class="add-model-actions">
      <el-button @click="emit('fetch-models')" :loading="isFetching">
        <el-icon><Download /></el-icon>从API获取并选择
      </el-button>
    </div>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="submitForm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Download } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import type { AIModel, AIModelCreate, AIModelMetaConfig, AIModelUpdate } from '@/api/types';
import {
  tokenizerOptions,
  inputModalitiesOptions,
  outputModalitiesOptions,
} from '@/constants/metaConfigOptions';

interface ModelFormData {
  name: string;
  modelId: string;
  meta_config: AIModelMetaConfig;
}

const props = defineProps<{
  visible: boolean;
  modelData: AIModel | null;
  providerId: string | null;
  isFetching: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'submitted'): void;
  (e: 'fetch-models'): void;
}>();

const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const internalVisible = ref(false);
const modelFormRef = ref<FormInstance>();

const getInitialMetaConfig = (): AIModelMetaConfig => ({
  context_length: null,
  max_output_tokens: null,
  tokenizer: null,
  input_modalities: [],
  output_modalities: [],
  supported_parameters: [],
});

const modelForm = reactive<ModelFormData>({
  name: '',
  modelId: '',
  meta_config: getInitialMetaConfig(),
});

const isEditing = computed(() => !!props.modelData);

const modelFormRules = reactive<FormRules<Partial<ModelFormData>>>({
  name: [{ required: true, message: '请输入模型显示名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
});

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    modelFormRef.value?.resetFields();
    if (props.modelData) { // 编辑
      modelForm.name = props.modelData.name;
      modelForm.modelId = props.modelData.modelId;
      // 深拷贝 meta_config，防止直接修改 prop
      modelForm.meta_config = JSON.parse(JSON.stringify(props.modelData.meta_config || getInitialMetaConfig()));
    } else { // 新增
      modelForm.name = '';
      modelForm.modelId = '';
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
    return {
      ...config,
      context_length: config.context_length || null,
      max_output_tokens: config.max_output_tokens || null,
    };
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
            meta_config: sanitizedMetaConfig
          };
          await providerStore.updateModel(props.modelData.id, updateData);
          ElMessage.success('更新模型成功！');
        } else if (props.providerId) {
          const createData: AIModelCreate = {
            name: modelForm.name,
            modelId: modelForm.modelId,
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
.add-model-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 20px;
}
</style>
