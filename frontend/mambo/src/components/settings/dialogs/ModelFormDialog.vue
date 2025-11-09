<template>
  <el-dialog
    v-model="internalVisible"
    :title="isEditing ? '编辑 AI 模型' : '新增 AI 模型'"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form ref="modelFormRef" :model="modelForm" :rules="modelFormRules" label-width="120px">
      <el-form-item label="模型 ID" prop="modelId">
        <el-input v-model.trim="modelForm.modelId" placeholder="例如：gpt-4o" :disabled="isEditing" />
      </el-form-item>
      <el-form-item label="模型显示名称" prop="name">
        <el-input v-model.trim="modelForm.name" placeholder="例如：GPT-4o" />
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
import type { AIModel, AIModelCreate } from '@/api/types';

interface ModelFormData {
  name: string;
  modelId: string;
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
const internalVisible = ref(false);
const modelFormRef = ref<FormInstance>();
const modelForm = reactive<ModelFormData>({ name: '', modelId: '' });

const isEditing = computed(() => !!props.modelData);

const modelFormRules = reactive<FormRules<ModelFormData>>({
  name: [{ required: true, message: '请输入模型显示名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
});

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    if (props.modelData) { // 编辑
      modelForm.name = props.modelData.name;
      modelForm.modelId = props.modelData.modelId;
    } else { // 新增
      modelFormRef.value?.resetFields();
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

async function submitForm() {
  if (!modelFormRef.value) return;
  await modelFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        if (isEditing.value && props.modelData) {
          await providerStore.updateModel(props.modelData.id, { name: modelForm.name });
          ElMessage.success('更新模型成功！');
        } else if (props.providerId) {
          const createData: AIModelCreate = { ...modelForm, providerId: props.providerId };
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
