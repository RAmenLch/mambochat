<template>
  <el-dialog v-model="internalVisible" :title="t('model.fetch.title')" width="500px" @close="handleClose">
    <el-input v-model="modelSearchQuery" :placeholder="t('model.fetch.placeholder')" clearable class="model-search-input" />
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
      <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirm">{{ t('model.fetch.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
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

const { t } = useI18n();
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
