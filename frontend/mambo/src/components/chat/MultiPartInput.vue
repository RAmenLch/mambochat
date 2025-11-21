<!-- frontend/mambo/src/components/chat/MultiPartInput.vue -->
<template>
  <div class="multi-part-input-container">
    <div class="partition-sidebar">
      <el-scrollbar>
        <div
          v-for="(part, index) in localPartitions"
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
      <!-- 确保在 localPartitions 可用时才渲染 el-input，防止绑定错误 -->
      <el-input
        v-if="localPartitions.length > 0 && localPartitions[activeIndex]"
        ref="textareaRef"
        v-model="localPartitions[activeIndex].content"
        type="textarea"
        resize="none"
        :placeholder="`输入分区 ${activeIndex + 1} 的内容... (Shift + Enter 换行)`"
        @keydown="handleKeydown"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { Plus, Close } from '@element-plus/icons-vue';
import type { SubMessageCreate } from '@/api/types';
import type { ElInput } from 'element-plus';

// 分区对象的本地UI表示
interface Partition {
  id: number;
  content: string;
}

// 接收 modelValue prop (用于 v-model)
const props = defineProps<{
  modelValue: Partition[];
  activeIndex: number;
}>();

// 定义组件可发出的事件
const emit = defineEmits<{
  (e: 'update:modelValue', value: Partition[]): void;
  (e: 'update:activeIndex', index: number): void;
  (e: 'send'): void;
}>();


const localPartitions = ref<Partition[]>([]);
// 移除本地 activeIndex 状态
const textareaRef = ref<InstanceType<typeof ElInput>>();

// --- 数据同步 ---

// 1. 从父组件(prop)到本地状态的单向同步
watch(() => props.modelValue, (newVal) => {
  if (JSON.stringify(newVal) !== JSON.stringify(localPartitions.value)) {
    const partitionsToSet = newVal && newVal.length > 0 ? newVal : [{ id: Date.now(), content: '' }];
    localPartitions.value = JSON.parse(JSON.stringify(partitionsToSet));
  }
}, { deep: true, immediate: true });

// 2. 从本地状态到父组件(emit)的单向同步
watch(localPartitions, (newVal) => {
  emit('update:modelValue', newVal);
}, { deep: true });


// --- UI 交互方法 ---

const selectPartition = (index: number) => {
  // 不再修改本地状态，而是发出事件
  emit('update:activeIndex', index);
  textareaRef.value?.focus();
};

const addPartition = async () => {
  localPartitions.value.push({ id: Date.now(), content: '' });
  const newIndex = localPartitions.value.length - 1;
  // 发出事件以更新父组件中的 activeIndex
  emit('update:activeIndex', newIndex);
  await nextTick();
  textareaRef.value?.focus();
};

const removePartition = (index: number) => {
  if (localPartitions.value.length <= 1) return;

  const currentActiveIndex = props.activeIndex;
  localPartitions.value.splice(index, 1);

  // 如果删除的是当前激活的分区或其之前的分区，则需要调整激活索引
  if (index <= currentActiveIndex) {
    const newIndex = Math.max(0, currentActiveIndex - 1);
    if (newIndex !== currentActiveIndex) {
      emit('update:activeIndex', newIndex);
    }
  }
};

const handleKeydown = (event: Event) => {
  if (!(event instanceof KeyboardEvent)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    emit('send');
  }
};

// --- 暴露给父组件的方法 ---

/**
 * 获取符合API格式的分区数据。
 */
const getData = (): SubMessageCreate[] => {
  return localPartitions.value
    .map((part, index): SubMessageCreate => ({
      content: part.content,
      sortOrder: index,
      type: 'Normal',
    }))
    .filter(part => part.content.trim() !== '');
};

/**
 * 重置输入框为初始状态。
 */
const reset = () => {
  localPartitions.value = [{ id: Date.now(), content: '' }];
  // 重置时，通知父组件将索引也重置为0
  emit('update:activeIndex', 0);
};

/**
 * 将焦点设置到当前激活的文本区域。
 */
const focus = () => {
  textareaRef.value?.focus();
};

defineExpose({
  getData,
  reset,
  focus,
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

.partition-editor .el-input,
.partition-editor :deep(.el-textarea) {
  height: 100%;
}

.partition-editor :deep(.el-textarea__inner) {
  height: 100% !important;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
</style>
