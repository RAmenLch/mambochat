<!-- frontend/mambo/src/mobile/components/settings/dialogs/MobileFetchModelsDialog.vue -->
<template>
  <!-- Bottom to top style often better for selection lists on mobile -->
  <el-drawer
    v-model="internalVisible"
    :title="t('model.fetch.title')"
    direction="btt"
    size="70%"
  >
    <div class="fetch-dialog-content">
      <el-input
        v-model="searchQuery"
        :placeholder="t('model.fetch.placeholder')"
        clearable
        class="search-input"
      />

      <el-scrollbar height="100%">
        <div class="model-list">
          <el-check-tag
            v-for="model in filteredModels"
            :key="model.modelId"
            :checked="selectedIds.includes(model.modelId)"
            @change="toggleSelection(model.modelId)"
            class="model-tag"
          >
            {{ model.modelId }}
          </el-check-tag>
        </div>
      </el-scrollbar>
    </div>

    <template #footer>
      <el-button type="primary" @click="handleConfirm" style="width: 100%">
        {{ t('model.fetch.confirm') }} ({{ selectedIds.length }})
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { AIModelBase } from '@/api/types';

const props = defineProps<{
  visible: boolean;
  fetchedModels: AIModelBase[];
  existingModelIds: string[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', selectedIds: string[]): void;
}>();

const { t } = useI18n();
const searchQuery = ref('');
const selectedIds = ref<string[]>([]);

// 修复核心：使用计算属性代理 v-model
// get: 读取 props.visible
// set: 触发 update:visible 事件，通知父组件更新
const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const filteredModels = computed(() => {
  if (!searchQuery.value) return props.fetchedModels;
  return props.fetchedModels.filter(m =>
    m.modelId.toLowerCase().includes(searchQuery.value.toLowerCase())
  );
});

watch(() => props.visible, (val) => {
  if (val) {
    searchQuery.value = '';
    selectedIds.value = [...props.existingModelIds]; // Default select existing
  }
});

const toggleSelection = (id: string) => {
  const index = selectedIds.value.indexOf(id);
  if (index > -1) {
    selectedIds.value.splice(index, 1);
  } else {
    selectedIds.value.push(id);
  }
};

const handleConfirm = () => {
  emit('confirm', selectedIds.value);
  // 关闭抽屉，这会触发 internalVisible 的 set，进而 emit 事件
  internalVisible.value = false;
};
</script>

<style scoped>
.fetch-dialog-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.search-input {
  margin-bottom: 15px;
}
.model-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.model-tag {
  padding: 8px 15px;
  border-radius: 20px;
}
</style>
