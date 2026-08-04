<!-- MobileAgentEditor.vue — 移动端 Agent 编辑器（P1 重构） -->
<template>
  <div class="mobile-agent-editor" v-if="agentData">
    <!-- 毛玻璃 Header -->
    <div class="editor-header">
      <div class="header-left">
        <el-tag size="small" type="info" effect="plain">{{ agentData.AgentType }}</el-tag>
      </div>
    </div>

    <div class="editor-body">
      <!-- 1. 基本信息 -->
      <div class="section-card">
        <div class="section-title">{{ $t('agent.basicInfo') }}</div>
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
            <div class="field-item">
              <label class="field-label">{{ $t('agent.name') }}</label>
              <input
                v-model="form.name"
                class="native-input"
                :placeholder="$t('agent.namePlaceholder')"
              />
            </div>
            <div class="field-item">
              <label class="field-label">{{ $t('agent.type') }}</label>
              <el-select v-model="form.AgentType" style="width: 100%" popper-class="mobile-popper">
                <el-option label="Mambo Agent" value="Mambo" />
                <el-option label="Deep Agent" value="DeepAgent" />
                <el-option label="ReAct Agent" value="ReActAgent" />
              </el-select>
            </div>
            <div class="field-item">
              <label class="field-label">{{ $t('agent.description') }}</label>
              <textarea
                v-model="form.description"
                class="native-textarea"
                :rows="2"
                :placeholder="$t('agent.descPlaceholder')"
              ></textarea>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. 模型配置 -->
      <div class="section-card">
        <div class="section-title">{{ $t('agent.modelConfig') }}</div>
        <div class="field-item">
          <label class="field-label">{{ $t('agent.bindModel') }}</label>
          <el-select
            ref="modelSelectRef"
            v-model="form.aiModelId"
            :placeholder="$t('agent.modelPlaceholder')"
            style="width: 100%"
            clearable
            popper-class="mobile-popper"
            @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, modelSelectRef)"
          >
            <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
              <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
            </el-option-group>
          </el-select>
        </div>

        <template v-if="form.aiModelId">
          <div class="field-row">
            <div class="field-label">
              <span>{{ $t('agent.contextMessages') }}</span>
              <el-tooltip effect="dark" :content="$t('agent.contextMessagesTip')" placement="top">
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <el-input-number
              :model-value="Number(form.modelParameters.max_context_messages) || 0"
              @update:model-value="(val: number | undefined) => form.modelParameters.max_context_messages = val"
              :min="0" :step="2" controls-position="right" style="width: 100%"
            />
          </div>

          <div class="field-row">
            <div class="field-label">
              <span>{{ $t('agent.streamOutput') }}</span>
              <el-tooltip effect="dark" :content="$t('agent.streamOutputTip')" placement="top">
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <el-switch v-model="form.modelParameters.stream" />
          </div>
        </template>

        <template v-if="form.aiModelId">
          <div v-for="param in dynamicParameters" :key="param.key" class="field-row">
            <div class="field-label">
              <span>{{ param.label }}</span>
              <el-tooltip effect="dark" :content="param.description" placement="top">
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <div class="param-control">
              <el-input-number
                v-if="param.type === 'number'"
                :model-value="form.modelParameters[param.key] as number | undefined"
                @update:model-value="(val: number | undefined) => form.modelParameters[param.key] = val"
                :min="!Array.isArray(param.limit) ? param.limit?.min ?? 0 : 0"
                :max="!Array.isArray(param.limit) ? param.limit?.max ?? 1 : 1"
                :step="getSliderStep(!Array.isArray(param.limit) ? param.limit?.min ?? 0 : 0, !Array.isArray(param.limit) ? param.limit?.max ?? 1 : 1)"
                :disabled="!param.isEnabled"
                controls-position="right"
                class="param-input-num"
              />
              <el-input-number
                v-else-if="param.type === 'integer'"
                :model-value="form.modelParameters[param.key] as number | undefined"
                @update:model-value="(val: number | undefined) => form.modelParameters[param.key] = val"
                :min="!Array.isArray(param.limit) ? param.limit?.min : undefined"
                :max="!Array.isArray(param.limit) ? param.limit?.max : undefined"
                :disabled="!param.isEnabled"
                controls-position="right"
                class="param-input-num"
              />
              <el-switch
                v-else-if="param.type === 'boolean'"
                v-model="form.modelParameters[param.key]"
                :disabled="!param.isEnabled"
              />
              <el-select
                v-else-if="param.type === 'string' && Array.isArray(param.limit)"
                v-model="form.modelParameters[param.key]"
                :disabled="!param.isEnabled"
                class="param-select"
                popper-class="mobile-popper"
              >
                <el-option v-for="opt in param.limit" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <input
                v-else-if="param.type === 'string'"
                :value="form.modelParameters[param.key] as string"
                @input="(e: Event) => form.modelParameters[param.key] = (e.target as HTMLInputElement).value"
                :disabled="!param.isEnabled"
                class="native-input param-native-input"
              />
              <el-switch
                :model-value="param.isEnabled"
                @change="(val: string | number | boolean) => handleToggleParameter(param, val as boolean)"
                class="param-enable-switch"
              />
            </div>
          </div>
        </template>
      </div>

      <!-- 3. 设定与能力 -->
      <div class="section-card">
        <div class="section-title">{{ $t('agent.settingsAndResources') }}</div>

        <!-- 系统提示词 -->
        <div class="field-item">
          <label class="field-label">{{ $t('agent.systemPrompt') }}</label>
          <textarea
            v-model="form.systemPrompt"
            class="native-textarea"
            :rows="6"
            :placeholder="$t('agent.sysPromptPlaceholder')"
          ></textarea>
        </div>

        <!-- 挂载资源 -->
        <div class="field-item">
          <label class="field-label">{{ $t('agent.mountedResources') }}</label>
          <div class="chip-area">
            <button class="chip-add-btn" @click="resourceSelectorVisible = true">
              <el-icon :size="16"><Collection /></el-icon>
              <span>{{ $t('agent.mountResource') }}</span>
            </button>
            <template v-if="mountedResources.length > 0">
              <MountedResourceTags v-model="mountedResources" color-by-type />
            </template>
            <span v-else class="chip-empty">{{ $t('agent.noResources') }}</span>
          </div>
        </div>

        <!-- MCP 工具 -->
        <div class="field-item">
          <label class="field-label">{{ $t('agent.enableMcp') }}</label>
          <div class="chip-area">
            <button class="chip-add-btn" @click="mcpSelectorVisible = true">
              <el-icon :size="16"><Connection /></el-icon>
              <span>{{ $t('agent.mountMcp') }}</span>
            </button>
            <div v-if="mountedMcpList.length > 0" class="chip-list">
              <span
                v-for="mcp in mountedMcpList"
                :key="mcp.id"
                class="chip"
              >
                <el-icon :size="14"><Connection /></el-icon>
                <span class="chip-text">{{ mcp.name }}</span>
                <button class="chip-close" @click="handleRemoveMcp(mcp.id)">&times;</button>
              </span>
            </div>
            <span v-else class="chip-empty">{{ $t('agent.noMcp') }}</span>
          </div>
        </div>

        <!-- 子 Agent -->
        <div class="field-item" v-if="form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo'">
          <label class="field-label">{{ $t('agent.subAgents') }}</label>
          <div class="chip-area">
            <button class="chip-add-btn" @click="agentSelectorVisible = true">
              <el-icon :size="16"><Plus /></el-icon>
              <span>{{ $t('agent.mountSubAgent') }}</span>
            </button>
            <div v-if="mountedSubAgents.length > 0" class="chip-list">
              <span
                v-for="sub in mountedSubAgents"
                :key="sub.id"
                class="chip chip-primary"
              >
                <el-avatar :size="14" :src="sub.agentAvatarUrl ?? undefined" :icon="User" class="chip-avatar" />
                <span class="chip-text">{{ sub.name }}</span>
                <button class="chip-close" @click="handleRemoveSubAgent(sub.id)">&times;</button>
              </span>
            </div>
            <span v-else class="chip-empty">{{ $t('agent.noSubAgents') }}</span>
          </div>
        </div>

        <!-- Backend 挂载 -->
        <div class="field-item" v-if="form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo'">
          <label class="field-label">{{ $t('agent.mountBackend') }}</label>
          <div class="chip-area">
            <button class="chip-add-btn chip-add-warning" @click="backendSelectorVisible = true">
              <el-icon :size="16"><Monitor /></el-icon>
              <span>{{ $t('agent.addBackend') }}</span>
            </button>
            <div v-if="mountedBackendList.length > 0" class="chip-list">
              <span
                v-for="b in mountedBackendList"
                :key="b.id"
                class="chip"
                :class="{ 'chip-warning': b.id !== form.defaultBackendId, 'chip-danger': b.id === form.defaultBackendId }"
              >
                <el-icon :size="14"><Monitor /></el-icon>
                <span class="chip-text">{{ b.name }}</span>
                <span v-if="b.id === form.defaultBackendId" class="chip-star">★</span>
                <button class="chip-close" @click="handleRemoveBackend(b.id)">&times;</button>
              </span>
            </div>
            <span v-else class="chip-empty">{{ $t('agent.noBackend') }}</span>
          </div>
          <div v-if="mountedBackendList.length > 0" class="field-item" style="margin-top: 8px; margin-bottom: 0;">
            <label class="field-label">{{ $t('agent.selectDefaultBackend') }}</label>
            <el-select v-model="form.defaultBackendId" clearable :placeholder="$t('agent.selectDefaultBackend')" style="width: 100%" popper-class="mobile-popper">
              <el-option v-for="b in mountedBackendList" :key="b.id" :label="`${b.name} (${b.backendType})`" :value="b.id" />
            </el-select>
          </div>
        </div>
      </div>

      <!-- 4. Mambo 专属配置 -->
      <div class="section-card" v-if="form.AgentType === 'Mambo'">
        <div class="section-title">{{ $t('agent.mamboConfig') }}</div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.generalPurpose') }}</span>
          </div>
          <el-switch v-model="form.mambo_general_purpose" size="small" />
        </div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.mamboPlanning') }}</span>
          </div>
          <el-switch v-model="form.mambo_planning_enabled" size="small" />
        </div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.mamboShow') }}</span>
          </div>
          <el-switch v-model="form.mambo_show_enabled" size="small" />
        </div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.mamboMemory') }}</span>
          </div>
          <el-switch v-model="form.mambo_memory_enabled" size="small" />
        </div>

        <template v-if="form.mambo_memory_enabled">
          <div class="field-item">
            <label class="field-label">{{ $t('agent.memoryResources') }}</label>
            <div class="chip-area">
              <button class="chip-add-btn" @click="memorySelectorVisible = true">
                <el-icon :size="16"><Collection /></el-icon>
                <span>{{ $t('agent.mountMemory') }}</span>
              </button>
              <div v-if="mountedMemoryResources.length > 0" class="chip-list">
                <span
                  v-for="res in mountedMemoryResources"
                  :key="res.id"
                  class="chip chip-success"
                >
                  <span class="chip-text">{{ res.name }}</span>
                  <button class="chip-close" @click="handleRemoveMemory(res.id)">&times;</button>
                </span>
              </div>
              <span v-else class="chip-empty">{{ $t('agent.noMemory') }}</span>
            </div>
          </div>
        </template>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.summarization') }}</span>
          </div>
          <el-switch v-model="form.mambo_summary_enabled" size="small" />
        </div>

        <template v-if="form.mambo_summary_enabled">
          <div class="field-item">
            <label class="field-label">{{ $t('agent.summarizationTrigger') }}</label>
            <div class="param-row-split">
              <el-select v-model="form.mambo_summary_trigger_type" style="flex: 1" popper-class="mobile-popper">
                <el-option :label="$t('agent.triggerFraction')" value="fraction" />
                <el-option :label="$t('agent.triggerTokens')" value="tokens" />
                <el-option :label="$t('agent.triggerMessages')" value="messages" />
              </el-select>
              <el-input-number
                v-model="form.mambo_summary_trigger_value"
                :min="form.mambo_summary_trigger_type === 'fraction' ? 0.1 : 1"
                :max="form.mambo_summary_trigger_type === 'fraction' ? 1 : 1000000"
                :step="form.mambo_summary_trigger_type === 'fraction' ? 0.05 : 1000"
                :precision="form.mambo_summary_trigger_type === 'fraction' ? 2 : 0"
                controls-position="right"
                style="width: 130px"
              />
            </div>
          </div>

          <div class="field-item">
            <label class="field-label">{{ $t('agent.summarizationKeep') }}</label>
            <div class="param-row-split">
              <el-select v-model="form.mambo_summary_keep_type" style="flex: 1" popper-class="mobile-popper">
                <el-option :label="$t('agent.keepFraction')" value="fraction" />
                <el-option :label="$t('agent.keepTokens')" value="tokens" />
                <el-option :label="$t('agent.keepMessages')" value="messages" />
              </el-select>
              <el-input-number
                v-model="form.mambo_summary_keep_value"
                :min="form.mambo_summary_keep_type === 'fraction' ? 0.01 : 1"
                :max="form.mambo_summary_keep_type === 'fraction' ? 1 : 500000"
                :step="form.mambo_summary_keep_type === 'fraction' ? 0.05 : 1000"
                :precision="form.mambo_summary_keep_type === 'fraction' ? 2 : 0"
                controls-position="right"
                style="width: 130px"
              />
            </div>
          </div>

          <div class="field-row">
            <div class="field-label">
              <span>{{ $t('agent.summarizationOffload') }}</span>
            </div>
            <el-switch v-model="form.mambo_summary_offload" size="small" />
          </div>
        </template>

        <div class="section-divider"></div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.versionControl') }}</span>
          </div>
          <el-switch v-model="form.mambo_version_control_enabled" size="small" />
        </div>

        <div class="section-divider"></div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.mcpThreshold') }}</span>
          </div>
          <el-input-number
            v-model="form.mambo_mcp_threshold"
            :min="0"
            :step="1"
            size="small"
            controls-position="right"
            style="width: 120px;"
          />
        </div>

        <div class="section-divider"></div>

        <div class="field-row">
          <div class="field-label">
            <span>{{ $t('agent.securityReviewEnable') }}</span>
          </div>
          <el-switch v-model="form.mambo_security_review_enabled" size="small" />
        </div>

        <template v-if="form.mambo_security_review_enabled">
          <div class="field-item">
            <label class="field-label">{{ $t('agent.securityReviewModel') }}</label>
            <el-select v-model="form.mambo_security_review_model_id" clearable :placeholder="$t('agent.securityReviewModelPlaceholder')" style="width: 100%" popper-class="mobile-popper">
              <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
                <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
              </el-option-group>
            </el-select>
          </div>

          <div class="field-item">
            <label class="field-label">{{ $t('agent.securityReviewTools') }}</label>
            <el-select
              v-model="form.mambo_security_review_tools"
              multiple
              filterable
              :placeholder="$t('agent.securityReviewToolsPlaceholder')"
              style="width: 100%"
              popper-class="mobile-popper"
            >
              <el-option v-for="tool in hitlToolOptions" :key="tool.name" :label="tool.name" :value="tool.name">
                <span>{{ tool.name }}</span>
                <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px; margin-left: 12px;">
                  {{ tool.source === 'backend' ? 'Backend' : 'MCP' }}
                </span>
              </el-option>
            </el-select>
            <div v-if="staleToolNames.length > 0" class="stale-tools-hint">
              <span v-for="name in staleToolNames" :key="name" class="chip chip-stale">
                <s>{{ name }}</s>
                <button class="chip-close" @click="removeReviewTool(name)">&times;</button>
              </span>
            </div>
          </div>

          <div class="field-item">
            <label class="field-label">{{ $t('agent.securityReviewPrompt') }}</label>
            <textarea
              v-model="form.mambo_security_review_system_prompt"
              class="native-textarea"
              :rows="5"
              :placeholder="DEFAULT_SECURITY_REVIEW_SYSTEM_PROMPT"
            ></textarea>
          </div>
        </template>
      </div>

      <div class="body-spacer"></div>
    </div>

    <!-- 固定底部保存栏 -->
    <div class="save-bar">
      <button class="save-btn" @click="handleSave" :disabled="isSaving">
        <el-icon v-if="isSaving" class="is-loading"><Loading /></el-icon>
        <span>{{ isSaving ? $t('common.status.saving') : $t('common.action.save') }}</span>
      </button>
    </div>

    <!-- ===== Bottom Sheets ===== -->

    <!-- 资源选择器 -->
    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      :context="(form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') ? 'agent-deep' : 'agent-react'"
      @mount-resources="handleMountResources"
    />

    <!-- 子 Agent 选择器 -->
    <MobileAgentSelectorSheet
      v-if="currentAgentId"
      v-model:visible="agentSelectorVisible"
      :current-agent-id="currentAgentId"
      :initial-selected-ids="form.subAgents"
      @select="handleMountSubAgents"
    />

    <!-- MCP 选择器 Bottom Sheet -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="mcpSelectorVisible" class="sheet-overlay" @click="mcpSelectorVisible = false">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ $t('agent.mountMcp') }}</span>
              <button class="sheet-close" @click="mcpSelectorVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="sheet-body">
              <div v-if="availableMcps.length === 0" class="sheet-empty">
                <el-empty :description="$t('common.noData')" :image-size="60" />
              </div>
              <button
                v-for="mcp in availableMcps"
                :key="mcp.id"
                class="sheet-item"
                @click="handleAddMcp(mcp.id); mcpSelectorVisible = false"
              >
                <div class="sheet-item-left">
                  <el-icon :size="18"><Connection /></el-icon>
                  <div class="sheet-item-info">
                    <span class="sheet-item-name">{{ mcp.name }}</span>
                    <span class="sheet-item-desc" v-if="mcp.description">{{ mcp.description }}</span>
                  </div>
                </div>
                <el-icon :size="16" class="sheet-item-arrow"><Plus /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Backend 选择器 Bottom Sheet -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="backendSelectorVisible" class="sheet-overlay" @click="backendSelectorVisible = false">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ $t('agent.mountBackend') }}</span>
              <button class="sheet-close" @click="backendSelectorVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="sheet-body">
              <div v-if="availableBackends.length === 0" class="sheet-empty">
                <el-empty :description="$t('common.noData')" :image-size="60" />
              </div>
              <button
                v-for="b in availableBackends"
                :key="b.id"
                class="sheet-item"
                @click="handleAddBackend(b.id); backendSelectorVisible = false"
              >
                <div class="sheet-item-left">
                  <el-icon :size="18"><Monitor /></el-icon>
                  <div class="sheet-item-info">
                    <span class="sheet-item-name">{{ b.name }}</span>
                    <span class="sheet-item-desc">{{ b.backendType }}</span>
                  </div>
                </div>
                <el-icon :size="16" class="sheet-item-arrow"><Plus /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Memory 资源选择器 -->
    <ResourceSelectorDialog
      v-model:visible="memorySelectorVisible"
      context="agent-memory"
      @mount-resources="handleMountMemory"
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
import { User, QuestionFilled, Collection, Plus, Connection, Monitor, Loading, Close } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useBackendStore } from '@/stores/backendStore';

import { uploadAgentAvatar, deleteAgentAvatar, getAgent, getAgentHitlTools } from '@/api/agentService';
import { getResourceDetails } from '@/api/resourceService';
import type { Resource, Agent, AgentType, HitlToolInfo, MamboAgentParameters } from '@/api/types';

import AvatarUploader from '@/components/settings/AvatarUploader.vue';
import ResourceSelectorDialog from '@/mobile/components/chat/dialogs/ResourceSelectorDialog.vue';
import MobileAgentSelectorSheet from './dialogs/MobileAgentSelectorSheet.vue';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';
import { useModelSelectScroll } from '@/composables/useModelSelectScroll';

type AgentModelParameterValue = boolean | number | string | undefined;

const { t } = useI18n();

const DEFAULT_SECURITY_REVIEW_SYSTEM_PROMPT = `You are a security reviewer for an AI coding agent.
Your job is to review tool calls the agent wants to make and determine if they pose a security risk.

## Review Guidelines

### Generally SAFE operations (is_safe=True):
- Reading files, listing directories, searching/grepping within files
- Writing/editing files within the user's project workspace
- Creating new files in project directories
- Non-destructive git operations (status, diff, log)
- Informational/read-only system queries

### Potentially UNSAFE operations (consider is_safe=False):
- Deleting files or directories (especially outside project workspace)
- Modifying system configuration files (e.g., /etc/*, Windows Registry)
- Executing shell commands that install/uninstall software
- Commands that modify system services or scheduled tasks
- Operations that access or export credentials, API keys, or secrets
- Force pushing to git repositories
- Modifying files outside the project workspace without explicit user intent`;

const agentStore = useAgentStore();
const providerStore = useProviderStore();
const systemConfigStore = useSystemConfigStore();
const mcpStore = useMcpStore();
const backendStore = useBackendStore();

const { currentAgentId, agentList } = storeToRefs(agentStore);
const { groupedModels, allModels } = storeToRefs(providerStore);
const { activeUserMcpServices } = storeToRefs(mcpStore);
const { backendList } = storeToRefs(backendStore);

const isSaving = ref(false);
const isAvatarLoading = ref(false);
const resourceSelectorVisible = ref(false);
const agentSelectorVisible = ref(false);
const mcpSelectorVisible = ref(false);
const backendSelectorVisible = ref(false);
const memorySelectorVisible = ref(false);
const modelSelectRef = ref();
const { scrollToTopIfStarred } = useModelSelectScroll();

const hitlToolOptions = ref<HitlToolInfo[]>([]);
const hitlToolOptionsLoaded = ref(false);

const staleToolNames = computed(() => {
  if (!hitlToolOptionsLoaded.value) return [] as string[];
  const activeNames = new Set(hitlToolOptions.value.map(t => t.name));
  return form.mambo_security_review_tools.filter(name => !activeNames.has(name) && name.trim());
});

function removeReviewTool(toolName: string) {
  form.mambo_security_review_tools = form.mambo_security_review_tools.filter(v => v !== toolName);
}

const agentData = computed(() => agentList.value.find(a => a.id === currentAgentId.value));
const mountedResources = ref<Resource[]>([]);
const mountedSubAgents = ref<Agent[]>([]);
const mountedMemoryResources = ref<Resource[]>([]);

const form = reactive({
  name: '', description: '', AgentType: 'ReActAgent', systemPrompt: '',
  aiModelId: null as string | null, modelParameters: {} as Record<string, AgentModelParameterValue>,
  agentAvatarUrl: null as string | null, enabledMcpIds: [] as string[], subAgents: [] as string[],
  backendIds: [] as string[], defaultBackendId: null as string | null,

  // Mambo 专属配置
  mambo_general_purpose: false,
  mambo_planning_enabled: true,
  mambo_show_enabled: true,
  mambo_memory_enabled: false,
  mambo_memory_resource_ids: [] as string[],
  mambo_summary_enabled: false,
  mambo_summary_trigger_type: 'tokens' as 'fraction' | 'tokens' | 'messages',
  mambo_summary_trigger_value: 180000,
  mambo_summary_keep_type: 'messages' as 'fraction' | 'tokens' | 'messages',
  mambo_summary_keep_value: 20,
  mambo_summary_offload: false,
  mambo_security_review_enabled: false,
  mambo_security_review_model_id: null as string | null,
  mambo_security_review_system_prompt: '',
  mambo_security_review_tools: [] as string[],
  mambo_version_control_enabled: false,
  mambo_mcp_threshold: 15,
});

const availableBackends = computed(() => backendList.value.filter(b => !form.backendIds.includes(b.id)));
const mountedBackendList = computed(() => form.backendIds.map(id => backendList.value.find(b => b.id === id) || { id, name: 'Unknown Backend', backendType: 'unknown' }));

function handleAddBackend(backendId: string) {
  if (!form.backendIds.includes(backendId)) form.backendIds.push(backendId);
}
function handleRemoveBackend(backendId: string) {
  form.backendIds = form.backendIds.filter(id => id !== backendId);
}

const availableMcps = computed(() => activeUserMcpServices.value.filter(mcp => !form.enabledMcpIds.includes(mcp.id)));
const mountedMcpList = computed(() => form.enabledMcpIds.map(id => activeUserMcpServices.value.find(mcp => mcp.id === id) || { id, name: 'Unknown MCP' }));

function handleAddMcp(mcpId: string) {
  if (!form.enabledMcpIds.includes(mcpId)) form.enabledMcpIds.push(mcpId);
}
function handleRemoveMcp(mcpId: string) {
  form.enabledMcpIds = form.enabledMcpIds.filter(id => id !== mcpId);
}

const filteredGroupedModels = computed(() => groupedModels.value.map(group => ({ label: group.label, options: group.options.filter(m => m.model_type === 'chat') })).filter(group => group.options.length > 0));

const dynamicParameters = computed(() => {
  if (!form.aiModelId) return [];
  const currentModel = allModels.value.find(m => m.id === form.aiModelId);
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? []);
  const coreParameters = ['temperature', 'top_p'];
  return systemConfigStore.llmParameters.filter(p => coreParameters.includes(p.key) || supportedParameters.has(p.key) || p.default_activate).map(p => ({
    key: p.key, label: p.label, description: p.description, type: p.type, limit: p.limit,
    isEnabled: Object.prototype.hasOwnProperty.call(form.modelParameters, p.key), definition: p
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
    Object.keys(params).forEach(key => { if (params[key] === null) params[key] = undefined; });

    form.modelParameters = { ...params, max_context_messages: params.max_context_messages ?? 0, stream: params.stream ?? true };
    form.agentAvatarUrl = newVal.agentAvatarUrl || null;
    form.enabledMcpIds = newVal.enabledMcpIds ? [...newVal.enabledMcpIds] : [];
    form.subAgents = newVal.subAgents ? [...newVal.subAgents] : [];
    form.backendIds = newVal.backendIds ? [...newVal.backendIds] : [];
    form.defaultBackendId = (newVal as any).defaultBackendId || null;

    // Mambo 专属配置还原
    const mamboParams: MamboAgentParameters = newVal.agentParameters ?? {
      include_general_purpose: false, enable_planning: true, enable_memory: false,
      enable_summarization: false, enable_show: true, memory_resource_ids: [],
      summarization_config: null, security_review: null,
      mcp_direct_tool_threshold: 15,
    };
    form.mambo_general_purpose = mamboParams.include_general_purpose ?? false;
    form.mambo_planning_enabled = mamboParams.enable_planning ?? true;
    form.mambo_show_enabled = mamboParams.enable_show ?? true;
    form.mambo_memory_enabled = mamboParams.enable_memory ?? false;
    form.mambo_memory_resource_ids = mamboParams.memory_resource_ids ? [...mamboParams.memory_resource_ids] : [];
    form.mambo_summary_enabled = mamboParams.enable_summarization ?? false;
    if (mamboParams.summarization_config) {
      form.mambo_summary_trigger_type = mamboParams.summarization_config.trigger_type || 'tokens';
      form.mambo_summary_trigger_value = mamboParams.summarization_config.trigger_value ?? 180000;
      form.mambo_summary_keep_type = mamboParams.summarization_config.keep_type || 'messages';
      form.mambo_summary_keep_value = mamboParams.summarization_config.keep_value ?? 20;
      form.mambo_summary_offload = mamboParams.summarization_config.offload_to_backend ?? false;
    } else {
      form.mambo_summary_trigger_type = 'tokens'; form.mambo_summary_trigger_value = 180000;
      form.mambo_summary_keep_type = 'messages'; form.mambo_summary_keep_value = 20;
      form.mambo_summary_offload = false;
    }
    const srCfg = mamboParams.security_review;
    if (srCfg && srCfg.enabled) {
      form.mambo_security_review_enabled = true;
      form.mambo_security_review_model_id = srCfg.model_id || null;
      form.mambo_security_review_system_prompt = srCfg.system_prompt || '';
      form.mambo_security_review_tools = (srCfg.review_tools || []) as string[];
    } else {
      form.mambo_security_review_enabled = false;
      form.mambo_security_review_model_id = null;
      form.mambo_security_review_system_prompt = '';
      form.mambo_security_review_tools = [];
    }
    const vcCfg = mamboParams.version_control;
    form.mambo_version_control_enabled = !!(vcCfg && vcCfg.enabled);
    form.mambo_mcp_threshold = mamboParams.mcp_direct_tool_threshold ?? 15;

    fetchHitlTools(newVal.id);

    if (newVal.resourcePromptList && newVal.resourcePromptList.length > 0) {
      try { mountedResources.value = (await Promise.all(newVal.resourcePromptList.map(id => getResourceDetails(id)))).filter(r => !!r) as Resource[]; }
      catch { mountedResources.value = []; }
    } else { mountedResources.value = []; }

    if (newVal.subAgents && newVal.subAgents.length > 0) {
      try { mountedSubAgents.value = (await Promise.all(newVal.subAgents.map(id => getAgent(id)))).filter(r => !!r) as Agent[]; }
      catch { mountedSubAgents.value = []; }
    } else { mountedSubAgents.value = []; }

    if (form.mambo_memory_resource_ids.length > 0) {
      try {
        const promises = form.mambo_memory_resource_ids.map(id => getResourceDetails(id).catch(() => null));
        const results = await Promise.all(promises);
        mountedMemoryResources.value = results.filter(r => !!r) as Resource[];
      } catch { mountedMemoryResources.value = []; }
    } else { mountedMemoryResources.value = []; }
  }
}, { immediate: true, deep: true });

watch(() => form.aiModelId, (newModelId) => {
  if (!newModelId) return;
  const currentModel = allModels.value.find(m => m.id === newModelId);
  if (!currentModel) return;
  const supportedParams = new Set(currentModel.meta_config?.supported_parameters ?? []);
  const keysToKeep = new Set(['max_context_messages', 'stream', 'temperature', 'top_p']);
  systemConfigStore.llmParameters.forEach(p => { if (supportedParams.has(p.key) || p.default_activate) keysToKeep.add(p.key); });
  const newParams: Record<string, AgentModelParameterValue> = {};
  for (const key in form.modelParameters) { if (keysToKeep.has(key)) newParams[key] = form.modelParameters[key]; }
  form.modelParameters = newParams;
});

watch(() => form.mambo_summary_trigger_type, (newType) => {
  if (newType === 'fraction') form.mambo_summary_trigger_value = 0.9;
  else if (newType === 'tokens') form.mambo_summary_trigger_value = 180000;
  else if (newType === 'messages') form.mambo_summary_trigger_value = 200;
});

watch(() => form.mambo_summary_keep_type, (newType) => {
  if (newType === 'fraction') form.mambo_summary_keep_value = 0.2;
  else if (newType === 'tokens') form.mambo_summary_keep_value = 40000;
  else if (newType === 'messages') form.mambo_summary_keep_value = 20;
});

function getSliderStep(min: number, max: number): number {
  const range = max - min;
  if (range <= 2) return 0.01;
  if (range <= 20) return 0.1;
  return 1;
}

function handleToggleParameter(param: { key: string; definition: { default_value: unknown } }, isEnabled: boolean) {
  const newParams = { ...form.modelParameters };
  if (isEnabled) { newParams[param.key] = (param.definition.default_value ?? undefined) as AgentModelParameterValue; }
  else { delete newParams[param.key]; }
  form.modelParameters = newParams;
}

// 与后端 validate_mounted_resources 保持一致的同名池：
// knowledge_base / skill 各自独立池；file / system_prompt / submessage_template 共享池；kb_file 等不参与检查
function getMountPoolKey(resourceType: string | null | undefined): string | null {
  if (resourceType === 'knowledge_base') return 'kb';
  if (resourceType === 'skill') return 'skill';
  if (resourceType === 'file' || resourceType === 'system_prompt' || resourceType === 'submessage_template') return 'leaf';
  return null;
}

function findDuplicateMountName(list: Resource[]): string | null {
  const pools: Record<string, Set<string>> = {};
  for (const r of list) {
    if ((r as any)._deleted) continue;
    const pool = getMountPoolKey(r.resourceType);
    if (!pool) continue;
    if (!pools[pool]) pools[pool] = new Set();
    if (pools[pool].has(r.name)) return r.name;
    pools[pool].add(r.name);
  }
  return null;
}

function handleMountResources(resources: Resource[]) {
  if (resources.length === 0) return;
  const existingIds = new Set(mountedResources.value.map(r => r.id));
  const newResources = resources.filter(r => !existingIds.has(r.id));
  if (newResources.length === 0) return;

  const combined = [...mountedResources.value.filter(r => !(r as any)._deleted), ...newResources];
  const duplicate = findDuplicateMountName(combined);
  if (duplicate) {
    ElMessage.error(t('agent.duplicateMountResource', { name: duplicate }));
    return;
  }

  mountedResources.value = [...mountedResources.value, ...newResources];
  ElMessage.success(t('common.msg.updateSuccess'));
}

function handleMountSubAgents(agents: Agent[]) {
  const seen = new Set<string>();
  const duplicate = agents.find(a => {
    if (seen.has(a.name)) return true;
    seen.add(a.name);
    return false;
  });
  if (duplicate) {
    ElMessage.error(t('agent.duplicateSubAgentName', { name: duplicate.name }));
    return;
  }
  mountedSubAgents.value = agents;
  form.subAgents = agents.map(a => a.id);
}

function handleRemoveSubAgent(id: string) {
  mountedSubAgents.value = mountedSubAgents.value.filter(a => a.id !== id);
  form.subAgents = mountedSubAgents.value.map(a => a.id);
}

function handleMountMemory(resources: Resource[]) {
  if (resources.length === 0) return;
  const existingIds = new Set(mountedMemoryResources.value.map(r => r.id));
  const newResources = resources.filter(r => !existingIds.has(r.id));
  if (newResources.length === 0) return;

  const combined = [...mountedMemoryResources.value.filter(r => !(r as any)._deleted), ...newResources];
  const names = new Set<string>();
  const duplicate = combined.find(r => {
    if (names.has(r.name)) return true;
    names.add(r.name);
    return false;
  });
  if (duplicate) {
    ElMessage.error(t('agent.duplicateMountResource', { name: duplicate.name }));
    return;
  }

  mountedMemoryResources.value = [...mountedMemoryResources.value, ...newResources];
  form.mambo_memory_resource_ids = mountedMemoryResources.value.map(r => r.id);
}

function handleRemoveMemory(id: string) {
  mountedMemoryResources.value = mountedMemoryResources.value.filter(r => r.id !== id);
  form.mambo_memory_resource_ids = mountedMemoryResources.value.map(r => r.id);
}

function getMemoryTypeLabel(type: string | undefined): string {
  if (type === 'knowledge_base') return t('resource.type.knowledgeBase');
  if (type === 'system_prompt') return t('resource.type.systemPrompt');
  if (type === 'submessage_template') return t('resource.type.submessageTemplate');
  return t('resource.type.file');
}

async function fetchHitlTools(agentId: string) {
  try {
    hitlToolOptions.value = await getAgentHitlTools(agentId);
    hitlToolOptionsLoaded.value = true;
  } catch { hitlToolOptions.value = []; }
}

function buildMamboAgentParameters(): MamboAgentParameters | null {
  return {
    include_general_purpose: form.mambo_general_purpose,
    enable_planning: form.mambo_planning_enabled,
    enable_show: form.mambo_show_enabled,
    enable_memory: form.mambo_memory_enabled,
    enable_summarization: form.mambo_summary_enabled,
    memory_resource_ids: form.mambo_memory_enabled ? [...form.mambo_memory_resource_ids] : [],
    summarization_config: form.mambo_summary_enabled ? {
      trigger_type: form.mambo_summary_trigger_type,
      trigger_value: form.mambo_summary_trigger_value,
      keep_type: form.mambo_summary_keep_type,
      keep_value: form.mambo_summary_keep_value,
      offload_to_backend: form.mambo_summary_offload,
    } : null,
    security_review: form.mambo_security_review_enabled ? {
      enabled: true,
      model_id: form.mambo_security_review_model_id || null,
      system_prompt: form.mambo_security_review_system_prompt || null,
      review_tools: form.mambo_security_review_tools.length > 0 ? [...form.mambo_security_review_tools] : null,
    } : null,
    version_control: form.mambo_version_control_enabled ? { enabled: true, auto_snapshot: true } : null,
    mcp_direct_tool_threshold: form.mambo_mcp_threshold,
  };
}

async function handleUploadAvatar(file: File) {
  if (!currentAgentId.value) return;
  isAvatarLoading.value = true;
  try {
    const response = await uploadAgentAvatar(currentAgentId.value, file);
    form.agentAvatarUrl = response.url;
    if (agentData.value) { agentData.value.agentAvatarUrl = response.url; agentData.value.agentAvatarId = response.id; }
    ElMessage.success(t('agent.avatarUploadSuccess'));
  } catch { ElMessage.error(t('agent.avatarUploadFailed')); }
  finally { isAvatarLoading.value = false; }
}

async function handleDeleteAvatar() {
  if (!currentAgentId.value) return;
  isAvatarLoading.value = true;
  try {
    await deleteAgentAvatar(currentAgentId.value);
    form.agentAvatarUrl = null;
    if (agentData.value) { agentData.value.agentAvatarUrl = null; agentData.value.agentAvatarId = null; }
    ElMessage.success(t('agent.avatarDeleteSuccess'));
  } catch { ElMessage.error(t('agent.avatarDeleteFailed')); }
  finally { isAvatarLoading.value = false; }
}

async function handleSave() {
  if (!currentAgentId.value) return;
  isSaving.value = true;
  try {
    const resourcePromptList = mountedResources.value.map(r => r.id);
    const finalModelParameters: Record<string, AgentModelParameterValue> = {
      max_context_messages: form.modelParameters.max_context_messages,
      stream: form.modelParameters.stream
    };
    for (const key in form.modelParameters) {
      if (Object.prototype.hasOwnProperty.call(form.modelParameters, key)) {
        if (key === 'max_context_messages' || key === 'stream') continue;
        finalModelParameters[key] = form.modelParameters[key];
      }
    }
    const finalBackendIds = (form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') ? [...form.backendIds] : [];

    await agentStore.updateAgentSettings(currentAgentId.value, {
      name: form.name,
      description: form.description,
      AgentType: form.AgentType as AgentType,
      systemPrompt: form.systemPrompt,
      aiModelId: form.aiModelId,
      modelParameters: finalModelParameters,
      resourcePromptList: resourcePromptList.length > 0 ? [...resourcePromptList] : [],
      enabledMcpIds: form.enabledMcpIds.length > 0 ? [...form.enabledMcpIds] : [],
      subAgents: (form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') && form.subAgents.length > 0 ? [...form.subAgents] : [],
      backendIds: finalBackendIds,
      defaultBackendId: form.defaultBackendId,
      memoryResourceIds: form.AgentType === 'Mambo' && form.mambo_memory_enabled ? [...form.mambo_memory_resource_ids] : [],
      securityReviewConfig: form.AgentType === 'Mambo' && form.mambo_security_review_enabled ? {
        enabled: true,
        model_id: form.mambo_security_review_model_id || null,
        system_prompt: form.mambo_security_review_system_prompt || null,
        review_tools: form.mambo_security_review_tools.length > 0 ? [...form.mambo_security_review_tools] : null,
      } : null,
      agentParameters: form.AgentType === 'Mambo' ? buildMamboAgentParameters() : null,
    });
    ElMessage.success(t('agent.saveSuccess'));
  } catch { ElMessage.error(t('agent.saveFailed')); }
  finally { isSaving.value = false; }
}

onMounted(() => {
  providerStore.fetchProviders();
  systemConfigStore.fetchSystemConfig();
  if (backendStore.backendList.length === 0) backendStore.fetchBackends();
});
</script>

<style scoped>
.mobile-agent-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-background);
}

/* ===== Header (Frosted Glass) ===== */
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  padding-top: max(8px, env(safe-area-inset-top));
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
  z-index: 10;
}

/* ===== Editor Body ===== */
.editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  -webkit-overflow-scrolling: touch;
}

.body-spacer {
  height: 80px;
}

/* ===== Section Card ===== */
.section-card {
  background: var(--color-background-soft);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 14px;
  border: 0.5px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 14px;
  background: var(--el-color-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

/* ===== Basic Info ===== */
.basic-info-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.avatar-section {
  padding-top: 4px;
}

.info-section {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ===== Field Items ===== */
.field-item {
  margin-bottom: 14px;
}

.field-item:last-child {
  margin-bottom: 0;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}

.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  gap: 12px;
}

.field-row + .field-row {
  border-top: 0.5px solid rgba(0, 0, 0, 0.05);
}

.tip-icon {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  cursor: help;
}

/* ===== Native Inputs ===== */
.native-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  font-size: 15px;
  font-family: inherit;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  border: none;
  border-radius: 10px;
  box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;
  outline: none;
  box-sizing: border-box;
  transition: box-shadow 0.2s;
}

.native-input:focus {
  box-shadow: 0 0 0 2px var(--el-color-primary) inset;
}

.native-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  border: none;
  border-radius: 10px;
  box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;
  outline: none;
  resize: vertical;
  box-sizing: border-box;
  transition: box-shadow 0.2s;
}

.native-textarea:focus {
  box-shadow: 0 0 0 2px var(--el-color-primary) inset;
}

/* ===== Parameter Controls ===== */
.param-control {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  justify-content: flex-end;
}

.param-slider {
  flex: 1;
  min-width: 0;
}

.param-input-num {
  width: 100%;
}

.param-enable-switch {
  flex-shrink: 0;
}

.param-select {
  flex: 1;
}

.param-native-input {
  flex: 1;
  height: 32px;
  font-size: 13px;
}

/* ===== Chip Area ===== */
.chip-area {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-height: 36px;
}

.chip-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border: none;
  border-radius: 16px;
  cursor: pointer;
  transition: background 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.chip-add-btn:active {
  background: var(--el-color-primary-light-7);
}

.chip-add-warning {
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
}

.chip-add-warning:active {
  background: var(--el-color-warning-light-7);
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color);
  border-radius: 14px;
  border: 0.5px solid var(--el-border-color-lighter);
}

.chip-primary {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
}

.chip-warning {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
  border-color: var(--el-color-warning-light-7);
}

.chip-danger {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  border-color: var(--el-color-danger-light-7);
}

.chip-success {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success-dark-2);
  border-color: var(--el-color-success-light-7);
}

.chip-stale {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
  border-color: var(--el-color-warning-light-7);
}

.chip-star {
  font-size: 10px;
  margin-left: 2px;
}

.stale-tools-hint {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.section-divider {
  height: 1px;
  background: rgba(0, 0, 0, 0.06);
  margin: 10px 0;
}

.param-row-split {
  display: flex;
  gap: 10px;
  align-items: center;
}

.chip-text {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-avatar {
  background: transparent;
  flex-shrink: 0;
}

.chip-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  margin-left: 2px;
  font-size: 14px;
  line-height: 1;
  color: inherit;
  opacity: 0.5;
  background: none;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.chip-close:active {
  opacity: 0.8;
  background: rgba(0, 0, 0, 0.08);
}

.chip-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

/* ===== Save Bar ===== */
.save-bar {
  flex-shrink: 0;
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-top: 0.5px solid rgba(0, 0, 0, 0.08);
}

.save-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 46px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  border: none;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.35);
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
  -webkit-tap-highlight-color: transparent;
}

.save-btn:active {
  transform: scale(0.98);
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ===== Bottom Sheet ===== */
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet-panel {
  width: 100%;
  max-width: 500px;
  max-height: 70vh;
  background: var(--el-bg-color);
  border-radius: 16px 16px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 2px;
  margin: 10px auto 0;
  flex-shrink: 0;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 8px;
  flex-shrink: 0;
}

.sheet-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.sheet-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: var(--el-fill-color-light);
  border-radius: 50%;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.sheet-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 16px 20px;
  -webkit-overflow-scrolling: touch;
}

.sheet-empty {
  padding: 30px 0;
}

.sheet-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 14px 12px;
  margin-bottom: 6px;
  background: var(--color-background-soft);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.sheet-item:active {
  background: var(--el-fill-color);
}

.sheet-item-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.sheet-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.sheet-item-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sheet-item-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sheet-item-arrow {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

/* ===== Sheet Transitions ===== */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}

.sheet-enter-active .sheet-panel,
.sheet-leave-active .sheet-panel {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}

.sheet-enter-from .sheet-panel,
.sheet-leave-to .sheet-panel {
  transform: translateY(100%);
}

/* ===== Empty State ===== */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  background: var(--color-background);
}

/* ===== Dark Mode ===== */
@media (prefers-color-scheme: dark) {
  .editor-header {
    background: rgba(30, 30, 30, 0.72);
    border-bottom-color: rgba(255, 255, 255, 0.08);
  }

  .section-card {
    border-color: rgba(255, 255, 255, 0.06);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  }

  .section-title {
    border-bottom-color: rgba(255, 255, 255, 0.06);
  }

  .field-row + .field-row {
    border-top-color: rgba(255, 255, 255, 0.05);
  }

  .native-input,
  .native-textarea {
    box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
  }

  .native-input:focus,
  .native-textarea:focus {
    box-shadow: 0 0 0 2px var(--el-color-primary) inset;
  }

  .save-bar {
    background: rgba(30, 30, 30, 0.88);
    border-top-color: rgba(255, 255, 255, 0.08);
  }

  .sheet-handle {
    background: rgba(255, 255, 255, 0.2);
  }

  .chip-close:active {
    background: rgba(255, 255, 255, 0.1);
  }

  .section-divider {
    background: rgba(255, 255, 255, 0.06);
  }
}
</style>
