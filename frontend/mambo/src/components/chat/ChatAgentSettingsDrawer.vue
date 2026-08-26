<!-- frontend/mambo/src/components/chat/ChatAgentSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    :title="$t('chat.settings.title')"
    direction="rtl"
    size="500px"
    @update:model-value="handleUpdateModelValue"
    @close="handleDrawerClose"
  >
    <div class="drawer-content">
      <el-form v-if="chatData" :model="form" label-position="top">
        <el-form-item :label="$t('chat.settings.name')">
          <el-input v-model.trim="form.name" :placeholder="$t('chat.settings.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('chat.settings.bindAgent')">
          <el-select v-model="form.agentId" style="width: 100%">
            <el-option
              v-for="agent in agentOptions"
              :key="agent.value"
              :label="agent.label"
              :value="agent.value"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-divider border-style="dashed">
        <span class="preview-divider-title">{{ $t('chat.settings.agentInfoPreview') }}</span>
      </el-divider>

      <el-scrollbar class="agent-preview-scrollbar" v-if="selectedAgent">
        <div class="agent-preview-container">

          <div class="preview-section">
            <div class="agent-header">
              <el-avatar
                :size="48"
                :src="resolveFileUrl(selectedAgent.agentAvatarUrl) || ''"
                :icon="User"
                class="agent-avatar"
              />
              <div class="agent-title-info">
                <div class="agent-name-row">
                  <span
                    class="agent-name clickable-agent"
                    @click="openAgentSettings(selectedAgent.id)"
                    :title="$t('common.action.edit')"
                  >
                    {{ selectedAgent.name }}
                  </span>
                  <el-tag size="small" type="info" effect="plain">{{ selectedAgent.AgentType }}</el-tag>
                </div>
                <div class="agent-desc" :title="selectedAgent.description || ''">
                  {{ selectedAgent.description || $t('common.none') }}
                </div>
              </div>
            </div>
          </div>

          <div class="preview-section">
            <div class="section-title"><el-icon><Cpu /></el-icon> {{ $t('agent.modelConfig') }}</div>
            <el-form :model="modelForm" label-position="top" class="model-config-form">
              <el-form-item :label="$t('agent.bindModel')">
                <el-select
                  v-model="modelForm.aiModelId"
                  :placeholder="$t('agent.modelPlaceholder')"
                  style="width: 100%"
                  clearable
                >
                  <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
                    <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
                  </el-option-group>
                </el-select>
                <el-tag v-if="isModelDeleted" size="small" type="warning" effect="light" class="deleted-model-tag">
                  {{ $t('common.status.deleted') }}
                </el-tag>
              </el-form-item>
              <el-form-item :label="$t('agent.contextMessages')">
                <el-input-number
                  v-model="modelForm.modelParameters.max_context_messages"
                  :min="0"
                  :step="2"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item :label="$t('agent.streamOutput')">
                <el-switch v-model="modelForm.modelParameters.stream" />
              </el-form-item>
              <el-form-item :label="$t('chat.settings.enableSuggest')">
                <el-switch v-model="modelForm.modelParameters.enable_suggest" />
              </el-form-item>
              <el-form-item :label="$t('chat.settings.enableAskUser')">
                <el-switch v-model="modelForm.modelParameters.enable_ask_user" />
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
                  <el-slider
                    v-if="param.type === 'number'"
                    v-model="modelForm.modelParameters[param.key]"
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
                    v-model="modelForm.modelParameters[param.key]"
                    :min="!Array.isArray(param.limit) ? param.limit?.min : undefined"
                    :max="!Array.isArray(param.limit) ? param.limit?.max : undefined"
                    :disabled="!param.isEnabled"
                    controls-position="right"
                    class="parameter-input"
                  />
                  <el-select
                    v-else-if="param.type === 'string' && Array.isArray(param.limit)"
                    v-model="modelForm.modelParameters[param.key]"
                    :disabled="!param.isEnabled"
                    class="parameter-input"
                  >
                    <el-option v-for="opt in param.limit" :key="opt" :label="opt" :value="opt" />
                  </el-select>
                  <el-input
                    v-else-if="param.type === 'string'"
                    v-model="modelForm.modelParameters[param.key]"
                    :disabled="!param.isEnabled"
                    class="parameter-input"
                  />
                  <el-switch
                    v-else-if="param.type === 'boolean'"
                    v-model="modelForm.modelParameters[param.key]"
                    :disabled="!param.isEnabled"
                    class="parameter-input"
                  />
                  <el-switch
                    :model-value="param.isEnabled"
                    @change="(isEnabled: string | number | boolean) => handleToggleParameter(param, isEnabled as boolean)"
                    class="parameter-switch"
                  />
                </div>
              </el-form-item>
            </el-form>
          </div>

          <div class="preview-section">
            <div class="section-title"><el-icon><Document /></el-icon> {{ $t('agent.systemPrompt') }}</div>
            <div class="prompt-box">
              {{ selectedAgent.systemPrompt || $t('common.none') }}
            </div>
          </div>

          <div class="preview-section ext-section">
            <div class="section-title"><el-icon><MagicStick /></el-icon> {{ $t('agent.settingsAndResources') }}</div>

            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.mountedResources') }}:</div>
              <div class="ext-tags" v-if="previewResources.length > 0">
                <MountedResourceTags :model-value="previewResources" color-by-type readonly />
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
            </div>

            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.enableMcp') }}:</div>
              <div class="ext-tags" v-if="displayMcpList.length > 0">
                <el-tag v-for="mcp in displayMcpList" :key="mcp.id" size="small" :type="mcp.name === t('common.status.unknownMcp') ? 'info' : undefined" :class="{ 'deleted-tag': mcp.name === t('common.status.unknownMcp') }" effect="light">
                  <el-icon><Connection /></el-icon> {{ mcp.name === t('common.status.unknownMcp') ? mcp.name + ' (ID: ' + mcp.id.substring(0, 8) + '...)' : mcp.name }}
                </el-tag>
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
            </div>

            <div class="ext-item" v-if="selectedAgent.AgentType === 'DeepAgent' || selectedAgent.AgentType === 'Mambo'">
              <div class="ext-label">{{ $t('agent.mountBackend') }}:</div>
              <div class="ext-tags" v-if="displayBackendList.length > 0">
                <el-tag
                  v-for="b in displayBackendList"
                  :key="b.id"
                  size="small"
                  :type="b.name === t('common.status.unknownBackend') ? 'info' : (b.id === defaultBackendId ? 'danger' : 'warning')"
                  effect="light"
                  :class="{ 'deleted-tag': b.name === t('common.status.unknownBackend') }"
                >
                  <el-icon><Monitor /></el-icon> {{ b.name === t('common.status.unknownBackend') ? b.name + ' (ID: ' + b.id.substring(0, 8) + '...)' : b.name }}
                  <span v-if="b.id === defaultBackendId && b.name !== t('common.status.unknownBackend')" class="default-star">★</span>
                </el-tag>
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
            </div>

            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.subAgents') }}:</div>
              <div class="ext-tags" v-if="displaySubAgents.length > 0">
                <el-tag
                  v-for="sub in displaySubAgents"
                  :key="sub.id"
                  size="small"
                  type="primary"
                  effect="light"
                  :class="{ 'clickable-tag custom-agent-tag': sub.name !== t('common.status.unknownAgent'), 'deleted-tag': sub.name === t('common.status.unknownAgent') }"
                  @click="sub.name !== t('common.status.unknownAgent') && openAgentSettings(sub.id)"
                  :title="sub.name !== t('common.status.unknownAgent') ? $t('common.action.edit') : $t('resource.deletedTooltip')"
                >
                  <div class="tag-inner">
                    <el-avatar v-if="sub.avatar && sub.name !== t('common.status.unknownAgent')" :size="14" :src="resolveFileUrl(sub.avatar) ?? undefined" class="tag-avatar" />
                    <el-icon v-else><User /></el-icon>
                    <span>{{ sub.name === t('common.status.unknownAgent') ? sub.name + ' (ID: ' + sub.id.substring(0, 8) + '...)' : sub.name }}</span>
                  </div>
                </el-tag>
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
            </div>
          </div>

          <!-- Mambo 专属配置预览 -->
          <div class="preview-section" v-if="selectedAgent.AgentType === 'Mambo' && mamboPreview">
            <div class="section-title"><el-icon><Setting /></el-icon> {{ $t('agent.mamboConfig') }}</div>
            <div class="mambo-preview-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.generalPurpose') }}:</span>
                <span class="info-value">{{ mamboPreview.generalPurpose ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">{{ $t('agent.mamboPlanning') }}:</span>
                <span class="info-value">{{ mamboPreview.planningEnabled ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
            </div>
            <div class="mambo-preview-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.mamboShow') }}:</span>
                <span class="info-value">{{ mamboPreview.showEnabled ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
            </div>
            <div class="mambo-preview-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.mamboMemory') }}:</span>
                <span class="info-value">{{ mamboPreview.memoryEnabled ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">{{ $t('agent.summarization') }}:</span>
                <span class="info-value">{{ mamboPreview.summaryEnabled ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
            </div>
            <div class="mambo-preview-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.versionControl') }}:</span>
                <span class="info-value">
                  <el-tag v-if="mamboPreview.versionControlEnabled" size="small" type="success" effect="light">
                    {{ $t('common.status.enabled') }}
                  </el-tag>
                  <span v-else>{{ $t('common.status.disabled') }}</span>
                </span>
              </div>
            </div>
            <div v-if="mamboPreview.memoryEnabled && displayMemoryResources.length > 0" class="ext-item" style="margin-top: 12px;">
              <div class="ext-label">{{ $t('agent.memoryResources') }}:</div>
              <div class="ext-tags">
                <el-tag v-for="res in displayMemoryResources" :key="res.id" size="small" type="success" effect="light">
                  {{ res.name }}
                </el-tag>
              </div>
            </div>
            <template v-if="mamboPreview.summaryEnabled && mamboPreview.summaryConfig">
              <div class="mambo-preview-grid" style="margin-top: 12px;">
                <div class="info-item">
                  <span class="info-label">{{ $t('agent.summarizationTrigger') }}:</span>
                  <span class="info-value">{{ mamboTriggerLabel }} ({{ mamboPreview.summaryConfig.trigger_value }})</span>
                </div>
                <div class="info-item">
                  <span class="info-label">{{ $t('agent.summarizationKeep') }}:</span>
                  <span class="info-value">{{ mamboKeepLabel }} ({{ mamboPreview.summaryConfig.keep_value }})</span>
                </div>
              </div>
              <div class="mambo-preview-grid" style="margin-top: 12px;">
                <div class="info-item">
                  <span class="info-label">{{ $t('agent.summarizationOffload') }}:</span>
                  <span class="info-value">{{ mamboPreview.summaryConfig.offload_to_backend ? t('common.status.enabled') : t('common.status.disabled') }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- Mambo 任务循环预览 -->
          <div class="preview-section" v-if="goalLoopPreview">
            <div class="section-title"><el-icon><Aim /></el-icon> {{ $t('agent.goalLoop.title') }}</div>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.goalLoop.mode') }}:</span>
                <span class="info-value">{{ goalLoopModeLabel }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">{{ $t('agent.goalLoop.maxRounds') }}:</span>
                <span class="info-value">{{ goalLoopPreview.max_rounds }}</span>
              </div>
              <div class="info-item" v-if="goalLoopPreview.mode === 'llm' && goalLoopPreview.blocked_threshold != null">
                <span class="info-label">{{ $t('agent.goalLoop.blockedThreshold') }}:</span>
                <span class="info-value">{{ goalLoopPreview.blocked_threshold }}</span>
              </div>
            </div>
            <template v-if="goalLoopPreview.mode === 'preset'">
              <div class="info-item goal-objective-item" v-if="goalLoopPreview.objective">
                <span class="info-label">{{ $t('agent.goalLoop.objective') }}:</span>
                <span class="info-value goal-objective">{{ goalLoopPreview.objective }}</span>
              </div>
              <div class="ext-item" v-if="goalLoopPreview.conditions && goalLoopPreview.conditions.length > 0">
                <div class="ext-label">{{ $t('agent.goalLoop.conditions') }}:</div>
                <div class="ext-tags">
                  <el-tag v-for="(cond, idx) in goalLoopPreview.conditions" :key="idx" size="small" type="primary" effect="light">
                    {{ cond.tool }} × {{ cond.times }}{{ t('agent.goalLoop.conditionTimesSuffix') }}
                    <span v-if="cond.args && Object.keys(cond.args).length > 0" class="goal-condition-args">
                      ({{ Object.entries(cond.args).map(([k, v]) => `${k}=${v}`).join(', ') }})
                    </span>
                  </el-tag>
                </div>
              </div>
            </template>
          </div>

          <!-- Mambo 安全审核预览 -->
          <div class="preview-section" v-if="selectedAgent.AgentType === 'Mambo' && securityReviewPreview">
            <div class="section-title"><el-icon><WarningFilled /></el-icon> {{ $t('agent.securityReview') }}</div>
            <div class="mambo-preview-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.securityReviewEnable') }}:</span>
                <span class="info-value">{{ securityReviewPreview.enabled ? t('common.status.enabled') : t('common.status.disabled') }}</span>
              </div>
              <div class="info-item" v-if="securityReviewPreview.enabled && securityReviewPreview.model_name">
                <span class="info-label">{{ $t('agent.securityReviewModel') }}:</span>
                <span class="info-value">{{ securityReviewPreview.model_name }}</span>
              </div>
            </div>
            <div v-if="securityReviewPreview.enabled && securityReviewPreview.review_tools && securityReviewPreview.review_tools.length > 0" class="ext-item" style="margin-top: 12px;">
              <div class="ext-label">{{ $t('agent.securityReviewTools') }}:</div>
              <div class="ext-tags">
                <el-tag v-for="tool in securityReviewPreview.review_tools" :key="tool" size="small" type="danger" effect="light">
                  {{ tool }}
                </el-tag>
              </div>
            </div>
          </div>

        </div>
      </el-scrollbar>
      <div v-else class="empty-agent-preview">
        <el-empty :description="$t('common.rule.selectRequired')" :image-size="60" />
      </div>

    </div>
    <template #footer>
      <div style="flex: auto">
        <el-button @click="emit('update:visible', false)">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveSettings">{{ $t('common.action.save') }}</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, watch, computed, ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, Cpu, Document, MagicStick, Collection, Connection, Monitor, Setting, WarningFilled, Aim, QuestionFilled } from '@element-plus/icons-vue';
import { resolveFileUrl } from '@/services/electronUrl';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useBackendStore } from '@/stores/backendStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { getResourceDetails } from '@/api/resourceService';
import { updateAgent } from '@/api/agentService';
import type { Chat, ChatUpdate, Resource, Agent, GoalLoopConfig, LLMParameterDefinition } from '@/api/types';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';
import { isDefaultChatName } from '@/utils/chatName';

const props = defineProps<{
  visible: boolean;
  chatData: Chat | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'close'): void;
  (e: 'save', settings: ChatUpdate): void;
}>();

const { t } = useI18n();
const router = useRouter();
const agentStore = useAgentStore();
const providerStore = useProviderStore();
const mcpStore = useMcpStore();
const backendStore = useBackendStore();
const systemConfigStore = useSystemConfigStore();

const form = reactive({
  name: '',
  agentId: '' as string | null,
});

/** 模型配置编辑表单（保存至 Agent，全局生效） */
interface DynamicParameterUI {
  key: string;
  label: string;
  description: string;
  type: 'integer' | 'number' | 'string' | 'boolean';
  limit?: Array<string | number> | { min?: number; max?: number; };
  isEnabled: boolean;
  definition: LLMParameterDefinition;
}

const modelForm = reactive<{
  aiModelId: string | null;
  modelParameters: Record<string, any>;
}>({
  aiModelId: null,
  modelParameters: {},
});

const previewResources = ref<Resource[]>([]);

const agentOptions = computed(() => {
  return agentStore.allAgents
    .filter(a => a.itemType === 'agent')
    .map(a => ({
      label: a.name,
      value: a.id
    }));
});

const selectedAgent = computed(() => {
  if (!form.agentId) return null;
  return agentStore.allAgents.find(a => a.id === form.agentId) || null;
});

const filteredGroupedModels = computed(() => {
  return providerStore.groupedModels
    .map(group => ({ label: group.label, options: group.options.filter(m => m.model_type === 'chat') }))
    .filter(group => group.options.length > 0);
});

const isModelDeleted = computed(() => {
  if (!selectedAgent.value?.aiModelId) return false;
  return !providerStore.allModels.find(m => m.id === selectedAgent.value!.aiModelId);
});

const dynamicParameters = computed((): DynamicParameterUI[] => {
  if (!modelForm.aiModelId) return [];
  const currentModel = providerStore.allModels.find(m => m.id === modelForm.aiModelId);
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
      isEnabled: Object.prototype.hasOwnProperty.call(modelForm.modelParameters, paramDef.key),
      definition: paramDef,
    }));
});

const displayMcpList = computed(() => {
  const mcpIds = selectedAgent.value?.enabledMcpIds || [];
  return mcpIds.map(id => {
    const mcp = mcpStore.activeUserMcpServices.find(m => m.id === id);
    return mcp ? { id, name: mcp.name } : { id, name: t('common.status.unknownMcp') };
  });
});

const displayBackendList = ref<Array<{ id: string; name: string }>>([]);

// [修改] 异步按 ID 兜底解析：缓存未命中时回源拉取，避免新导入的 Backend 显示"未知 Backend"
watch(
  () => (selectedAgent.value?.backendIds ? [...selectedAgent.value.backendIds] : []),
  async (bIds) => {
    const resolved: Array<{ id: string; name: string }> = [];
    for (const id of bIds) {
      const b = backendStore.backendList.find(x => x.id === id) || await backendStore.ensureBackend(id);
      resolved.push(b ? { id, name: b.name } : { id, name: t('common.status.unknownBackend') });
    }
    displayBackendList.value = resolved;
  },
  { immediate: true }
);

const displaySubAgents = computed(() => {
  const subIds = selectedAgent.value?.subAgents || [];
  return subIds.map(id => {
    const agent = agentStore.allAgents.find(a => a.id === id);
    return agent ? { id, name: agent.name, avatar: resolveFileUrl(agent.agentAvatarUrl) } : { id, name: t('common.status.unknownAgent'), avatar: null };
  });
});

// --- Mambo 专属配置预览 ---
const mamboPreview = computed(() => {
  if (!selectedAgent.value || selectedAgent.value.AgentType !== 'Mambo') return null;
  const params = (selectedAgent.value as any).agentParameters;
  if (!params) return null;
  return {
    generalPurpose: params.include_general_purpose ?? false,
    planningEnabled: params.enable_planning ?? true,
    showEnabled: params.enable_show ?? true,
    memoryEnabled: params.enable_memory ?? false,
    memoryResourceIds: params.memory_resource_ids ?? [],
    summaryEnabled: params.enable_summarization ?? false,
    summaryConfig: params.summarization_config ?? null,
    versionControlEnabled: params.version_control?.enabled ?? false,
  };
});

const securityReviewPreview = computed(() => {
  if (!selectedAgent.value || selectedAgent.value.AgentType !== 'Mambo') return null;
  const params = (selectedAgent.value as any).agentParameters;
  const sr = params?.security_review;
  if (!sr) {
    return { enabled: false, model_id: null, model_name: '', system_prompt: null, review_tools: null };
  }
  let modelName = '';
  if (sr.model_id) {
    const model = providerStore.allModels.find(m => m.id === sr.model_id);
    modelName = model ? model.name : sr.model_id;
  }
  return {
    enabled: sr.enabled ?? false,
    model_id: sr.model_id ?? null,
    model_name: modelName,
    system_prompt: sr.system_prompt ?? null,
    review_tools: sr.review_tools ?? null,
  };
});

const goalLoopPreview = computed<GoalLoopConfig | null>(() => {
  if (!selectedAgent.value || selectedAgent.value.AgentType !== 'Mambo') return null;
  const params = (selectedAgent.value as any).agentParameters;
  return params?.goal_loop ?? null;
});

const goalLoopModeLabel = computed(() => {
  if (goalLoopPreview.value?.mode === 'llm') return t('agent.goalLoop.modeLlm');
  if (goalLoopPreview.value?.mode === 'preset') return t('agent.goalLoop.modePreset');
  return String(goalLoopPreview.value?.mode || '');
});

const displayMemoryResources = ref<Resource[]>([]);

const defaultBackendId = computed(() => {
  return (selectedAgent.value as any)?.defaultBackendId ?? null;
});

const mamboTriggerLabel = computed(() => {
  const triggerType = mamboPreview.value?.summaryConfig?.trigger_type;
  if (triggerType === 'fraction') return t('agent.triggerFraction');
  if (triggerType === 'tokens') return t('agent.triggerTokens');
  if (triggerType === 'messages') return t('agent.triggerMessages');
  return String(triggerType || '');
});

const mamboKeepLabel = computed(() => {
  const keepType = mamboPreview.value?.summaryConfig?.keep_type;
  if (keepType === 'fraction') return t('agent.keepFraction');
  if (keepType === 'tokens') return t('agent.keepTokens');
  if (keepType === 'messages') return t('agent.keepMessages');
  return String(keepType || '');
});
// --- Mambo 专属配置预览 END ---

onMounted(() => {
  if (agentStore.allAgents.length === 0) {
    agentStore.fetchAllAgents();
  }
  if (backendStore.backendList.length === 0) {
    backendStore.fetchBackends();
  }
});

watch(() => props.chatData, (newData) => {
  if (newData) {
    form.name = isDefaultChatName(newData.name) ? t('chat.sidebar.initChatName') : newData.name;
    form.agentId = newData.agentId || null;
  }
}, { immediate: true, deep: true });

// 模型配置表单：随选中 Agent 同步（深拷贝，避免直接改 store 数据）
watch(() => selectedAgent.value, (agent) => {
  if (!agent) return;
  modelForm.aiModelId = agent.aiModelId || null;
  const params = agent.modelParameters ? JSON.parse(JSON.stringify(agent.modelParameters)) : {};
  modelForm.modelParameters = {
    ...params,
    max_context_messages: params.max_context_messages ?? 0,
    stream: params.stream ?? true,
    enable_suggest: params.enable_suggest ?? false,
    enable_ask_user: params.enable_ask_user ?? false,
  };
}, { immediate: true });

// 切换模型时保留通用参数、丢弃模型专属参数（与 AgentEditor 逻辑一致）
watch(() => modelForm.aiModelId, (newModelId) => {
  if (!newModelId) return;
  const currentModel = providerStore.allModels.find(m => m.id === newModelId);
  if (!currentModel) return;
  const supportedParams = new Set(currentModel.meta_config?.supported_parameters ?? []);
  const keysToKeep = new Set<string>(['max_context_messages', 'stream', 'enable_suggest', 'enable_ask_user']);
  systemConfigStore.llmParameters.forEach(paramDef => {
    if (['temperature', 'top_p'].includes(paramDef.key) || supportedParams.has(paramDef.key) || paramDef.default_activate) {
      keysToKeep.add(paramDef.key);
    }
  });
  const newParams: Record<string, any> = {};
  for (const key in modelForm.modelParameters) {
    if (keysToKeep.has(key)) newParams[key] = modelForm.modelParameters[key];
  }
  modelForm.modelParameters = newParams;
});

watch(() => selectedAgent.value?.resourcePromptList, async (resourceIds) => {
  if (!resourceIds || resourceIds.length === 0) {
    previewResources.value = [];
    return;
  }
  try {
    const promises = resourceIds.map(id => getResourceDetails(id).catch(() => null));
    const results = await Promise.all(promises);
    // 用已删除资源的占位 stub 替换 null，保留顺序
    previewResources.value = results.map((r, i) => {
      if (r) return r;
      const id = resourceIds[i];
      return { id, name: t('resource.deletedNameWithId', { id: id.substring(0, 8) }), resourceType: 'file', _deleted: true } as unknown as Resource;
    });
  } catch (error) {
    console.error('Failed to load preview resources:', error);
    previewResources.value = [];
  }
}, { immediate: true });

watch(() => mamboPreview.value?.memoryResourceIds, async (memoryIds) => {
  if (!memoryIds || memoryIds.length === 0) {
    displayMemoryResources.value = [];
    return;
  }
  try {
    const promises = memoryIds.map((id: string) => getResourceDetails(id).catch(() => null));
    const results = await Promise.all(promises);
    // 用已删除资源的占位 stub 替换 null，保留顺序
    displayMemoryResources.value = results.map((r, i) => {
      if (r) return r;
      const id = memoryIds[i];
      return { id, name: t('resource.deletedNameWithId', { id: id.substring(0, 8) }), resourceType: 'file', _deleted: true } as unknown as Resource;
    });
  } catch (error) {
    console.error('Failed to load memory resources:', error);
    displayMemoryResources.value = [];
  }
}, { immediate: true });

const handleUpdateModelValue = (val: boolean) => {
  emit('update:visible', val);
};

const handleDrawerClose = () => {
  emit('close');
};

function getSliderStep(min: number, max: number): number {
  const range = max - min;
  if (range <= 2) return 0.01;
  if (range <= 20) return 0.1;
  return 1;
}

function handleToggleParameter(param: DynamicParameterUI, isEnabled: boolean) {
  const newParams = { ...modelForm.modelParameters };
  if (isEnabled) {
    newParams[param.key] = param.definition.default_value;
  } else {
    delete newParams[param.key];
  }
  modelForm.modelParameters = newParams;
}

/** 组装最终保存的 modelParameters（与 AgentEditor 保存逻辑一致） */
function buildFinalModelParameters(): Record<string, any> {
  const finalModelParameters: Record<string, any> = {
    max_context_messages: modelForm.modelParameters.max_context_messages,
    stream: modelForm.modelParameters.stream,
    enable_suggest: modelForm.modelParameters.enable_suggest,
    enable_ask_user: modelForm.modelParameters.enable_ask_user,
  };
  for (const key in modelForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(modelForm.modelParameters, key)) {
      if (key === 'max_context_messages' || key === 'stream') continue;
      finalModelParameters[key] = modelForm.modelParameters[key];
    }
  }
  return finalModelParameters;
}

/** 模型配置是否有实际变更（与 Agent 当前值对比，仅比较最终会保存的键） */
function isModelConfigChanged(agent: Agent): boolean {
  if ((modelForm.aiModelId ?? null) !== (agent.aiModelId ?? null)) return true;
  const originalParams = agent.modelParameters ? JSON.parse(JSON.stringify(agent.modelParameters)) : {};
  const normalizedOriginal: Record<string, any> = {
    ...originalParams,
    max_context_messages: originalParams.max_context_messages ?? 0,
    stream: originalParams.stream ?? true,
    enable_suggest: originalParams.enable_suggest ?? false,
    enable_ask_user: originalParams.enable_ask_user ?? false,
  };
  const finalParams = buildFinalModelParameters();
  for (const key of Object.keys(finalParams)) {
    if (finalParams[key] !== normalizedOriginal[key]) return true;
  }
  return false;
}

async function handleSaveSettings() {
  if (!props.chatData) return;
  if (!form.name?.trim()) {
    ElMessage.warning(t('chat.settings.namePlaceholder'));
    return;
  }
  if (!form.agentId) {
    ElMessage.warning(t('common.rule.selectRequired'));
    return;
  }

  // 模型配置变更 → 保存至 Agent（全局生效，需用户确认）
  const agent = selectedAgent.value;
  if (agent && isModelConfigChanged(agent)) {
    try {
      await ElMessageBox.confirm(
        t('chat.settings.modelConfigGlobalTip'),
        t('agent.modelConfig'),
        { confirmButtonText: t('common.action.save'), cancelButtonText: t('common.action.cancel'), type: 'warning' }
      );
    } catch {
      return;
    }
    try {
      const updated = await updateAgent(agent.id, {
        aiModelId: modelForm.aiModelId ?? null,
        modelParameters: buildFinalModelParameters(),
      });
      // 同步 store 缓存（updateAgentSettings 包装器会吞掉异常，这里直接调 API 以便感知失败）
      const idx = agentStore.allAgents.findIndex(a => a.id === agent.id);
      if (idx !== -1) {
        agentStore.allAgents[idx] = { ...agentStore.allAgents[idx], ...updated };
      }
    } catch (error) {
      console.error('Failed to update agent model config:', error);
      ElMessage.error(t('common.operationFailed'));
      return;
    }
  }

  const payload: ChatUpdate = { agentId: form.agentId };
  // 与 header 一致:输入等于当前显示标题 = 未修改 → 不提交 name,保留后端默认 Key
  const displayTitle = isDefaultChatName(props.chatData.name) ? t('chat.sidebar.initChatName') : props.chatData.name;
  if (form.name && form.name.trim() !== displayTitle) {
    payload.name = form.name.trim();
  }
  emit('save', payload);
};

const openAgentSettings = (agentId: string) => {
  router.push({
    path: '/settings',
    query: { tab: 'agentManager', agentId }
  });
};
</script>

<style scoped>
.drawer-content {
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.preview-divider-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.agent-preview-scrollbar {
  flex-grow: 1;
  margin: 0 -20px;
  padding: 0 20px;
}

.agent-preview-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 20px;
}

.preview-section {
  background-color: var(--color-background-soft);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 16px;
}
.agent-avatar {
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.agent-title-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}
.agent-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-name {
  font-size: 16px;
  font-weight: bold;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.clickable-agent {
  cursor: pointer;
  color: var(--el-color-primary);
  transition: opacity 0.3s, text-decoration 0.3s;
}
.clickable-agent:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.agent-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.info-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.info-value {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.prompt-box {
  font-size: 13px;
  color: var(--el-text-color-regular);
  background-color: var(--el-bg-color);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}

.ext-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ext-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ext-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}
.ext-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.clickable-tag {
  cursor: pointer;
  transition: opacity 0.3s;
}
.clickable-tag:hover {
  opacity: 0.8;
}

.custom-agent-tag {
  height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
}

.tag-inner {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tag-avatar {
  background-color: transparent;
}

.ext-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

.mambo-preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.empty-agent-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

.default-star {
  margin-left: 4px;
  font-size: 10px;
  color: var(--el-color-danger);
}

.deleted-tag {
  opacity: 0.5;
  border-style: dashed;
  cursor: default;
}

.deleted-model-tag {
  margin-left: 6px;
  font-size: 11px;
}

.model-config-form .el-form-item {
  margin-bottom: 14px;
}

.label-icon {
  margin-left: 8px;
  color: #909399;
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

.goal-objective-item {
  grid-column: 1 / -1;
  margin-top: 12px;
  width: 100%;
}
.goal-objective {
  white-space: pre-wrap;
  word-break: break-word;
}
.goal-condition-args {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-left: 4px;
}
</style>
