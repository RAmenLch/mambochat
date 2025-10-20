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
        <el-form-item label="System Prompt (系统提示词)">
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
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import type { Chat, ChatUpdate, AIModel } from '@/api/types.ts';

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

const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: { temperature: 0.7, top_p: 0.9, stream: true, max_context_messages: 0 },
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
</style>
