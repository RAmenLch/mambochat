<!-- frontend/mambo/src/components/chat/ChatSettingsDrawer.vue -->
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
            <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
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

          <!-- 挂载资源预览区 (支持拖拽排序) -->
          <div v-if="mountedSystemResources.length > 0" class="mounted-resources-wrapper">
            <transition-group
              name="list"
              tag="div"
              class="mounted-resources-area"
            >
              <el-tag
                v-for="(resource, index) in mountedSystemResources"
                :key="resource.id"
                closable
                disable-transitions
                type="info"
                class="draggable-tag"
                :class="{ 'is-dragging': draggedIndex === index }"
                draggable="true"
                @dragstart.stop="handleDragStart(index, $event)"
                @dragover.prevent.stop="handleDragOver($event)"
                @drop.stop="handleDrop(index)"
                @dragend="handleDragEnd"
                @close="handleRemoveMountedResource(resource.id)"
              >
                <el-tooltip :content="resource.latest_version?.content || '无内容'" placement="top">
                  <span>{{ resource.name }}</span>
                </el-tooltip>
              </el-tag>
            </transition-group>
          </div>
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
        <el-form-item label="流式对话">
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
    source="settings"
    @mount-resources="handleMountResources"
  />
</template>

<script setup lang="ts">
import { reactive, watch, ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useProviderStore } from '@/stores/providerStore';
import { getResourceDetails } from '@/api/resourceService';
import type { Chat, ChatUpdate, AIModel, Resource, LLMParameterDefinition } from '@/api/types';
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

// --- Mounted Resources State ---
const mountedSystemResources = ref<Resource[]>([]);

// --- Drag and Drop State ---
const draggedIndex = ref<number | null>(null);

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

  // 核心参数：无论模型是否显式声明支持，都应显示在列表中，允许用户按需启用
  const coreParameters = ['temperature', 'top_p'];

  return systemConfigStore.llmParameters
    .filter(paramDef =>
      // 显示条件：核心参数 或 模型明确支持 或 参数是默认激活的
      coreParameters.includes(paramDef.key) ||
      supportedParameters.has(paramDef.key) ||
      paramDef.default_activate
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
    // 1. 同步基本表单数据
    chatSettingsForm.name = newConfig.name;
    chatSettingsForm.aiModelId = newConfig.aiModelId;
    chatSettingsForm.systemPrompt = newConfig.systemPrompt;

    const params = newConfig.modelParameters || {};
    chatSettingsForm.modelParameters = {
      ...JSON.parse(JSON.stringify(params)),
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
    };

    // 2. 智能加载挂载资源
    const hasResourceChanged =
      JSON.stringify(newConfig.resource_prompt_list) !== JSON.stringify(oldConfig?.resource_prompt_list);
    const hasChatChanged = newConfig.id !== oldConfig?.id;

    if (hasResourceChanged || hasChatChanged) {
      if (newConfig.resource_prompt_list && newConfig.resource_prompt_list.length > 0) {
        mountedSystemResources.value = [];
        try {
          // 并发请求资源详情
          const promises = newConfig.resource_prompt_list.map(id => getResourceDetails(id));
          const results = await Promise.all(promises);

          // 保持原有顺序，并过滤掉 undefined
          // 修复：使用 as Resource[] 强制类型转换，解决 ResourceWithVersions 和 Resource 的类型兼容问题
          const orderedResults = newConfig.resource_prompt_list
            .map(id => results.find(r => r.id === id))
            .filter((r) => !!r) as Resource[];

          mountedSystemResources.value = orderedResults;
        } catch (error) {
          console.error('Failed to load mounted resources:', error);
          ElMessage.error('加载挂载资源失败');
        }
      } else {
        mountedSystemResources.value = [];
      }
    }
  }
}, { immediate: true, deep: true });

// 监听模型切换，清理不支持的参数
watch(() => chatSettingsForm.aiModelId, (newModelId) => {
  if (!newModelId) return;

  const currentModel = providerStore.allModels.find(m => m.id === newModelId);
  if (!currentModel) return;

  const supportedParams = new Set(currentModel.meta_config?.supported_parameters ?? []);
  const coreParameters = ['temperature', 'top_p'];

  const keysToKeep = new Set<string>();

  keysToKeep.add('max_context_messages');
  keysToKeep.add('stream');

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

// --- Methods ---

// --- Drag and Drop Logic ---
const handleDragStart = (index: number, event: DragEvent) => {
  draggedIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', index.toString());
  }
};

const handleDragOver = (event: DragEvent) => {
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move';
  }
};

const handleDrop = (targetIndex: number) => {
  if (draggedIndex.value === null || draggedIndex.value === targetIndex) {
    return;
  }

  const newResources = [...mountedSystemResources.value];
  const [draggedItem] = newResources.splice(draggedIndex.value, 1);
  newResources.splice(targetIndex, 0, draggedItem);

  mountedSystemResources.value = newResources;
  draggedIndex.value = null;
};

const handleDragEnd = () => {
  draggedIndex.value = null;
};

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

function handleRemoveMountedResource(resourceId: string) {
  const index = mountedSystemResources.value.findIndex(r => r.id === resourceId);
  if (index !== -1) {
    mountedSystemResources.value.splice(index, 1);
  }
}

function handleSaveSettings() {
  if (!props.chatData) return;
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning('会话名称不能为空');
    return;
  }

  const finalModelParameters: Record<string, any> = {
    max_context_messages: chatSettingsForm.modelParameters.max_context_messages,
    stream: chatSettingsForm.modelParameters.stream,
  };

  for (const key in chatSettingsForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, key)) {
      if (key === 'max_context_messages' || key === 'stream') {
        continue;
      }
      finalModelParameters[key] = chatSettingsForm.modelParameters[key];
    }
  }

  // 保存时使用当前 mountedSystemResources 的顺序
  const resourcePromptList = mountedSystemResources.value.map(r => r.id);

  emit('save', {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: finalModelParameters,
    resource_prompt_list: resourcePromptList.length > 0 ? resourcePromptList : null,
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

/* 挂载资源区域样式 */
.mounted-resources-wrapper {
  margin-top: 8px;
  background-color: var(--color-background-soft);
  padding: 4px;
  border-radius: 4px;
}

.mounted-resources-area {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Drag and Drop Styles */
.draggable-tag {
  cursor: grab;
  transition: all 0.3s ease;
}

.draggable-tag:active {
  cursor: grabbing;
}

.draggable-tag.is-dragging {
  opacity: 0.3;
  background-color: var(--el-color-info-light-8);
  border-style: dashed;
}

/* List Transitions */
.list-move,
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-leave-active {
  position: absolute;
}
</style>
