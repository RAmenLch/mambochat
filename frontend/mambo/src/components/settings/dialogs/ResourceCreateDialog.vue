<!-- frontend/mambo/src/components/settings/dialogs/ResourceCreateDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="400px"
    @update:model-value="val => emit('update:visible', val)"
    @open="handleOpen"
  >
    <el-form :model="form" ref="formRef" label-position="top" @submit.prevent>
      <el-form-item label="资源名称" prop="name" :rules="{ required: true, message: '资源名称不能为空', trigger: 'blur' }">
        <el-input v-model="form.name" placeholder="请输入资源名称" @keyup.enter="handleConfirm" />
      </el-form-item>
      <el-form-item label="资源类型" prop="resourceType" :rules="{ required: true, message: '请选择资源类型', trigger: 'change' }">
        <el-select v-model="form.resourceType" placeholder="请选择资源类型" style="width: 100%;">
          <el-option
            v-for="type in resourceTypes"
            :key="type.value"
            :label="type.label"
            :value="type.value"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="handleConfirm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { ElMessage, type FormInstance } from 'element-plus';
import type { ResourceType } from '@/api/types';

// --- 类型定义 ---
interface ResourceTypeOption {
  value: ResourceType;
  label: string;
}

interface ConfirmPayload {
  name: string;
  resourceType: ResourceType;
}

// --- Props ---
const props = defineProps<{
  visible: boolean;
  title: string;
  resourceTypes: ResourceTypeOption[];
}>();

// --- Emits ---
const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', payload: ConfirmPayload): void;
}>();

// --- 响应式状态 ---
const formRef = ref<FormInstance>();
const form = reactive({
  name: '',
  resourceType: '' as ResourceType | '',
});

// --- 方法 ---
function handleOpen() {
  form.name = '新的资源';
  // 默认选中第一个可用的资源类型
  if (props.resourceTypes.length > 0) {
    form.resourceType = props.resourceTypes[0].value;
  }
  formRef.value?.clearValidate();
}

async function handleConfirm() {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (valid) {
      emit('confirm', {
        name: form.name.trim(),
        resourceType: form.resourceType as ResourceType,
      });
      emit('update:visible', false);
    } else {
      ElMessage.warning('请检查输入项');
    }
  });
};
</script>
