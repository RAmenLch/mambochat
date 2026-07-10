<!-- frontend/mambo/src/mobile/components/chat/MobileChatAgentSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    direction="rtl"
    size="100%"
    :before-close="handleDrawerClose"
    :show-close="false"
    class="mobile-settings-drawer"
  >
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ $t('chat.settings.title') }}</span>
        <el-button :icon="Close" circle size="small" @click="handleDrawerClose" class="header-close-btn" />
      </div>
    </template>
    <div class="drawer-content">
      <!-- 会话自身的可编辑设置 -->
      <el-form v-if="chatData" :model="form" label-position="top">
        <el-form-item :label="$t('chat.settings.name')">
          <el-input
            v-model.trim="form.name"
            :placeholder="$t('chat.settings.namePlaceholder')"
          />
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

      <!-- Agent 详细配置预览区 -->
      <div v-if="selectedAgent" class="agent-preview-container">
        <!-- 1. 基本信息 -->
        <div class="preview-section">
          <div class="agent-header">
            <el-avatar
              :size="56"
              :src="selectedAgent.agentAvatarUrl || ''"
              :icon="User"
              class="agent-avatar"
            />
            <div class="agent-title-info">
              <div class="agent-name-row">
                <span class="agent-name">{{ selectedAgent.name }}</span>
                <el-tag size="small" type="info" effect="plain">{{ selectedAgent.AgentType }}</el-tag>
              </div>
              <div class="agent-desc">
                {{ selectedAgent.description || $t('common.none') }}
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 模型配置 -->
        <div class="preview-section">
          <div class="section-title">
            <el-icon><Cpu /></el-icon> {{ $t('agent.modelConfig') }}
          </div>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('agent.bindModel') }}:</span>
              <span class="info-value">{{ displayModelName }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.max_context_messages !== undefined">
              <span class="info-label">{{ $t('agent.contextMessages') }}:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.max_context_messages }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.stream !== undefined">
              <span class="info-label">{{ $t('agent.streamOutput') }}:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.stream ? '开启' : '关闭' }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.temperature !== undefined">
              <span class="info-label">Temperature:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.temperature }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.top_p !== undefined">
              <span class="info-label">Top P:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.top_p }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.enable_suggest !== undefined">
              <span class="info-label">{{ $t('chat.settings.enableSuggest') }}:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.enable_suggest ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item" v-if="selectedAgent.modelParameters?.enable_ask_user !== undefined">
              <span class="info-label">{{ $t('chat.settings.enableAskUser') }}:</span>
              <span class="info-value">{{ selectedAgent.modelParameters.enable_ask_user ? '✓' : '✗' }}</span>
            </div>
          </div>
        </div>

        <!-- 3. 系统设定 -->
        <div class="preview-section">
          <div class="section-title">
            <el-icon><Document /></el-icon> {{ $t('agent.systemPrompt') }}
          </div>
          <div class="prompt-box">
            {{ selectedAgent.systemPrompt || $t('common.none') }}
          </div>
        </div>

        <!-- 4. 扩展能力 -->
        <div class="preview-section ext-section">
          <div class="section-title">
            <el-icon><MagicStick /></el-icon> {{ $t('agent.settingsAndResources') }}
          </div>

          <!-- 扩展能力: 挂载资源 -->
          <div class="ext-item">
            <div class="ext-label">{{ $t('agent.mountedResources') }}:</div>
            <div class="ext-tags" v-if="previewResources.length > 0">
              <MountedResourceTags :model-value="previewResources" color-by-type readonly />
            </div>
            <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
          </div>

          <!-- MCP 工具 -->
          <div class="ext-item">
            <div class="ext-label">{{ $t('agent.enableMcp') }}:</div>
            <div class="ext-tags" v-if="displayMcpList.length > 0">
              <el-tag v-for="mcp in displayMcpList" :key="mcp.id" size="small" type="info" effect="light">
                <el-icon><Connection /></el-icon> {{ mcp.name }}
              </el-tag>
            </div>
            <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
          </div>

          <!-- 子 Agent -->
          <div class="ext-item">
            <div class="ext-label">{{ $t('agent.subAgents') }}:</div>
            <div class="ext-tags" v-if="displaySubAgents.length > 0">
              <el-tag
                v-for="sub in displaySubAgents"
                :key="sub.id"
                size="small"
                type="primary"
                effect="light"
                class="custom-agent-tag"
              >
                <div class="tag-inner">
                  <el-avatar v-if="sub.avatar" :size="14" :src="sub.avatar" class="tag-avatar" />
                  <el-icon v-else><User /></el-icon>
                  <span>{{ sub.name }}</span>
                </div>
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
                :type="b.name === 'Unknown Backend' ? 'info' : 'warning'"
                effect="light"
                :class="{ 'deleted-tag': b.name === 'Unknown Backend' }"
              >
                <el-icon><Monitor /></el-icon> {{ b.name }}
                <span v-if="b.id === defaultBackendId && b.name !== 'Unknown Backend'" class="default-star">★</span>
              </el-tag>
            </div>
            <div class="ext-empty" v-else>{{ $t('common.none') }}</div>
          </div>
        </div>

        <div class="preview-section" v-if="selectedAgent.AgentType === 'Mambo' && mamboPreview">
          <div class="section-title"><el-icon><Setting /></el-icon> {{ $t('agent.mamboConfig') }}</div>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('agent.generalPurpose') }}:</span>
              <span class="info-value">{{ mamboPreview.generalPurpose ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('agent.mamboPlanning') }}:</span>
              <span class="info-value">{{ mamboPreview.planningEnabled ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('agent.mamboShow') }}:</span>
              <span class="info-value">{{ mamboPreview.showEnabled ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('agent.mamboMemory') }}:</span>
              <span class="info-value">{{ mamboPreview.memoryEnabled ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('agent.summarization') }}:</span>
              <span class="info-value">{{ mamboPreview.summaryEnabled ? '✓' : '✗' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('agent.versionControl') }}:</span>
              <span class="info-value">{{ mamboPreview.versionControlEnabled ? '✓' : '✗' }}</span>
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
            <div class="info-grid" style="margin-top: 12px;">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.summarizationTrigger') }}:</span>
                <span class="info-value">{{ mamboTriggerLabel }} ({{ mamboPreview.summaryConfig.trigger_value }})</span>
              </div>
              <div class="info-item">
                <span class="info-label">{{ $t('agent.summarizationKeep') }}:</span>
                <span class="info-value">{{ mamboKeepLabel }} ({{ mamboPreview.summaryConfig.keep_value }})</span>
              </div>
            </div>
            <div class="info-grid" style="margin-top: 12px;">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.summarizationOffload') }}:</span>
                <span class="info-value">{{ mamboPreview.summaryConfig.offload_to_backend ? '✓' : '✗' }}</span>
              </div>
            </div>
          </template>
        </div>

        <div class="preview-section" v-if="selectedAgent.AgentType === 'Mambo' && securityReviewPreview">
          <div class="section-title"><el-icon><WarningFilled /></el-icon> {{ $t('agent.securityReview') }}</div>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('agent.securityReviewEnable') }}:</span>
              <span class="info-value">{{ securityReviewPreview.enabled ? '✓' : '✗' }}</span>
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

      <div v-else class="empty-agent-preview">
        <el-empty :description="$t('common.rule.selectRequired')" :image-size="60" />
      </div>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <div class="footer-divider"></div>
        <div class="footer-buttons">
          <el-button @click="emit('update:visible', false)" class="footer-btn cancel-btn">
            {{ $t('common.action.cancel') }}
          </el-button>
          <el-button type="primary" @click="handleSaveSettings" class="footer-btn save-btn">
            {{ $t('common.action.save') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, watch, computed, ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { User, Cpu, Document, MagicStick, Connection, Monitor, Setting, WarningFilled, Close } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useBackendStore } from '@/stores/backendStore';
import { getResourceDetails } from '@/api/resourceService';
import type { Chat, ChatUpdate, Resource } from '@/api/types';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';

const props = defineProps<{
  visible: boolean;
  chatData: Chat | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'save', settings: ChatUpdate): void;
}>();

const { t } = useI18n();
const agentStore = useAgentStore();
const providerStore = useProviderStore();
const mcpStore = useMcpStore();
const backendStore = useBackendStore();

const form = reactive({
  name: '',
  agentId: '' as string | null,
});

const previewResources = ref<Resource[]>([]);

// --- Computed ---

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

const displayModelName = computed(() => {
  if (!selectedAgent.value?.aiModelId) return t('common.status.unspecified');
  const model = providerStore.allModels.find(m => m.id === selectedAgent.value!.aiModelId);
  return model ? model.name : t('common.status.unknownModel');
});

const displayMcpList = computed(() => {
  const mcpIds = selectedAgent.value?.enabledMcpIds || [];
  return mcpIds.map(id => {
    const mcp = mcpStore.activeUserMcpServices.find(m => m.id === id);
    return mcp ? { id, name: mcp.name } : { id, name: 'Unknown MCP' };
  });
});

const displaySubAgents = computed(() => {
  const subIds = selectedAgent.value?.subAgents || [];
  return subIds.map(id => {
    const agent = agentStore.allAgents.find(a => a.id === id);
    return agent ? { id, name: agent.name, avatar: agent.agentAvatarUrl } : { id, name: 'Unknown Agent', avatar: null };
  });
});

const displayBackendList = computed(() => {
  const bIds = selectedAgent.value?.backendIds || [];
  return bIds.map(id => {
    const b = backendStore.backendList.find(x => x.id === id);
    return b ? { id, name: b.name } : { id, name: 'Unknown Backend' };
  });
});

const defaultBackendId = computed(() => {
  return (selectedAgent.value as any)?.defaultBackendId ?? null;
});

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
  if (!params?.security_review) return null;
  const sr = params.security_review;
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

const displayMemoryResources = ref<Resource[]>([]);

// --- Lifecycle ---

onMounted(() => {
  if (agentStore.allAgents.length === 0) {
    agentStore.fetchAllAgents();
  }
  if (backendStore.backendList.length === 0) {
    backendStore.fetchBackends();
  }
});

// --- Watchers ---

watch(() => props.chatData, (newData) => {
  if (newData) {
    form.name = newData.name || '';
    form.agentId = newData.agentId || null;
  }
}, { immediate: true, deep: true });

watch(() => selectedAgent.value?.resourcePromptList, async (resourceIds) => {
  if (!resourceIds || resourceIds.length === 0) {
    previewResources.value = [];
    return;
  }
  try {
    const promises = resourceIds.map(id => getResourceDetails(id).catch(() => null));
    const results = await Promise.all(promises);
    previewResources.value = results.filter(r => r !== null) as Resource[];
  } catch (error) {
    console.error('Failed to load preview resources:', error);
    previewResources.value = [];
  }
}, { immediate: true });

// --- Methods ---

const handleDrawerClose = () => {
  emit('update:visible', false);
};

const handleSaveSettings = () => {
  if (!props.chatData) return;
  if (!form.name?.trim()) {
    ElMessage.warning(t('chat.settings.namePlaceholder'));
    return;
  }
  if (!form.agentId) {
    ElMessage.warning(t('common.rule.selectRequired'));
    return;
  }

  emit('save', {
    name: form.name,
    agentId: form.agentId,
  });
};
</script>

<style scoped>
.mobile-settings-drawer :deep(.el-drawer__header) {
  margin-bottom: 0 !important;
  padding: 8px 16px 4px 16px;
}

.mobile-settings-drawer :deep(.el-drawer__body) {
  padding: 0 16px 20px 16px;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.drawer-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-title::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 20px;
  background: var(--el-color-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

.header-close-btn {
  color: var(--el-text-color-secondary);
  border: none;
  background: var(--el-fill-color-light);
  width: 32px;
  height: 32px;
}

.drawer-content {
  padding: 0 14px 28px 14px;
  display: flex;
  flex-direction: column;
}

.drawer-content :deep(.el-input__wrapper),
.drawer-content :deep(.el-select .el-input__wrapper) {
  border-radius: 10px;
  background-color: var(--color-background-soft);
  box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;
}

.drawer-footer {
  padding: 0;
}

.footer-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 0 -20px 8px -20px;
}

.footer-buttons {
  display: inline-flex;
  justify-content: center;
  gap: 12px;
  padding: 0 16px;
  padding-bottom: max(8px, env(safe-area-inset-bottom));
}

.footer-btn {
  flex: 0 0 auto;
  width: auto;
  height: 40px;
  padding: 0 32px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
}

.cancel-btn {
  background: var(--el-fill-color-light);
  border: none;
  color: var(--el-text-color-regular);
}

.save-btn {
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)) !important;
  border: none !important;
  color: #fff !important;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.35);
}

.preview-divider-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.5px;
}

.agent-preview-container {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 18px;
}

.preview-section {
  background-color: var(--color-background-soft);
  border-radius: 14px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title :deep(.el-icon) {
  color: var(--el-color-primary);
  font-size: 16px;
}

/* 1. 基本信息样式 */
.agent-header {
  display: flex;
  align-items: center;
  gap: 14px;
}
.agent-avatar {
  background: linear-gradient(135deg, var(--el-color-primary-light-7), var(--el-color-primary-light-5));
  color: var(--el-color-primary);
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}
.agent-title-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
  flex: 1;
}
.agent-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.agent-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.agent-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

/* 2. 模型配置样式 */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  background: var(--el-bg-color);
  border-radius: 10px;
  padding: 10px 12px;
}
.info-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.3px;
}
.info-value {
  font-size: 13px;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

/* 3. 系统提示词样式 */
.prompt-box {
  font-size: 13px;
  color: var(--el-text-color-regular);
  background-color: var(--el-bg-color);
  padding: 12px 12px 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-left: 3px solid var(--el-color-primary-light-5);
  max-height: 140px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.6;
}

/* 4. 扩展能力样式 */
.ext-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ext-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ext-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 600;
}
.ext-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.custom-agent-tag {
  height: 26px;
  padding: 0 10px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  font-weight: 500;
}

.tag-inner {
  display: flex;
  align-items: center;
  gap: 5px;
}

.tag-avatar {
  background-color: transparent;
}

.ext-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

.empty-agent-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 160px;
}

.default-star {
  margin-left: 4px;
  font-size: 11px;
  color: var(--el-color-danger);
}

.deleted-tag {
  opacity: 0.5;
  border-style: dashed;
  cursor: default;
}

@media (max-width: 380px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
.mobile-settings-drawer .el-drawer__header {
  margin-bottom: 0 !important;
  padding: 14px 16px 10px 16px !important;
}
.mobile-settings-drawer .el-drawer__body {
  padding-top: 0 !important;
}
.mobile-settings-drawer .el-drawer__footer {
  padding: 5px 0 5px 0 !important;
  text-align: center !important;
}
</style>
