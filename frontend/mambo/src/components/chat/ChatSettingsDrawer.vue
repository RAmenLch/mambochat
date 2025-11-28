<template>
  <el-drawer
    :model-value="visible"
    title="会话设置"
    direction="rtl"
    size="450px"
    @update:model-value="val => emit('update:visible', val)"
    @close="handleDrawerClose"
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

        <!-- 固定参数 -->
        <el-form-item>
          <template #label>
            <span>上下文消息数量 (Context)</span>
            <el-tooltip effect="dark" content="每次请求时携带的最近历史消息数量。0 代表不限制（发送全部历史）。" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number v-model="chatSettingsForm.modelParameters.max_context_messages" :min="0" :step="2" controls-position="right" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="流式对话 (Stream)">
           <el-switch v-model="chatSettingsForm.modelParameters.stream" />
           <el-tooltip class="box-item" effect="dark" content="关闭后, AI将一次性返回完整回复, 可能会增加等待时间。" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
        </el-form-item>

        <!-- 动态参数 -->
        <el-form-item v-for="param in dynamicParameters" :key="param.key">
          <template #label>
            <span>{{ param.label }}</span>
            <el-tooltip effect="dark" :content="param.description" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <div class="parameter-control-wrapper">
            <!-- 输入控件 -->
            <el-slider
              v-if="param.type === 'number'"
              v-model="chatSettingsForm.modelParameters[param.key]"
              :min="!Array.isArray(param.limit) ? param.limit?.min ?? 0 : 0"
              :max="!Array.isArray(param.limit) ? param.limit?.max ?? 1 : 1"
              :step="getSliderStep(
                !Array.isArray(param.limit) ? param.limit?.min ?? 0 : 0,
                !Array.isArray(param.limit) ? param.limit?.max ?? 1 : 1
              )"
              :disabled="!param.isEnabled"
              show-input
              class="parameter-input"
            />
            <el-input-number
              v-else-if="param.type === 'integer'"
              v-model="chatSettingsForm.modelParameters[param.key]"
              :min="!Array.isArray(param.limit) ? param.limit?.min : undefined"
              :max="!Array.isArray(param.limit) ? param.limit?.max : undefined"
              :disabled="!param.isEnabled"
              controls-position="right"
              class="parameter-input"
            />
            <el-select
              v-else-if="param.type === 'string' && Array.isArray(param.limit)"
              v-model="chatSettingsForm.modelParameters[param.key]"
              :disabled="!param.isEnabled"
              class="parameter-input"
            >
              <el-option v-for="opt in param.limit" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-switch
              v-else-if="param.type === 'boolean'"
              v-model="chatSettingsForm.modelParameters[param.key]"
              :disabled="!param.isEnabled"
              class="parameter-input"
            />

            <!-- 启用开关 -->
            <el-switch
              :model-value="param.isEnabled"
              @change="isEnabled => handleToggleParameter(param, isEnabled as boolean)"
              class="parameter-switch"
            />
          </div>
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

  <!-- Reusable Resource Selector Dialog -->
  <ResourceSelectorDialog
    v-model:visible="promptDialogVisible"
    resource-type-filter="system_prompt"
    @select-resource="handleAppendSystemPrompt"
  />
</template>

<script setup lang="ts">
import { reactive, watch, ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useProviderStore } from '@/stores/providerStore';
import type { Chat, ChatUpdate, AIModel, Resource, LLMParameterDefinition } from '@/api/types.ts';
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue';

interface GroupedModels {
  label: string;
  options: AIModel[];
}

interface ChatSettingsForm {
  name: string | null;
  aiModelId: string | null;
  systemPrompt: string | null;
  modelParameters: Record<string, any>;
}

interface DynamicParameterUI {
  key: string;
  label: string;
  description: string;
  type: 'integer' | 'number' | 'string' | 'boolean';
  limit?: Array<any> | { min?: number; max?: number; };
  isEnabled: boolean;
  definition: LLMParameterDefinition;
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

const systemConfigStore = useSystemConfigStore();
const providerStore = useProviderStore();

// --- Dialog Visibility State ---
const promptDialogVisible = ref(false);

// --- Form State ---
const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: {},
});

// --- Computed Properties ---
const dynamicParameters = computed((): DynamicParameterUI[] => {
  if (!props.chatData) return [];

  const currentModel = providerStore.allModels.find(m => m.id === chatSettingsForm.aiModelId);
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? []);

  return systemConfigStore.llmParameters
    .filter(paramDef =>
      // 显示条件：模型支持 或 参数是默认激活的
      supportedParameters.has(paramDef.key) || paramDef.default_activate
    )
    .map(paramDef => ({
      key: paramDef.key,
      label: paramDef.label,
      description: paramDef.description,
      type: paramDef.type,
      limit: paramDef.limit,
      isEnabled: Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, paramDef.key),
      definition: paramDef,
    }));
});

// --- Watchers ---
watch(() => props.chatData, (newChat) => {
  if (newChat) {
    chatSettingsForm.name = newChat.name;
    chatSettingsForm.aiModelId = newChat.aiModelId;
    chatSettingsForm.systemPrompt = newChat.systemPrompt;

    const params = newChat.modelParameters || {};
    // 深拷贝并确保固定参数有默认值
    chatSettingsForm.modelParameters = {
      ...JSON.parse(JSON.stringify(params)),
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
    };
  }
}, { immediate: true, deep: true });

// --- Methods ---

function getSliderStep(min: number, max: number): number {
  const range = max - min;
  if (range <= 2) return 0.01;
  if (range <= 20) return 0.1;
  return 1;
}

function handleToggleParameter(param: DynamicParameterUI, isEnabled: boolean) {
  // 创建 modelParameters 的一个新副本以确保响应性
  const newParams = { ...chatSettingsForm.modelParameters };

  if (isEnabled) {
    // 当启用参数时，为其设置默认值
    newParams[param.key] = param.definition.default_value;
  } else {
    // 当禁用参数时，从新副本中移除该键
    delete newParams[param.key];
  }

  // 将修改后的新副本重新赋值给 chatSettingsForm.modelParameters
  chatSettingsForm.modelParameters = newParams;
}

function handleAppendSystemPrompt(resources: Resource[]) {
  if (resources.length === 0) return;

  const contentsToAppend = resources
    .map(res => res.latest_version?.content)
    .filter((content): content is string => !!content)
    .join('\n');

  if (!contentsToAppend) return;

  const currentPrompt = chatSettingsForm.systemPrompt || '';
  const separator = currentPrompt.trim().length > 0 ? '\n' : '';

  chatSettingsForm.systemPrompt = currentPrompt + separator + contentsToAppend;
}

function handleSaveSettings() {
  if (!props.chatData) return;
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning('会话名称不能为空');
    return;
  }

  const currentModel = providerStore.allModels.find(m => m.id === chatSettingsForm.aiModelId);
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? []);

  const finalModelParameters: Record<string, any> = {
    max_context_messages: chatSettingsForm.modelParameters.max_context_messages,
    stream: chatSettingsForm.modelParameters.stream,
  };

  for (const key in chatSettingsForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, key)) {
      if (key === 'max_context_messages' || key === 'stream') {
        continue;
      }
      // 仅当参数被当前模型支持时，才将其包含在最终提交的数据中
      if (supportedParameters.has(key)) {
        finalModelParameters[key] = chatSettingsForm.modelParameters[key];
      }
    }
  }

  emit('save', {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: finalModelParameters,
  });
}

function handleDrawerClose() {
  emit('close');
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
.parameter-control-wrapper {
  display: flex;
  align-items: center;
  width: 100%;
}
.parameter-input {
  flex-grow: 1;
}
.parameter-switch {
  margin-left: 16px;
  flex-shrink: 0;
}
</style>
