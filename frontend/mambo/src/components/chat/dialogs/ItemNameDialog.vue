<template>
  <el-dialog v-model="internalVisible" :title="dialogTitle" width="400px" @close="handleClose">
    <el-input v-model="itemNameInput" placeholder="请输入名称" @keyup.enter="handleConfirm" />
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleConfirm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';

const props = defineProps<{
  // 控制对话框的显示与隐藏
  visible: boolean;
  // 对话框的标题
  title: string;
  // 初始的名称值，用于编辑场景
  initialName?: string;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', name: string): void;
}>();

const internalVisible = ref(false);
const itemNameInput = ref('');
const dialogTitle = ref('');

// 监听外部 visible 属性的变化以控制内部状态
watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    // 每次打开对话框时，根据 props 初始化标题和输入值
    dialogTitle.value = props.title;
    itemNameInput.value = props.initialName ?? '';
  }
});

const handleClose = () => {
  emit('update:visible', false);
};

const handleConfirm = () => {
  const trimmedName = itemNameInput.value.trim();
  if (!trimmedName) {
    ElMessage.warning('名称不能为空');
    return;
  }
  emit('confirm', trimmedName);
  handleClose();
};
</script>
