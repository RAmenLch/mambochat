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
                :avatar-url="resolveFileUrl(form.agentAvatarUrl) ?? null"
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
                      <el-option label="Deep Agent" value="DeepAgent" />
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

        <!-- 2. 模型配置 (保持不变) -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.modelConfig') }}</span>
          </template>

          <el-row :gutter="40">
            <el-col :span="12">
              <el-form-item :label="$t('agent.bindModel')">
                <el-select ref="modelSelectRef" v-model="form.aiModelId" :placeholder="$t('agent.modelPlaceholder')" style="width: 100%" clearable
                  @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, modelSelectRef)"
                >
                  <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
                    <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
                  </el-option-group>
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

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
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>{{ $t('chat.settings.enableSuggest') }}</span>
                  <el-tooltip effect="dark" :content="$t('chat.settings.enableSuggestTip')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.modelParameters.enable_suggest" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="40" v-if="form.aiModelId">
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>{{ $t('chat.settings.enableAskUser') }}</span>
                  <el-tooltip effect="dark" :content="$t('chat.settings.enableAskUserTip')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.modelParameters.enable_ask_user" />
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
                    @change="(val: string | number | boolean) => handleToggleParameter(param, val as boolean)"
                    class="parameter-switch"
                  />
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-card>

        <!-- 3. 设定与能力 -->
        <el-card shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.settingsAndResources') }}</span>
          </template>

          <!-- 第一行：系统提示词 & 挂载资源 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="12">
              <el-form-item :label="$t('agent.systemPrompt')">
                <el-input
                  v-model="form.systemPrompt"
                  type="textarea"
                  :rows="8"
                  :placeholder="$t('agent.sysPromptPlaceholder')"
                  class="prompt-textarea"
                />
              </el-form-item>
            </el-col>

            <el-col :span="12">
              <el-form-item :label="$t('agent.mountedResources')">
                <div class="mount-container">
                  <div class="mount-action">
                    <el-button type="primary" plain size="small" @click="resourceSelectorVisible = true">
                      <el-icon><Collection /></el-icon> {{ $t('agent.mountResource') }}
                    </el-button>
                  </div>
                  <div v-if="mountedResources.length > 0" class="tag-list-wrapper">
                    <MountedResourceTags v-model="mountedResources" color-by-type />
                  </div>
                  <div v-else class="empty-mount">
                    {{ $t('agent.noResources') }}
                  </div>
                </div>
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 第二行：MCP 工具 & 子 Agent -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="12">
              <el-form-item :label="$t('agent.enableMcp')">
                <div class="mount-container">
                  <div class="mount-action">
                    <el-dropdown trigger="click" @command="handleAddMcp" placement="bottom-start">
                      <el-button type="primary" plain size="small">
                        <el-icon><Connection /></el-icon> {{ $t('agent.mountMcp') }}
                      </el-button>
                      <template #dropdown>
                        <el-dropdown-menu class="mcp-dropdown-menu">
                          <el-dropdown-item v-for="mcp in availableMcps" :key="mcp.id" :command="mcp.id">
                            {{ mcp.name }}
                          </el-dropdown-item>
                          <el-dropdown-item v-if="availableMcps.length === 0" disabled>
                            {{ $t('common.noData') }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                  <div v-if="mountedMcpList.length > 0" class="tag-list-wrapper">
                    <el-tag
                      v-for="mcp in mountedMcpList"
                      :key="mcp.id"
                      closable
                      type="info"
                      effect="light"
                      class="custom-tag"
                      @close="handleRemoveMcp(mcp.id)"
                    >
                      <div class="tag-inner">
                        <el-icon class="tag-icon"><Connection /></el-icon>
                        <span class="tag-text">{{ mcp.name }}</span>
                      </div>
                    </el-tag>
                  </div>
                  <div v-else class="empty-mount">
                    {{ $t('agent.noMcp') }}
                  </div>
                </div>
              </el-form-item>
            </el-col>

            <el-col :span="12" v-if="form.AgentType === 'DeepAgent'">
              <el-form-item :label="$t('agent.subAgents')">
                <div class="mount-container">
                  <div class="mount-action">
                    <el-button type="primary" plain size="small" @click="agentSelectorVisible = true">
                      <el-icon><Plus /></el-icon> {{ $t('agent.mountSubAgent') }}
                    </el-button>
                  </div>
                  <div v-if="mountedSubAgents.length > 0" class="tag-list-wrapper">
                    <el-tag
                      v-for="subAgent in mountedSubAgents"
                      :key="subAgent.id"
                      closable
                      type="primary"
                      effect="light"
                      class="custom-tag"
                      @close="handleRemoveSubAgent(subAgent.id)"
                    >
                      <div class="tag-inner">
                        <el-avatar :size="14" :src="resolveFileUrl(subAgent.agentAvatarUrl) ?? undefined" :icon="User" class="tag-avatar" />
                        <span class="tag-text">{{ subAgent.name }}</span>
                      </div>
                    </el-tag>
                  </div>
                  <div v-else class="empty-mount">
                    {{ $t('agent.noSubAgents') }}
                  </div>
                </div>
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 第三行：Backend 挂载 (仅 DeepAgent 可见) -->
          <el-row :gutter="32" class="settings-row" v-if="form.AgentType === 'DeepAgent'">
            <el-col :span="24">
              <el-form-item :label="$t('agent.mountBackend')">
                <div class="mount-container" style="height: auto; min-height: 120px;">
                  <div class="mount-action" style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                    <el-dropdown trigger="click" @command="handleAddBackend" placement="bottom-start">
                      <el-button type="warning" plain size="small">
                        <el-icon><Monitor /></el-icon> {{ $t('agent.addBackend') }}
                      </el-button>
                      <template #dropdown>
                        <el-dropdown-menu class="mcp-dropdown-menu">
                          <el-dropdown-item v-for="b in availableBackends" :key="b.id" :command="b.id">
                            {{ b.name }} ({{ b.backendType }})
                          </el-dropdown-item>
                          <el-dropdown-item v-if="availableBackends.length === 0" disabled>
                            {{ $t('common.noData') }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                    <el-select
                      v-if="mountedBackendList.length > 0"
                      v-model="form.defaultBackendId"
                      clearable
                      :placeholder="$t('agent.selectDefaultBackend')"
                      size="small"
                      style="width: 220px;"
                    >
                      <el-option
                        v-for="b in mountedBackendList"
                        :key="b.id"
                        :label="`${b.name} (${b.backendType})`"
                        :value="b.id"
                      />
                    </el-select>
                  </div>
                  <div v-if="mountedBackendList.length > 0" class="tag-list-wrapper">
                    <el-tag
                      v-for="b in mountedBackendList"
                      :key="b.id"
                      closable
                      :type="b.id === form.defaultBackendId ? 'danger' : 'warning'"
                      effect="light"
                      class="custom-tag"
                      @close="handleRemoveBackend(b.id)"
                    >
                      <div class="tag-inner">
                        <el-icon class="tag-icon"><Monitor /></el-icon>
                        <span class="tag-text">{{ b.name }}</span>
                        <span v-if="b.id === form.defaultBackendId" class="default-star">★</span>
                      </div>
                    </el-tag>
                  </div>
                  <div v-else class="empty-mount">
                    {{ $t('agent.noBackend') }}
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
      :context="form.AgentType === 'DeepAgent' ? 'agent-deep' : 'agent-react'"
      @mount-resources="handleMountResources"
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
import { User, QuestionFilled, Collection, Plus, Connection, Monitor } from '@element-plus/icons-vue';
import { resolveFileUrl } from '@/services/electronUrl';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useBackendStore } from '@/stores/backendStore'; // [新增] 引入 BackendStore

import { uploadAgentAvatar, deleteAgentAvatar, getAgent } from '@/api/agentService';
import { getResourceDetails } from '@/api/resourceService';
import type { Resource, Agent } from '@/api/types';

import AvatarUploader from '../AvatarUploader.vue';
import ResourceSelectorDialog from '@/components/common/dialogs/ResourceSelectorDialog.vue';
import AgentSelectorDialog from './dialogs/AgentSelectorDialog.vue';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';
import { useModelSelectScroll } from '@/composables/useModelSelectScroll';

const { t } = useI18n();
const agentStore = useAgentStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const mcpStore = useMcpStore();
const backendStore = useBackendStore(); // [新增]

const { currentAgentId, agentList } = storeToRefs(agentStore);
const { groupedModels, allModels } = storeToRefs(providerStore);
const { activeUserMcpServices } = storeToRefs(mcpStore);
const { backendList } = storeToRefs(backendStore); // [新增]

const isSaving = ref(false);
const isAvatarLoading = ref(false);
const resourceSelectorVisible = ref(false);
const agentSelectorVisible = ref(false);
const modelSelectRef = ref();
const { scrollToTopIfStarred } = useModelSelectScroll();

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
  subAgents: [] as string[],
  backendIds: [] as string[], // [新增]
  defaultBackendId: null as string | null, // [新增] 默认 Backend
});

// --- Backend 挂载逻辑 [新增] ---
const availableBackends = computed(() => {
  return backendList.value.filter(b => !form.backendIds.includes(b.id));
});

const mountedBackendList = computed(() => {
  return form.backendIds.map(id => {
    return backendList.value.find(b => b.id === id) || { id, name: 'Unknown Backend', backendType: 'unknown' };
  });
});

function handleAddBackend(backendId: string) {
  if (!form.backendIds.includes(backendId)) {
    form.backendIds.push(backendId);
  }
}

function handleRemoveBackend(backendId: string) {
  form.backendIds = form.backendIds.filter(id => id !== backendId);
  if (form.defaultBackendId === backendId) {
    form.defaultBackendId = null;
  }
}
// --------------------

// --- MCP 挂载逻辑 ---
const availableMcps = computed(() => {
  return activeUserMcpServices.value.filter(mcp => !form.enabledMcpIds.includes(mcp.id));
});

const mountedMcpList = computed(() => {
  return form.enabledMcpIds.map(id => {
    return activeUserMcpServices.value.find(mcp => mcp.id === id) || { id, name: 'Unknown MCP' };
  });
});

function handleAddMcp(mcpId: string) {
  if (!form.enabledMcpIds.includes(mcpId)) {
    form.enabledMcpIds.push(mcpId);
  }
}

function handleRemoveMcp(mcpId: string) {
  form.enabledMcpIds = form.enabledMcpIds.filter(id => id !== mcpId);
}
// --------------------

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
      enable_suggest: params.enable_suggest ?? false,
      enable_ask_user: params.enable_ask_user ?? false,
    };

    form.agentAvatarUrl = newVal.agentAvatarUrl || null;
    form.enabledMcpIds = newVal.enabledMcpIds ? [...newVal.enabledMcpIds] : [];
    form.subAgents = newVal.subAgents ? [...newVal.subAgents] : [];
    form.backendIds = newVal.backendIds ? [...newVal.backendIds] : []; // [新增] 还原 Backend 绑定数据
    form.defaultBackendId = (newVal as any).defaultBackendId || null; // [新增] 还原默认 Backend

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
  const keysToKeep = new Set(['max_context_messages', 'stream', 'enable_suggest', 'enable_ask_user', 'temperature', 'top_p']);

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
      enable_suggest: form.modelParameters.enable_suggest,
      enable_ask_user: form.modelParameters.enable_ask_user,
    };

    for (const key in form.modelParameters) {
      if (Object.prototype.hasOwnProperty.call(form.modelParameters, key)) {
        if (key === 'max_context_messages' || key === 'stream') continue;
        finalModelParameters[key] = form.modelParameters[key];
      }
    }

    // [修复] 1. 解除 Proxy 包装，防止序列化为空数组
    // [修复] 2. 无论清空还是切换 AgentType，都显式发送 [] 让后端清空数据，而不是发送 null
    const finalBackendIds = form.AgentType === 'DeepAgent' ? [...form.backendIds] : [];

    await agentStore.updateAgentSettings(currentAgentId.value, {
      name: form.name,
      description: form.description,
      AgentType: form.AgentType as any,
      systemPrompt: form.systemPrompt,
      aiModelId: form.aiModelId,
      modelParameters: finalModelParameters,

      // 建议顺手把这里的其他数组也加上展开运算符 [...array] 和 [] 回退，防止遇到同样的 Bug
      resourcePromptList: resourcePromptList.length > 0 ? [...resourcePromptList] : [],
      enabledMcpIds: form.enabledMcpIds.length > 0 ? [...form.enabledMcpIds] : [],
      subAgents: form.AgentType === 'DeepAgent' && form.subAgents.length > 0 ? [...form.subAgents] : [],

      backendIds: finalBackendIds, // 使用修复后的变量
      defaultBackendId: form.defaultBackendId, // [新增] 默认 Backend
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
  if (backendStore.backendList.length === 0) {
    backendStore.fetchBackends(); // [新增] 初始化拉取 Backend 列表
  }
});
</script>

<style scoped>
/* (原有样式保持不变，截取主要部分) */
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
  box-sizing: border-box;
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
  font-size: 16px;
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

/* 设定与知识 2x2 布局样式 */
.settings-row {
  margin-bottom: 20px;
}
.settings-row:last-child {
  margin-bottom: 0;
}

.prompt-textarea {
  height: 100%;
}
:deep(.prompt-textarea .el-textarea__inner) {
  height: 190px;
}

/* 统一的挂载容器样式 */
.mount-container {
  width: 100%;
  height: 190px;
  background-color: var(--color-background-soft);
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  padding: 12px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.mount-action {
  margin-bottom: 12px;
  flex-shrink: 0;
}

/* Tag 流式布局 */
.tag-list-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}
.custom-tag {
  height: 28px;
  padding: 0 8px;
  border-radius: 4px;
}
.tag-inner {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tag-icon {
  font-size: 14px;
}
.tag-avatar {
  background-color: transparent;
}
.tag-text {
  font-size: 13px;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-mount {
  flex-grow: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}
.mcp-dropdown-menu {
  max-height: 250px;
  overflow-y: auto;
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
</style>
