<!-- frontend/mambo/src/components/chat/ChatSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    :title="$t('chat.settings.title')"
    direction="rtl"
    size="450px"
    @update:model-value="handleUpdateModelValue"
    @close="handleDrawerClose"
  >
    <div class="drawer-content">
      <el-form v-if="chatData" :model="chatSettingsForm" label-position="top">
        <el-form-item :label="$t('chat.settings.name')">
          <el-input v-model.trim="chatSettingsForm.name" :placeholder="$t('chat.settings.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('chat.settings.model')">
          <el-select v-model="chatSettingsForm.aiModelId" :placeholder="$t('chat.settings.modelPlaceholder')" style="width: 100%">
            <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
              <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label>
            <div class="form-item-label-with-action">
              <span>{{ $t('chat.settings.systemPrompt') }}</span>
              <el-button type="primary" link @click="promptDialogVisible = true">
                {{ $t('chat.settings.selectFromResource') }}
              </el-button>
            </div>
          </template>
          <el-input
            v-model="chatSettingsForm.systemPrompt"
            type="textarea"
            :rows="8"
            :placeholder="$t('chat.settings.systemPromptPlaceholder')"
          />

          <!-- 挂载资源预览区 (仅显示 System Prompt 和 Submessage Template) -->
          <div v-if="mountedSystemResources.length > 0" class="mounted-resources-wrapper">
            <MountedResourceTags v-model="mountedSystemResources" />
          </div>
        </el-form-item>
        <el-divider>{{ $t('chat.settings.modelParams') }}</el-divider>

        <!-- 固定参数 -->
        <el-form-item>
          <template #label>
            <span>{{ $t('chat.settings.contextCount') }}</span>
            <el-tooltip effect="dark" :content="$t('chat.settings.contextCountTip')" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number v-model="chatSettingsForm.modelParameters.max_context_messages" :min="0" :step="2" controls-position="right" style="width: 100%;" />
        </el-form-item>
        <el-form-item :label="$t('chat.settings.stream')">
           <el-switch v-model="chatSettingsForm.modelParameters.stream" />
           <el-tooltip class="box-item" effect="dark" :content="$t('chat.settings.streamTip')" placement="top">
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
           </el-tooltip>
        </el-form-item>
        <el-form-item :label="$t('chat.settings.enableSuggest')">
          <el-switch v-model="chatSettingsForm.modelParameters.enable_suggest" />
          <el-tooltip class="box-item" effect="dark" :content="$t('chat.settings.enableSuggestTip')" placement="top">
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item :label="$t('chat.settings.enableAskUser')">
          <el-switch v-model="chatSettingsForm.modelParameters.enable_ask_user" />
          <el-tooltip class="box-item" effect="dark" :content="$t('chat.settings.enableAskUserTip')" placement="top">
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
        <el-button @click="emit('update:visible', false)">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveSettings">{{ $t('common.action.save') }}</el-button>
      </div>
    </template>
  </el-drawer>

  <!-- Reusable Resource Selector Dialog -->
  <ResourceSelectorDialog
      v-model:visible="promptDialogVisible"
      context="chat-settings"
      @mount-resources="handleMountResources"
      @mount-knowledge-base="handleMountKnowledgeBase"
  />
</template>

<script setup lang="ts">
import { reactive, watch, ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useProviderStore } from '@/stores/providerStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { getResourceDetails } from '@/api/resourceService';
import type { Chat, ChatUpdate, AIModel, Resource, LLMParameterDefinition } from '@/api/types';
import ResourceSelectorDialog from '../common/dialogs/ResourceSelectorDialog.vue';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';
import { useChatListStore } from '@/stores/chatListStore';
const chatListStore = useChatListStore();

interface GroupedModels {
  label: string;
  options: AIModel[];
}

interface ChatSettingsForm {
  name: string | null;
  aiModelId: string | null;
  systemPrompt: string | null;
  modelParameters: Record<string, string | number | boolean | null | undefined | any>;
}

interface DynamicParameterUI {
  key: string;
  label: string;
  description: string;
  type: 'integer' | 'number' | 'string' | 'boolean';
  limit?: Array<string | number> | { min?: number; max?: number; };
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

const { t } = useI18n();
const systemConfigStore = useSystemConfigStore();
const providerStore = useProviderStore();
const chatSessionStore = useChatSessionStore();

// --- Dialog Visibility State ---
const promptDialogVisible = ref(false);

// --- Form State ---
const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: {},
});

// --- Mounted Resources State ---
// 仅用于管理 System Prompt 和 Submessage Template 类型的资源
const mountedSystemResources = ref<Resource[]>([]);

// --- Methods ---

const handleUpdateModelValue = (val: boolean) => {
  emit('update:visible', val);
};

const handleDrawerClose = () => {
  emit('close');
};

// --- Computed Properties ---

const filteredGroupedModels = computed(() => {
  return props.groupedModels
    .map(group => ({
      label: group.label,
      options: group.options.filter(m => m.model_type === 'chat')
    }))
    .filter(group => group.options.length > 0);
});

const dynamicParameters = computed((): DynamicParameterUI[] => {
  if (!props.chatData) return [];

  const currentModel = providerStore.allModels.find(m => m.id === chatSettingsForm.aiModelId);
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? []);

  const coreParameters = ['temperature', 'top_p'];

  return systemConfigStore.llmParameters
    .filter(paramDef =>
      coreParameters.includes(paramDef.key) ||
      supportedParameters.has(paramDef.key) ||
      paramDef.default_activate
    )
    .map(paramDef => ({
      key: paramDef.key,
      label: paramDef.label,
      description: paramDef.description,
      type: paramDef.type as 'integer' | 'number' | 'string' | 'boolean',
      limit: paramDef.limit,
      isEnabled: Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, paramDef.key),
      definition: paramDef,
    }));
});

const chatConfigSnapshot = computed(() => {
  if (!props.chatData) return null;
  return {
    id: props.chatData.id,
    name: props.chatData.name,
    aiModelId: props.chatData.aiModelId,
    systemPrompt: props.chatData.systemPrompt,
    modelParameters: props.chatData.modelParameters,
    resource_prompt_list: props.chatData.resource_prompt_list
  };
});

// --- Watchers ---

watch(chatConfigSnapshot, async (newConfig, oldConfig) => {
  if (newConfig) {
    chatSettingsForm.name = newConfig.name;
    chatSettingsForm.aiModelId = newConfig.aiModelId;
    chatSettingsForm.systemPrompt = newConfig.systemPrompt;

    const params = newConfig.modelParameters || {};
    chatSettingsForm.modelParameters = {
      ...JSON.parse(JSON.stringify(params)),
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
      enable_suggest: params.enable_suggest ?? false,
      enable_ask_user: params.enable_ask_user ?? false,
    };

    const hasResourceChanged =
      JSON.stringify(newConfig.resource_prompt_list) !== JSON.stringify(oldConfig?.resource_prompt_list);
    const hasChatChanged = newConfig.id !== oldConfig?.id;

    if (hasResourceChanged || hasChatChanged) {
      if (newConfig.resource_prompt_list && newConfig.resource_prompt_list.length > 0) {
        mountedSystemResources.value = [];
        try {
          const promises = newConfig.resource_prompt_list.map(id => getResourceDetails(id));
          const results = await Promise.all(promises);

          // 过滤：仅保留 System Prompt 和 Submessage Template
          const orderedResults = newConfig.resource_prompt_list
            .map(id => results.find(r => r.id === id))
            .filter((r) => !!r) as Resource[];

          mountedSystemResources.value = orderedResults.filter(
            r => r.resourceType === 'system_prompt' || r.resourceType === 'submessage_template'
          );
        } catch (error) {
          console.error('Failed to load mounted resources:', error);
        }
      } else {
        mountedSystemResources.value = [];
      }
    }
  }
}, { immediate: true, deep: true });

watch(() => chatSettingsForm.aiModelId, (newModelId) => {
  if (!newModelId) return;

  const currentModel = providerStore.allModels.find(m => m.id === newModelId);
  if (!currentModel) return;

  const supportedParams = new Set(currentModel.meta_config?.supported_parameters ?? []);
  const coreParameters = ['temperature', 'top_p'];

  const keysToKeep = new Set<string>();
  keysToKeep.add('max_context_messages');
  keysToKeep.add('stream');
  keysToKeep.add('enable_suggest');
  keysToKeep.add('enable_ask_user');

  if (systemConfigStore.llmParameters) {
    systemConfigStore.llmParameters.forEach(paramDef => {
      if (
        coreParameters.includes(paramDef.key) ||
        supportedParams.has(paramDef.key) ||
        paramDef.default_activate
      ) {
        keysToKeep.add(paramDef.key);
      }
    });
  }

  const newParams: Record<string, any> = {};
  for (const key in chatSettingsForm.modelParameters) {
    if (keysToKeep.has(key)) {
      newParams[key] = chatSettingsForm.modelParameters[key];
    }
  }

  chatSettingsForm.modelParameters = newParams;
});

function getSliderStep(min: number, max: number): number {
  const range = max - min;
  if (range <= 2) return 0.01;
  if (range <= 20) return 0.1;
  return 1;
}

function handleToggleParameter(param: DynamicParameterUI, isEnabled: boolean) {
  const newParams = { ...chatSettingsForm.modelParameters };

  if (isEnabled) {
    newParams[param.key] = param.definition.default_value;
  } else {
    delete newParams[param.key];
  }

  chatSettingsForm.modelParameters = newParams;
}

function handleMountResources(resources: Resource[]) {
  if (resources.length === 0) return;

  resources.forEach(resource => {
    if (!mountedSystemResources.value.some(r => r.id === resource.id)) {
      mountedSystemResources.value.push(resource);
    }
  });
}

function handleSaveSettings() {
  if (!props.chatData) return;
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning(t('chat.settings.namePlaceholder'));
    return;
  }

  const finalModelParameters: Record<string, any> = {
    max_context_messages: chatSettingsForm.modelParameters.max_context_messages,
    stream: chatSettingsForm.modelParameters.stream,
    enable_suggest: chatSettingsForm.modelParameters.enable_suggest,
    enable_ask_user: chatSettingsForm.modelParameters.enable_ask_user,
  };

  for (const key in chatSettingsForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, key)) {
      if (key === 'max_context_messages' || key === 'stream') {
        continue;
      }
      finalModelParameters[key] = chatSettingsForm.modelParameters[key];
    }
  }

  // 1. 获取抽屉中编辑的资源 ID (System Prompt / Template)
  const drawerResourceIds = mountedSystemResources.value.map(r => r.id);

  // 2. 获取当前挂载的知识库 ID (从 Session Store 中获取，避免覆盖)
  const currentKbIds = chatSessionStore.systemPromptResources
    .filter(r => r.resourceType === 'knowledge_base')
    .map(r => r.id);

  // 3. 合并生成最终的 resource_prompt_list
  const resourcePromptList = [...drawerResourceIds, ...currentKbIds];

  emit('save', {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: finalModelParameters,
    resource_prompt_list: resourcePromptList.length > 0 ? resourcePromptList : null,
  });
}
async function handleMountKnowledgeBase(resources: Resource[]) {
  if (!props.chatData) return;

  const currentList = props.chatData.resource_prompt_list || [];
  const newIds = resources.map(r => r.id).filter(id => !currentList.includes(id));

  if (newIds.length > 0) {
    const updatedList = [...currentList, ...newIds];
    // 立即更新后端，ChatWindow 会自动响应变化显示在 AttachmentPreview 中
    await chatListStore.updateChatSettings(props.chatData.id, {
      resource_prompt_list: updatedList
    });
    ElMessage.success(`已启用知识库: ${resources.map(r => r.name).join(', ')}`);
  }
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

.mounted-resources-wrapper {
  margin-top: 8px;
  background-color: var(--color-background-soft);
  padding: 4px;
  border-radius: 4px;
}
</style>
