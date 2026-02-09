<template>
  <el-dialog v-model="internalVisible" title="选择要添加的模型" width="500px" @close="handleClose">
    <el-input v-model="modelSearchQuery" placeholder="搜索模型" clearable class="model-search-input" />
    <el-scrollbar height="300px">
      <el-checkbox-group v-model="selectedModelIds" class="fetched-model-group">
        <el-checkbox
          v-for="model in filteredFetchedModels"
          :key="model.modelId"
          :label="model.modelId"
          border
          class="fetched-model-checkbox"
        >
          {{ model.modelId }}
        </el-checkbox>
      </el-checkbox-group>
    </el-scrollbar>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleConfirm">确认添加</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import type { AIModelBase } from '@/api/types';

const props = defineProps<{
  visible: boolean;
  fetchedModels: AIModelBase[];
  // 已存在的模型 ID，用于默认选中
  existingModelIds?: string[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', selectedIds: string[]): void;
}>();

const internalVisible = ref(false);
const modelSearchQuery = ref('');
const selectedModelIds = ref<string[]>([]);

const filteredFetchedModels = computed(() => {
  if (!modelSearchQuery.value) {
    return props.fetchedModels;
  }
  const query = modelSearchQuery.value.toLowerCase();
  return props.fetchedModels.filter(model =>
    model.name.toLowerCase().includes(query) ||
    model.modelId.toLowerCase().includes(query)
  );
});

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    modelSearchQuery.value = '';
    // 每次打开时，使用外部传入的已存在模型ID列表初始化选中状态
    selectedModelIds.value = [...(props.existingModelIds || [])];
  }
});

function handleClose() {
  emit('update:visible', false);
}

function handleConfirm() {
  emit('confirm', selectedModelIds.value);
  handleClose();
}
</script>

<style scoped>
.model-search-input { margin-bottom: 15px; }
.fetched-model-group { display: flex; flex-direction: column; }
.fetched-model-checkbox { width: 100%; margin-bottom: 8px; margin-left: 0 !important; }
</style>
