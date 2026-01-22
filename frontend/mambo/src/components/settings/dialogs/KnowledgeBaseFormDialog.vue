<!-- frontend/mambo/src/components/settings/dialogs/KnowledgeBaseFormDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    title="新建知识库"
    width="500px"
    @update:model-value="val => emit('update:visible', val)"
    @close="handleClose"
    @open="handleOpen"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="知识库名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="请输入知识库名称"
          ref="nameInputRef"
          @keyup.enter="handleConfirm"
        />
      </el-form-item>

      <el-form-item label="嵌入模型 (Embedding Model)" prop="embeddingModelId">
        <el-select
          v-model="form.embeddingModelId"
          placeholder="请选择嵌入模型"
          style="width: 100%"
        >
          <template v-for="group in embeddingModelOptions" :key="group.label">
            <el-option-group :label="group.label">
              <el-option
                v-for="item in group.options"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-option-group>
          </template>
        </el-select>
      </el-form-item>

      <el-form-item prop="embeddingRateLimit">
        <template #label>
          <span>嵌入频率限制 (秒)</span>
          <el-tooltip content="每次 Embedding 请求后的冷却时间，用于防止触发 API 速率限制" placement="top">
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <el-input-number
          v-model="form.embeddingRateLimit"
          :min="0"
          :step="0.1"
          :precision="2"
          style="width: 100%"
          placeholder="0.0"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleConfirm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue';
import { type FormInstance, type FormRules, ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';

// --- Types ---

export interface ModelOption {
  label: string;
  value: string;
}

export interface ModelGroup {
  label: string;
  options: ModelOption[];
}

export interface KBConfirmPayload {
  name: string;
  embeddingModelId: string;
  embeddingRateLimit: number;
}

// --- Props & Emits ---

const props = defineProps<{
  visible: boolean;
  embeddingModelOptions: ModelGroup[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', payload: KBConfirmPayload): void;
}>();

// --- State ---

const formRef = ref<FormInstance>();
const nameInputRef = ref<HTMLInputElement>();

const form = reactive({
  name: '',
  embeddingModelId: '',
  embeddingRateLimit: 0,
});

const rules = reactive<FormRules>({
  name: [{ required: true, message: '知识库名称不能为空', trigger: 'blur' }],
  embeddingModelId: [{ required: true, message: '请选择嵌入模型', trigger: 'change' }],
});

// --- Handlers ---

const handleOpen = () => {
  form.name = '';
  form.embeddingRateLimit = 0;

  // 尝试自动选中第一个可用的模型
  if (props.embeddingModelOptions.length > 0 && props.embeddingModelOptions[0].options.length > 0) {
    form.embeddingModelId = props.embeddingModelOptions[0].options[0].value;
  } else {
    form.embeddingModelId = '';
  }

  nextTick(() => {
    formRef.value?.clearValidate();
    nameInputRef.value?.focus();
  });
};

const handleClose = () => {
  emit('update:visible', false);
};

const handleConfirm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      emit('confirm', {
        name: form.name.trim(),
        embeddingModelId: form.embeddingModelId,
        embeddingRateLimit: form.embeddingRateLimit,
      });
      handleClose();
    } else {
      if (!form.name.trim()) {
        ElMessage.warning('请检查输入项');
      }
    }
  });
};
</script>

<style scoped>
.label-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}
</style>
