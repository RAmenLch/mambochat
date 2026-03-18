<!-- frontend/mambo/src/components/settings/agent/AgentEditor.vue -->
<template>
  <div class="agent-editor" v-if="agentData">
    <div class="editor-header">
      <div class="header-title">
        <h2>{{ agentData.name }}</h2>
        <el-tag size="small" type="info" effect="plain">{{ agentData.AgentType }}</el-tag>
      </div>
      <el-button type="primary" @click="handleSave" :loading="isSaving">{{ $t('common.action.save') }}</el-button>
    </div>

    <el-scrollbar class="editor-body">
      <el-form :model="form" label-position="top" class="editor-form">

        <!-- 1. 基本信息 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.basicInfo') }}</span>
          </template>
          <div class="basic-info-layout">
            <div class="avatar-section">
              <AvatarUploader
                :title="$t('agent.avatar')"
                :avatar-url="form.agentAvatarUrl"
                :icon="User"
                :is-loading="isAvatarLoading"
                @upload="handleUploadAvatar"
                @delete="handleDeleteAvatar"
              />
            </div>
            <div class="info-section">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item :label="$t('agent.name')">
                    <el-input v-model="form.name" :placeholder="$t('agent.namePlaceholder')" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item :label="$t('agent.type')">
                    <el-select v-model="form.AgentType" style="width: 100%">
                      <el-option label="ReAct Agent" value="ReActAgent" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="24">
                  <el-form-item :label="$t('agent.description')">
                    <el-input v-model="form.description" type="textarea" :rows="2" :placeholder="$t('agent.descPlaceholder')" />
                  </el-form-item>
                </el-col>
              </el-row>
            </div>
          </div>
        </el-card>

        <!-- 2. 设定与资源挂载 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <div class="card-header-with-action">
              <span class="card-title">{{ $t('agent.settingsAndResources') }}</span>
              <el-button type="primary" link @click="resourceSelectorVisible = true">
                <el-icon><Collection /></el-icon> {{ $t('agent.mountResource') }}
              </el-button>
            </div>
          </template>

          <el-form-item :label="$t('agent.systemPrompt')">
            <el-input
              v-model="form.systemPrompt"
              type="textarea"
              :rows="6"
              :placeholder="$t('agent.sysPromptPlaceholder')"
            />
          </el-form-item>

          <div v-if="mountedResources.length > 0" class="mounted-resources-wrapper">
            <div class="wrapper-title">{{ $t('agent.mountedResources') }}</div>
            <MountedResourceTags v-model="mountedResources" color-by-type />
          </div>
        </el-card>

        <!-- 3. 模型配置 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.modelConfig') }}</span>
          </template>

          <el-form-item :label="$t('agent.bindModel')">
            <el-select v-model="form.aiModelId" :placeholder="$t('agent.modelPlaceholder')" style="width: 100%" clearable>
              <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
                <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
              </el-option-group>
            </el-select>
          </el-form-item>

          <el-row :gutter="40" v-if="form.aiModelId">
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.contextMessages') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.contextMessagesTip')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.modelParameters.max_context_messages"
                  :min="0"
                  :step="2"
                  controls-position="right"
                  style="width: 100%;"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.streamOutput') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.streamOutputTip')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.modelParameters.stream" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="40" v-if="form.aiModelId">
            <el-col :span="12" v-for="param in dynamicParameters" :key="param.key">
              <el-form-item>
                <template #label>
                  <span>{{ param.label }}</span>
                  <el-tooltip effect="dark" :content="param.description" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <div class="parameter-control-wrapper">
                  <el-slider
                    v-if="param.type === 'number'"
                    v-model="form.modelParameters[param.key]"
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
                    v-model="form.modelParameters[param.key]"
                    :min="!Array.isArray(param.limit) ? param.limit?.min : undefined"
                    :max="!Array.isArray(param.limit) ? param.limit?.max : undefined"
                    :disabled="!param.isEnabled"
                    controls-position="right"
                    class="parameter-input"
                  />
                  <el-switch
                    v-else-if="param.type === 'boolean'"
                    v-model="form.modelParameters[param.key]"
                    :disabled="!param.isEnabled"
                    class="parameter-input"
                  />
                  <el-switch
                    :model-value="param.isEnabled"
                    @change="val => handleToggleParameter(param, val as boolean)"
                    class="parameter-switch"
                  />
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-card>

        <!-- 4. 高级配置 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.advancedConfig') }}</span>
          </template>

          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item :label="$t('agent.enableMcp')">
                <el-select
                  v-model="form.enabledMcpIds"
                  multiple
                  :placeholder="$t('agent.mcpPlaceholder')"
                  style="width: 100%"
                >
                  <el-option
                    v-for="tool in activeUserMcpServices"
                    :key="tool.id"
                    :label="tool.name"
                    :value="tool.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('agent.agentParams')">
                <el-input disabled :placeholder="$t('agent.reservedInterface')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('agent.subAgents')">
                <div class="sub-agents-wrapper">
                  <el-button type="primary" link @click="agentSelectorVisible = true">
                    <el-icon><Plus /></el-icon> {{ $t('agent.mountSubAgent') }}
                  </el-button>
                  <div v-if="mountedSubAgents.length > 0" class="mounted-sub-agents">
                    <el-tag
                      v-for="subAgent in mountedSubAgents"
                      :key="subAgent.id"
                      closable
                      @close="handleRemoveSubAgent(subAgent.id)"
                      class="sub-agent-tag"
                    >
                      {{ subAgent.name }}
                    </el-tag>
                  </div>
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-card>

      </el-form>
    </el-scrollbar>

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      source="settings"
      @mount-resources="handleMountResources"
      @mount-knowledge-base="handleMountResources"
    />

    <AgentSelectorDialog
      v-if="currentAgentId"
      v-model:visible="agentSelectorVisible"
      :current-agent-id="currentAgentId"
      :initial-selected-ids="form.subAgents"
      @select="handleMountSubAgents"
    />
  </div>

  <div v-else class="empty-state">
    <el-empty :description="$t('agent.emptyState')" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { User, QuestionFilled, Collection, Plus } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useMcpStore } from '@/stores/mcpStore';

import { uploadAgentAvatar, deleteAgentAvatar, getAgent } from '@/api/agentService';
import { getResourceDetails } from '@/api/resourceService';
import type { Resource, Agent } from '@/api/types';

import AvatarUploader from '../AvatarUploader.vue';
import ResourceSelectorDialog from '@/components/chat/dialogs/ResourceSelectorDialog.vue';
import AgentSelectorDialog from './dialogs/AgentSelectorDialog.vue';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';

const { t } = useI18n();
const agentStore = useAgentStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const mcpStore = useMcpStore();

const { currentAgentId, agentList } = storeToRefs(agentStore);
const { groupedModels, allModels } = storeToRefs(providerStore);
const { activeUserMcpServices } = storeToRefs(mcpStore);

const isSaving = ref(false);
const isAvatarLoading = ref(false);
const resourceSelectorVisible = ref(false);
const agentSelectorVisible = ref(false);

const agentData = computed(() => agentList.value.find(a => a.id === currentAgentId.value));

const mountedResources = ref<Resource[]>([]);
const mountedSubAgents = ref<Agent[]>([]);

const form = reactive({
  name: '',
  description: '',
  AgentType: 'ReActAgent',
  systemPrompt: '',
  aiModelId: null as string | null,
  modelParameters: {} as Record<string, any>,
  agentAvatarUrl: null as string | null,
  enabledMcpIds: [] as string[],
  subAgents: [] as string[]
});

const filteredGroupedModels = computed(() => {
  return groupedModels.value
    .map(group => ({ label: group.label, options: group.options.filter(m => m.model_type === 'chat') }))
    .filter(group => group.options.length > 0);
});

const dynamicParameters = computed(() => {
  if (!form.aiModelId) return [];
  const currentModel = allModels.value.find(m => m.id === form.aiModelId);
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? []);
  const coreParameters = ['temperature', 'top_p'];

  return systemConfigStore.llmParameters
    .filter(p => coreParameters.includes(p.key) || supportedParameters.has(p.key) || p.default_activate)
    .map(p => ({
      key: p.key,
      label: p.label,
      description: p.description,
      type: p.type,
      limit: p.limit,
      isEnabled: Object.prototype.hasOwnProperty.call(form.modelParameters, p.key),
      definition: p
    }));
});

watch(agentData, async (newVal) => {
  if (newVal) {
    form.name = newVal.name;
    form.description = newVal.description || '';
    form.AgentType = newVal.AgentType || 'ReActAgent';
    form.systemPrompt = newVal.systemPrompt || '';
    form.aiModelId = newVal.aiModelId || null;

    const params = newVal.modelParameters ? JSON.parse(JSON.stringify(newVal.modelParameters)) : {};
    form.modelParameters = {
      ...params,
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
    };

    form.agentAvatarUrl = newVal.agentAvatarUrl || null;
    form.enabledMcpIds = newVal.enabledMcpIds ? [...newVal.enabledMcpIds] : [];
    form.subAgents = newVal.subAgents ? [...newVal.subAgents] : [];

    if (newVal.resourcePromptList && newVal.resourcePromptList.length > 0) {
      try {
        const promises = newVal.resourcePromptList.map(id => getResourceDetails(id));
        const results = await Promise.all(promises);
        mountedResources.value = results.filter(r => !!r) as Resource[];
      } catch (error) {
        console.error('Failed to load agent resources:', error);
        mountedResources.value = [];
      }
    } else {
      mountedResources.value = [];
    }

    if (newVal.subAgents && newVal.subAgents.length > 0) {
      try {
        const promises = newVal.subAgents.map(id => getAgent(id));
        const results = await Promise.all(promises);
        mountedSubAgents.value = results.filter(r => !!r) as Agent[];
      } catch (error) {
        console.error('Failed to load sub agents:', error);
        mountedSubAgents.value = [];
      }
    } else {
      mountedSubAgents.value = [];
    }
  }
}, { immediate: true, deep: true });

watch(() => form.aiModelId, (newModelId) => {
  if (!newModelId) return;
  const currentModel = allModels.value.find(m => m.id === newModelId);
  if (!currentModel) return;

  const supportedParams = new Set(currentModel.meta_config?.supported_parameters ?? []);
  const keysToKeep = new Set(['max_context_messages', 'stream', 'temperature', 'top_p']);

  systemConfigStore.llmParameters.forEach(p => {
    if (supportedParams.has(p.key) || p.default_activate) keysToKeep.add(p.key);
  });

  const newParams: Record<string, any> = {};
  for (const key in form.modelParameters) {
    if (keysToKeep.has(key)) newParams[key] = form.modelParameters[key];
  }
  form.modelParameters = newParams;
});

function getSliderStep(min: number, max: number): number {
  const range = max - min;
  if (range <= 2) return 0.01;
  if (range <= 20) return 0.1;
  return 1;
}

function handleToggleParameter(param: any, isEnabled: boolean) {
  const newParams = { ...form.modelParameters };
  if (isEnabled) newParams[param.key] = param.definition.default_value;
  else delete newParams[param.key];
  form.modelParameters = newParams;
}

function handleMountResources(resources: Resource[]) {
  if (resources.length === 0) return;
  const existingIds = new Set(mountedResources.value.map(r => r.id));
  const newResources = resources.filter(r => !existingIds.has(r.id));

  if (newResources.length > 0) {
    mountedResources.value = [...mountedResources.value, ...newResources];
    ElMessage.success(t('common.msg.updateSuccess'));
  }
}

function handleMountSubAgents(agents: Agent[]) {
  mountedSubAgents.value = agents;
  form.subAgents = agents.map(a => a.id);
}

function handleRemoveSubAgent(id: string) {
  mountedSubAgents.value = mountedSubAgents.value.filter(a => a.id !== id);
  form.subAgents = mountedSubAgents.value.map(a => a.id);
}

async function handleUploadAvatar(file: File) {
  if (!currentAgentId.value) return;
  isAvatarLoading.value = true;
  try {
    const response = await uploadAgentAvatar(currentAgentId.value, file);
    form.agentAvatarUrl = response.url;
    if (agentData.value) {
      agentData.value.agentAvatarUrl = response.url;
      agentData.value.agentAvatarId = response.id;
    }
    ElMessage.success(t('agent.avatarUploadSuccess'));
  } catch (error) {
    ElMessage.error(t('agent.avatarUploadFailed'));
  } finally {
    isAvatarLoading.value = false;
  }
}

async function handleDeleteAvatar() {
  if (!currentAgentId.value) return;
  isAvatarLoading.value = true;
  try {
    await deleteAgentAvatar(currentAgentId.value);
    form.agentAvatarUrl = null;
    if (agentData.value) {
      agentData.value.agentAvatarUrl = null;
      agentData.value.agentAvatarId = null;
    }
    ElMessage.success(t('agent.avatarDeleteSuccess'));
  } catch (error) {
    ElMessage.error(t('agent.avatarDeleteFailed'));
  } finally {
    isAvatarLoading.value = false;
  }
}

async function handleSave() {
  if (!currentAgentId.value) return;
  isSaving.value = true;
  try {
    const resourcePromptList = mountedResources.value.map(r => r.id);

    const finalModelParameters: Record<string, any> = {
      max_context_messages: form.modelParameters.max_context_messages,
      stream: form.modelParameters.stream,
    };

    for (const key in form.modelParameters) {
      if (Object.prototype.hasOwnProperty.call(form.modelParameters, key)) {
        if (key === 'max_context_messages' || key === 'stream') continue;
        finalModelParameters[key] = form.modelParameters[key];
      }
    }

    await agentStore.updateAgentSettings(currentAgentId.value, {
      name: form.name,
      description: form.description,
      AgentType: form.AgentType as any,
      systemPrompt: form.systemPrompt,
      aiModelId: form.aiModelId,
      modelParameters: finalModelParameters,
      resourcePromptList: resourcePromptList.length > 0 ? resourcePromptList : null,
      enabledMcpIds: form.enabledMcpIds.length > 0 ? form.enabledMcpIds : null,
      subAgents: form.subAgents.length > 0 ? form.subAgents : null
    });
    ElMessage.success(t('agent.saveSuccess'));
  } catch (error) {
    ElMessage.error(t('agent.saveFailed'));
  } finally {
    isSaving.value = false;
  }
}

onMounted(() => {
  providerStore.fetchProviders();
  systemConfigStore.fetchSystemConfig();
});
</script>

<style scoped>
/* 保持原有样式不变，追加子 Agent 的样式 */
.agent-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--color-background-soft);
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.editor-body {
  flex-grow: 1;
  padding: 24px;
}

.config-card {
  margin-bottom: 24px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.basic-info-layout {
  display: flex;
  gap: 32px;
  align-items: flex-start;
}
.avatar-section {
  flex-shrink: 0;
  padding-top: 8px;
}
.info-section {
  flex-grow: 1;
}

.mounted-resources-wrapper {
  margin-top: 16px;
  padding: 16px;
  background-color: var(--color-background-soft);
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
}
.wrapper-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  font-weight: 600;
}

.label-icon {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
  cursor: help;
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

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  background-color: var(--el-bg-color);
}

.sub-agents-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.mounted-sub-agents {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sub-agent-tag {
  margin-right: 8px;
}
</style>
