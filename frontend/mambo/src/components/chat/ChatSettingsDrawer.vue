<template>
  <el-drawer
    :model-value="visible"
    title="会话设置"
    direction="rtl"
    size="450px"
    @update:model-value="val => emit('update:visible', val)"
    @close="emit('close')"
  >
    <div class="drawer-content">
      <el-form v-if="chatData" :model="chatSettingsForm" label-position="top">
        <el-form-item label="会话名称">
          <el-input v-model.trim="chatSettingsForm.name" placeholder="请输入会话名称" />
        </el-form-item>
        <el-form-item label="AI 模型">
          <el-select v-model="chatSettingsForm.aiModelId" placeholder="请选择一个AI模型" style="width: 100%">
            <el-option-group v-for="group in groupedModels" :key="group.label" :label="group.label">
              <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label>
            <div class="form-item-label-with-action">
              <span>System Prompt (系统提示词)</span>
              <el-button type="primary" link @click="promptDialogVisible = true">从资源库选择</el-button>
            </div>
          </template>
          <el-input v-model="chatSettingsForm.systemPrompt" type="textarea" :rows="8" placeholder="定义AI的角色和行为" />
        </el-form-item>
        <el-divider>模型参数</el-divider>
        <el-form-item>
          <template #label>
            <span>上下文消息数量 (Context)</span>
            <el-tooltip effect="dark" content="每次请求时携带的最近历史消息数量。0 代表不限制（发送全部历史）。" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number v-model="chatSettingsForm.modelParameters.max_context_messages" :min="0" :step="2" controls-position="right" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="Temperature (温度)">
          <el-slider v-model="chatSettingsForm.modelParameters.temperature" :min="0" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="Top P">
          <el-slider v-model="chatSettingsForm.modelParameters.top_p" :min="0" :max="1" :step="0.01" show-input />
        </el-form-item>
        <el-form-item label="流式对话 (Stream)">
           <el-switch v-model="chatSettingsForm.modelParameters.stream" />
           <el-tooltip class="box-item" effect="dark" content="关闭后, AI将一次性返回完整回复, 可能会增加等待时间。" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
        </el-form-item>
      </el-form>
    </div>
    <template #footer>
      <div style="flex: auto">
        <el-button @click="emit('update:visible', false)">取消</el-button>
        <el-button type="primary" @click="handleSaveSettings">保存</el-button>
      </div>
    </template>
  </el-drawer>

  <!-- System Prompt Selection Dialog -->
  <el-dialog v-model="promptDialogVisible" title="选择一个 System Prompt" width="500px">
    <div class="prompt-list-container">
      <el-scrollbar>
        <div v-if="isResourcesLoading" class="loading-state">
          <el-skeleton :rows="3" animated />
        </div>
        <div v-else-if="systemPrompts.length === 0" class="empty-state">
          <el-empty description="没有可用的提示模板" />
        </div>
        <ul v-else class="prompt-list">
          <li v-for="prompt in systemPrompts" :key="prompt.id" class="prompt-item" @click="handleSelectPrompt(prompt)">
            <div class="prompt-name">{{ prompt.name }}</div>
            <div class="prompt-description">{{ prompt.description }}</div>
          </li>
        </ul>
      </el-scrollbar>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch, ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useResourceStore } from '@/stores/resourceStore';
import type { Chat, ChatUpdate, AIModel, Resource } from '@/api/types.ts';

interface GroupedModels {
  label: string;
  options: AIModel[];
}
interface ChatSettingsForm extends ChatUpdate {
  name: string | null;
  modelParameters: {
    temperature: number;
    top_p: number;
    stream: boolean;
    max_context_messages: number;
  };
}

const props = defineProps<{
  visible: boolean;
  chatData: Chat | null;
  groupedModels: GroupedModels[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'close'): void;
  (e: 'save', settings: ChatUpdate): void;
}>();

// --- Resource Store Integration ---
const resourceStore = useResourceStore();
const { resources, isResourcesLoading } = storeToRefs(resourceStore);
const promptDialogVisible = ref(false);

const systemPrompts = computed(() =>
  resources.value.filter(r => r.itemType === 'resource' && r.resourceType === 'system_prompt')
);

// --- Form State ---
const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: { temperature: 0.7, top_p: 0.9, stream: true, max_context_messages: 0 },
});

// --- Watchers ---
watch(() => props.visible, (isVisible) => {
  // Fetch resources when the drawer is opened, if they haven't been fetched yet.
  if (isVisible && resources.value.length === 0) {
    resourceStore.fetchResources();
  }
});

watch(() => props.chatData, (newChat) => {
  if (newChat) {
    chatSettingsForm.name = newChat.name;
    chatSettingsForm.aiModelId = newChat.aiModelId;
    chatSettingsForm.systemPrompt = newChat.systemPrompt;
    const params = newChat.modelParameters;
    chatSettingsForm.modelParameters.temperature = params?.temperature ?? 0.7;
    chatSettingsForm.modelParameters.top_p = params?.top_p ?? 0.9;
    chatSettingsForm.modelParameters.stream = params?.stream ?? true;
    chatSettingsForm.modelParameters.max_context_messages = params?.max_context_messages ?? 0;
  }
}, { immediate: true, deep: true });

// --- Methods ---
function handleSelectPrompt(prompt: Resource) {
  if (prompt.latest_version && prompt.latest_version.content) {
    chatSettingsForm.systemPrompt = prompt.latest_version.content;
  }
  promptDialogVisible.value = false;
}

function handleSaveSettings() {
  if (!props.chatData) return;
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning('会话名称不能为空');
    return;
  }
  emit('save', {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: { ...chatSettingsForm.modelParameters },
  });
}
</script>

<style scoped>
.drawer-content {
  padding: 0 20px;
}
.label-icon {
  margin-left: 8px;
  color: #909399;
  cursor: help;
}
.el-form-item .el-switch {
  margin-right: 8px;
}
.form-item-label-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

/* Styles for Prompt Selection Dialog */
.prompt-list-container {
  height: 400px;
}
.prompt-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.prompt-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  transition: background-color 0.2s;
}
.prompt-item:hover {
  background-color: var(--el-fill-color-light);
}
.prompt-item:last-child {
  border-bottom: none;
}
.prompt-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.prompt-description {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.loading-state, .empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}
</style>
