<template>
  <div class="multi-part-input-container">
    <div class="partition-sidebar">
      <el-scrollbar>
        <div
          v-for="(part, index) in partitions"
          :key="part.id"
          class="partition-tab"
          :class="{ 'is-active': activeIndex === index }"
          @click="selectPartition(index)"
        >
          <span class="tab-index">{{ index + 1 }}</span>
          <el-icon class="close-icon" @click.stop="removePartition(index)"><Close /></el-icon>
        </div>
      </el-scrollbar>
      <div class="add-partition">
        <el-button :icon="Plus" circle size="small" @click="addPartition" title="添加分区" />
      </div>
    </div>
    <div class="partition-editor">
      <el-input
        ref="textareaRef"
        v-model="partitions[activeIndex].content"
        type="textarea"
        resize="none"
        :placeholder="`输入分区 ${activeIndex + 1} 的内容...`"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue';
import { Plus, Close } from '@element-plus/icons-vue';
import type { SubMessageCreate } from '@/api/types';
import type { ElInput } from 'element-plus';

interface Partition {
  id: number;
  content: string;
}

const partitions = ref<Partition[]>([{ id: Date.now(), content: '' }]);
const activeIndex = ref(0);
const textareaRef = ref<InstanceType<typeof ElInput>>();

const selectPartition = (index: number) => {
  activeIndex.value = index;
  textareaRef.value?.focus();
};

const addPartition = async () => {
  partitions.value.push({ id: Date.now(), content: '' });
  await nextTick();
  selectPartition(partitions.value.length - 1);
};

const removePartition = (index: number) => {
  if (partitions.value.length <= 1) return;

  partitions.value.splice(index, 1);

  if (activeIndex.value >= partitions.value.length) {
    activeIndex.value = partitions.value.length - 1;
  } else if (activeIndex.value === index) {
    // If the active tab was deleted, stay at the same index if possible
    // This is handled implicitly by the previous check if it was the last one
  }
};

const getData = (): SubMessageCreate[] => {
  return partitions.value
    .map((part, index) => ({
      content: part.content,
      sortOrder: index,
    }))
    .filter(part => part.content.trim() !== '');
};

const reset = () => {
  partitions.value = [{ id: Date.now(), content: '' }];
  activeIndex.value = 0;
};

defineExpose({
  getData,
  reset,
});
</script>

<style scoped>
.multi-part-input-container {
  display: flex;
  height: 100%;
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

.partition-sidebar {
  width: 40px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color);
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
}

.partition-sidebar .el-scrollbar {
  flex-grow: 1;
}

.partition-tab {
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  color: var(--el-text-color-regular);
}

.partition-tab:hover {
  background-color: var(--el-color-primary-light-9);
}

.partition-tab.is-active {
  background-color: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.tab-index {
  font-weight: 500;
}

.close-icon {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 12px;
  display: none;
  color: var(--el-text-color-placeholder);
}

.partition-tab:hover .close-icon {
  display: block;
}
.close-icon:hover {
  color: var(--el-color-danger);
}

.add-partition {
  height: 25px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-top: 1px solid var(--el-border-color);
}

.partition-editor {
  flex-grow: 1;
}

.partition-editor .el-textarea {
  height: 100%;
}

.partition-editor :deep(.el-textarea__inner) {
  height: 100% !important;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
</style>
