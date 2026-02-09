<!-- frontend/mambo/src/components/chat/ZipHistoryCard.vue -->
<template>
  <div class="zip-history-card-container">
    <!-- Card Header: Status and Actions -->
    <div class="zip-card-header">
      <el-tag :type="isZipEnabled ? 'success' : 'info'" size="small" effect="light">
        {{ isZipEnabled ? '已启用' : '未启用' }}
      </el-tag>
      <div class="actions" v-if="!isEditing">
        <el-button type="primary" link @click="handleEdit">编辑</el-button>
        <el-button :type="isZipEnabled ? 'warning' : 'primary'" link @click="handleToggleEnable">
          {{ isZipEnabled ? '禁用' : '启用' }}
        </el-button>
      </div>
    </div>

    <!-- Card Body: Content Display or Editor -->
    <div class="zip-card-body">
      <div v-if="!isEditing" class="content-display">
        {{ subMessage.content }}
      </div>
      <div v-else class="content-editor">
        <el-input
          ref="editorInputRef"
          v-model="editedContent"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 15 }"
          resize="none"
        />
        <div class="editor-actions">
          <el-button @click="isEditing = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="isSaving">保存</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue';
import type { PropType } from 'vue';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import type { SubMessage, SubMessageUpdate } from '@/api/types';
import { ElInput } from 'element-plus';

const props = defineProps({
  subMessage: {
    type: Object as PropType<SubMessage>,
    required: true,
  }
});

const interactionStore = useChatInteractionStore();

const isEditing = ref(false);
const isSaving = ref(false);
const editedContent = ref('');
const editorInputRef = ref<InstanceType<typeof ElInput> | null>(null);

const isZipEnabled = computed(() => props.subMessage.config.zip_enable === true);

async function handleEdit() {
  editedContent.value = props.subMessage.content;
  isEditing.value = true;
  await nextTick();
  editorInputRef.value?.focus();
}

async function handleSave() {
  if (editedContent.value.trim() === props.subMessage.content) {
    isEditing.value = false;
    return;
  }

  isSaving.value = true;
  try {
    const payload: SubMessageUpdate = {
      content: editedContent.value
    };
    await interactionStore.updateZipHistorySubMessage(props.subMessage.id, payload);
    isEditing.value = false;
  } finally {
    isSaving.value = false;
  }
}

function handleToggleEnable() {
  const newConfig = {
    ...props.subMessage.config,
    zip_enable: !isZipEnabled.value
  };
  const payload: SubMessageUpdate = {
    config: newConfig
  };
  interactionStore.updateZipHistorySubMessage(props.subMessage.id, payload);
}
</script>

<style scoped>
.zip-history-card-container {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background-color: var(--color-background-soft);
  overflow: hidden;
}

.zip-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background-color: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.actions {
  display: flex;
  gap: 8px;
}

.actions .el-button {
  font-size: 13px;
}

.zip-card-body {
  padding: 12px;
}

.content-display {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap; /* Preserve whitespace and newlines */
  word-break: break-word;
}

.content-editor {
  display: flex;
  flex-direction: column;
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
