<template>
  <el-dialog v-model="internalVisible" title="新建会话" width="400px" @close="handleClose">
    <el-form ref="formRef" :model="newChatForm" :rules="formRules" label-width="80px">
      <el-form-item label="会话名称" prop="name">
        <el-input v-model="newChatForm.name" placeholder="请输入会话名称" />
      </el-form-item>
      <el-form-item label="选择模型" prop="modelId">
        <el-select v-model="newChatForm.modelId" placeholder="请选择一个AI模型" style="width: 100%;">
          <el-option-group v-for="group in groupedModels" :key="group.id" :label="group.label">
            <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
          </el-option-group>
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleCreateChat">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import type { AIProviderWithModels } from '@/api/types';

// 定义表单的数据结构
interface NewChatForm {
  name: string;
  modelId: string;
}

const props = defineProps<{
  visible: boolean;
  // 外部传入的分组模型列表
  groupedModels: { id: string, label: string; options: { id: string; name: string }[] }[];
  // 外部传入的全局默认模型ID
  defaultModelId: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', formData: NewChatForm): void;
}>();

const internalVisible = ref(false);
const formRef = ref<FormInstance>();
const newChatForm = reactive<NewChatForm>({ name: '', modelId: '' });
const formRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入会话名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请选择一个模型', trigger: 'change' }],
});

// 监听外部 visible 属性的变化以控制内部状态
watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    // 每次打开时，重置表单为默认值
    newChatForm.name = '新的会话';
    newChatForm.modelId = props.defaultModelId || '';
    formRef.value?.clearValidate();
  }
});

const handleClose = () => {
  emit('update:visible', false);
};

const handleCreateChat = async () => {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (valid) {
      emit('confirm', { ...newChatForm });
      handleClose();
    }
  });
};
</script>
