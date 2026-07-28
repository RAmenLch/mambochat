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
                      <el-option label="Mambo Agent" value="Mambo" />
                      <el-option label="Deep Agent" value="DeepAgent" />
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
          </el-row>

          <el-row :gutter="40" v-if="form.aiModelId">
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
                  <el-select
                    v-else-if="param.type === 'string' && Array.isArray(param.limit)"
                    v-model="form.modelParameters[param.key]"
                    :disabled="!param.isEnabled"
                    class="parameter-input"
                  >
                    <el-option v-for="opt in param.limit" :key="opt" :label="opt" :value="opt" />
                  </el-select>
                  <el-input
                    v-else-if="param.type === 'string'"
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
                      :class="{ 'custom-tag': true, 'deleted-tag': mcp.name === 'Unknown MCP' }"
                      @close="handleRemoveMcp(mcp.id)"
                    >
                      <div class="tag-inner">
                        <el-icon class="tag-icon"><Connection /></el-icon>
                        <span class="tag-text">{{ mcp.name === 'Unknown MCP' ? t('common.status.unknownMcp') + ' (ID: ' + mcp.id.substring(0, 8) + '...)' : mcp.name }}</span>
                      </div>
                    </el-tag>
                  </div>
                  <div v-else class="empty-mount">
                    {{ $t('agent.noMcp') }}
                  </div>
                </div>
              </el-form-item>
            </el-col>

            <el-col :span="12" v-if="form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo'">
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
                      :type="(subAgent as any)._deleted ? 'info' : 'primary'"
                      effect="light"
                      :class="{ 'custom-tag': true, 'deleted-tag': (subAgent as any)._deleted }"
                      @close="handleRemoveSubAgent(subAgent.id)"
                    >
                      <div class="tag-inner">
                        <el-avatar v-if="!(subAgent as any)._deleted" :size="14" :src="resolveFileUrl(subAgent.agentAvatarUrl) ?? undefined" :icon="User" class="tag-avatar" />
                        <el-icon v-else><WarningFilled /></el-icon>
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

          <!-- 第三行：Backend 挂载 (仅 DeepAgent / Mambo 可见) -->
          <el-row :gutter="32" class="settings-row" v-if="form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo'">
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
                      :type="b.name === 'Unknown Backend' ? 'info' : (b.id === form.defaultBackendId ? 'danger' : 'warning')"
                      effect="light"
                      :class="{ 'custom-tag': true, 'deleted-tag': b.name === 'Unknown Backend' }"
                      @close="handleRemoveBackend(b.id)"
                    >
                      <div class="tag-inner">
                        <el-icon class="tag-icon"><Monitor /></el-icon>
                        <span class="tag-text">{{ b.name === 'Unknown Backend' ? t('common.status.unknownBackend') + ' (ID: ' + b.id.substring(0, 8) + '...)' : b.name }}</span>
                        <span v-if="b.id === form.defaultBackendId && b.name !== 'Unknown Backend'" class="default-star">★</span>
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

        <!-- 4. Mambo 专属配置 (仅 Mambo 类型可见) -->
        <el-card v-if="form.AgentType === 'Mambo'" shadow="never" class="config-card">
          <template #header>
            <span class="card-title">{{ $t('agent.mamboConfig') }}</span>
          </template>

          <!-- General Purpose 子代理 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.generalPurpose') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.generalPurposeDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_general_purpose" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 计划任务清单 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.mamboPlanning') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.mamboPlanningDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_planning_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- show 工具（展示文件/图片给用户） -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.mamboShow') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.mamboShowDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_show_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 长期记忆 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.mamboMemory') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.mamboMemoryDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_memory_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 记忆资源（仅开启记忆后显示） -->
          <template v-if="form.mambo_memory_enabled">
            <el-row :gutter="32" class="settings-row">
              <el-col :span="24">
                <el-form-item :label="$t('agent.memoryResources')">
                  <div class="mount-container" style="height: auto; min-height: 100px;">
                    <div class="mount-action">
                      <el-button type="primary" plain size="small" @click="memorySelectorVisible = true">
                        <el-icon><Collection /></el-icon> {{ $t('agent.mountMemory') }}
                      </el-button>
                    </div>
                    <div v-if="mountedMemoryResources.length > 0" class="tag-list-wrapper">
                      <el-tag
                        v-for="res in mountedMemoryResources"
                        :key="res.id"
                        closable
                        type="success"
                        effect="light"
                        class="custom-tag"
                        @close="handleRemoveMemory(res.id)"
                      >
                        <div class="tag-inner">
                          <span class="tag-text">{{ res.name }}</span>
                          <span class="memory-type-hint">({{ getMemoryTypeLabel(res.resourceType ?? undefined) }})</span>
                        </div>
                      </el-tag>
                    </div>
                    <div v-else class="empty-mount">
                      {{ $t('agent.noMemory') }}
                    </div>
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
          </template>

          <!-- 对话摘要 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.summarization') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.summarizationDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_summary_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 摘要参数（仅开启摘要后显示） -->
          <template v-if="form.mambo_summary_enabled">
            <p v-if="form.mambo_summary_trigger_type === 'fraction' || form.mambo_summary_keep_type === 'fraction'" class="mambo-fraction-warning">
              <el-icon><WarningFilled /></el-icon> {{ $t('agent.fractionWarning') }}
            </p>

            <el-row :gutter="32" class="settings-row">
              <el-col :span="12">
                <el-form-item :label="$t('agent.summarizationTrigger')">
                  <el-select v-model="form.mambo_summary_trigger_type" style="width: 100%">
                    <el-option :label="$t('agent.triggerFraction')" value="fraction" />
                    <el-option :label="$t('agent.triggerTokens')" value="tokens" />
                    <el-option :label="$t('agent.triggerMessages')" value="messages" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item>
                  <template #label>&nbsp;</template>
                  <el-input-number
                    v-model="form.mambo_summary_trigger_value"
                    :min="form.mambo_summary_trigger_type === 'fraction' ? 0.1 : 1"
                    :max="form.mambo_summary_trigger_type === 'fraction' ? 1 : 1000000"
                    :step="form.mambo_summary_trigger_type === 'fraction' ? 0.05 : 1000"
                    :precision="form.mambo_summary_trigger_type === 'fraction' ? 2 : 0"
                    controls-position="right"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="32" class="settings-row">
              <el-col :span="12">
                <el-form-item :label="$t('agent.summarizationKeep')">
                  <el-select v-model="form.mambo_summary_keep_type" style="width: 100%">
                    <el-option :label="$t('agent.keepFraction')" value="fraction" />
                    <el-option :label="$t('agent.keepTokens')" value="tokens" />
                    <el-option :label="$t('agent.keepMessages')" value="messages" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item>
                  <template #label>&nbsp;</template>
                  <el-input-number
                    v-model="form.mambo_summary_keep_value"
                    :min="form.mambo_summary_keep_type === 'fraction' ? 0.01 : 1"
                    :max="form.mambo_summary_keep_type === 'fraction' ? 1 : 500000"
                    :step="form.mambo_summary_keep_type === 'fraction' ? 0.05 : 1000"
                    :precision="form.mambo_summary_keep_type === 'fraction' ? 2 : 0"
                    controls-position="right"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="32" class="settings-row">
              <el-col :span="24">
                <el-form-item>
                  <template #label>
                    <span>{{ $t('agent.summarizationOffload') }}</span>
                    <el-tooltip effect="dark" :content="$t('agent.summarizationOffloadDesc')" placement="top">
                      <el-icon class="label-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </template>
                  <el-switch v-model="form.mambo_summary_offload" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>

          <el-divider />

          <!-- 版本控制 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.versionControl') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.versionControlDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_version_control_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider />

          <!-- MCP 工具阈值 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.mcpThreshold') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.mcpThresholdDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.mambo_mcp_threshold"
                  :min="0"
                  :step="1"
                  controls-position="right"
                  style="width: 200px;"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider />

          <!-- AI 安全审核 -->
          <el-row :gutter="32" class="settings-row">
            <el-col :span="24">
              <el-form-item>
                <template #label>
                  <span>{{ $t('agent.securityReviewEnable') }}</span>
                  <el-tooltip effect="dark" :content="$t('agent.securityReviewEnableDesc')" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.mambo_security_review_enabled" />
              </el-form-item>
            </el-col>
          </el-row>

          <template v-if="form.mambo_security_review_enabled">
            <el-row :gutter="32" class="settings-row">
              <el-col :span="12">
                <el-form-item :label="$t('agent.securityReviewModel')">
                  <el-select v-model="form.mambo_security_review_model_id" :placeholder="$t('agent.securityReviewModelPlaceholder')" style="width: 100%" clearable>
                    <el-option-group v-for="group in filteredGroupedModels" :key="group.label" :label="group.label">
                      <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
                    </el-option-group>
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="32" class="settings-row">
              <el-col :span="24">
                <el-form-item :label="$t('agent.securityReviewTools')">
                  <el-select
                    v-model="form.mambo_security_review_tools"
                    multiple
                    filterable
                    :placeholder="$t('agent.securityReviewToolsPlaceholder')"
                    style="width: 100%"
                    :no-data-text="$t('agent.securityReviewToolsEmpty')"
                  >
                    <el-option
                      v-for="tool in hitlToolOptions"
                      :key="tool.name"
                      :label="tool.name"
                      :value="tool.name"
                    >
                      <span style="float: left">{{ tool.name }}</span>
                      <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px; margin-left: 12px;">
                        {{ tool.source === 'backend' ? 'Backend' : 'MCP' }}
                      </span>
                    </el-option>
                  </el-select>
                  <div v-if="staleToolNames.length > 0" class="stale-tools-warning">
                    <el-icon><WarningFilled /></el-icon>
                    <span>{{ $t('agent.securityReviewToolsStale') }}：</span>
                    <el-tag
                      v-for="name in staleToolNames"
                      :key="name"
                      type="warning"
                      size="small"
                      closable
                      @close="removeReviewTool(name)"
                    >
                      <s>{{ name }}</s>
                    </el-tag>
                  </div>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="32" class="settings-row">
              <el-col :span="24">
                <el-form-item :label="$t('agent.securityReviewPrompt')">
                  <el-input v-model="form.mambo_security_review_system_prompt" type="textarea" :rows="6" :placeholder="DEFAULT_SECURITY_REVIEW_SYSTEM_PROMPT" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>
        </el-card>


      </el-form>
    </el-scrollbar>

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      :context="(form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') ? 'agent-deep' : 'agent-react'"
      @mount-resources="handleMountResources"
    />

    <AgentSelectorDialog
      v-if="currentAgentId"
      v-model:visible="agentSelectorVisible"
      :current-agent-id="currentAgentId"
      :initial-selected-ids="form.subAgents"
      @select="handleMountSubAgents"
    />

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
import { User, QuestionFilled, Collection, Plus, Connection, Monitor, WarningFilled } from '@element-plus/icons-vue';
import { resolveFileUrl } from '@/services/electronUrl';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore';
import { useMcpStore } from '@/stores/mcpStore';
import { useBackendStore } from '@/stores/backendStore'; // [新增] 引入 BackendStore

import { uploadAgentAvatar, deleteAgentAvatar, getAgent, getAgentHitlTools } from '@/api/agentService';
import { getResourceDetails } from '@/api/resourceService';
import type { Resource, Agent, HitlToolInfo, MamboAgentParameters } from '@/api/types';

import AvatarUploader from '../AvatarUploader.vue';
import ResourceSelectorDialog from '@/components/common/dialogs/ResourceSelectorDialog.vue';
import AgentSelectorDialog from './dialogs/AgentSelectorDialog.vue';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';
import { useModelSelectScroll } from '@/composables/useModelSelectScroll';

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
- Modifying files outside the project workspace without explicit user intent
- Network operations that send data to external servers

### Decision Rules:
- When in doubt, lean toward flagging as unsafe (is_safe=False)
- If the operation only affects the user's own project files and is non-destructive, mark as safe
- If the operation could affect system stability or security, mark as unsafe
- Consider the context: a file write to a project's config file is usually safe;
  a file write to system configuration is not

Respond with your structured assessment.`;
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
const memorySelectorVisible = ref(false);
const modelSelectRef = ref();
const { scrollToTopIfStarred } = useModelSelectScroll();

const hitlToolOptions = ref<HitlToolInfo[]>([]);
const hitlToolOptionsLoaded = ref(false);

/** 已保存但当前不在 HITL 中的工具（用户之前选了，后来被取消审核） */
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
  name: '',
  description: '',
  AgentType: 'ReActAgent',
  systemPrompt: '',
  aiModelId: null as string | null,
  modelParameters: {} as Record<string, any>,
  agentAvatarUrl: null as string | null,
  enabledMcpIds: [] as string[],
  subAgents: [] as string[],
  backendIds: [] as string[],
  defaultBackendId: null as string | null,

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

  // Mambo 安全审核
  mambo_security_review_enabled: false,
  mambo_security_review_model_id: null as string | null,
  mambo_security_review_system_prompt: '',
  mambo_security_review_tools: [] as string[],

  // Mambo 版本控制
  mambo_version_control_enabled: false,

  // Mambo MCP 工具阈值
  mambo_mcp_threshold: 15,
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
    form.backendIds = newVal.backendIds ? [...newVal.backendIds] : [];
    form.defaultBackendId = (newVal as any).defaultBackendId || null;

    // Mambo 专属配置还原（结构化访问）
    const mamboParams: MamboAgentParameters = newVal.agentParameters ?? {
      include_general_purpose: false,
      enable_planning: true,
      enable_memory: false,
      enable_summarization: false,
      enable_show: true,
      memory_resource_ids: [],
      summarization_config: null,
      security_review: null,
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
      form.mambo_summary_trigger_type = 'tokens';
      form.mambo_summary_trigger_value = 180000;
      form.mambo_summary_keep_type = 'messages';
      form.mambo_summary_keep_value = 20;
      form.mambo_summary_offload = false;
    }

    // 安全审核配置还原
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

    // 版本控制配置还原
    const vcCfg = mamboParams.version_control;
    if (vcCfg && vcCfg.enabled) {
      form.mambo_version_control_enabled = true;
    } else {
      form.mambo_version_control_enabled = false;
    }

    // MCP 工具阈值
    form.mambo_mcp_threshold = mamboParams.mcp_direct_tool_threshold ?? 15;

    // 加载 HITL 可审核工具列表
    fetchHitlTools(newVal.id);

    if (newVal.resourcePromptList && newVal.resourcePromptList.length > 0) {
      const rpList = newVal.resourcePromptList;
      try {
        const promises = rpList.map(id => getResourceDetails(id).catch(() => null));
        const results = await Promise.all(promises);
        // 已删除的资源创建占位 stub，保留顺序，引导用户取消选择
        mountedResources.value = results.map((r, i) => {
          if (r) return r;
          const id = rpList[i];
          return { id, name: t('resource.deletedNameWithId', { id: id.substring(0, 8) }), resourceType: 'file', _deleted: true } as unknown as Resource;
        });
      } catch (error) {
        console.error('Failed to load agent resources:', error);
        mountedResources.value = [];
      }
    } else {
      mountedResources.value = [];
    }

    if (newVal.subAgents && newVal.subAgents.length > 0) {
      const saList = newVal.subAgents;
      try {
        const promises = saList.map(id => getAgent(id).catch(() => null));
        const results = await Promise.all(promises);
        mountedSubAgents.value = results.map((r, i) => {
          if (r) return r;
          const id = saList[i];
          return { id, name: t('agent.subAgentDeleted', { id: id.substring(0, 8) }), AgentType: 'ReActAgent', _deleted: true } as unknown as Agent;
        });
      } catch (error) {
        console.error('Failed to load sub agents:', error);
        mountedSubAgents.value = [];
      }
    } else {
      mountedSubAgents.value = [];
    }

    // 加载 memory 资源详情
    if (form.mambo_memory_resource_ids.length > 0) {
      try {
        const promises = form.mambo_memory_resource_ids.map(id => getResourceDetails(id).catch(() => null));
        const results = await Promise.all(promises);
        mountedMemoryResources.value = results.map((r, i) => {
          if (r) return r;
          const id = form.mambo_memory_resource_ids[i];
          return { id, name: t('resource.deletedNameWithId', { id: id.substring(0, 8) }), resourceType: 'file', _deleted: true } as unknown as Resource;
        });
      } catch (error) {
        console.error('Failed to load memory resources:', error);
        mountedMemoryResources.value = [];
      }
    } else {
      mountedMemoryResources.value = [];
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

// 摘要类型切换时，自动匹配对应模式的默认值
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

// --- Memory 挂载逻辑 ---
function handleMountMemory(resources: Resource[]) {
  if (resources.length === 0) return;
  const existingIds = new Set(mountedMemoryResources.value.map(r => r.id));
  const newResources = resources.filter(r => !existingIds.has(r.id));

  if (newResources.length > 0) {
    mountedMemoryResources.value = [...mountedMemoryResources.value, ...newResources];
    form.mambo_memory_resource_ids = mountedMemoryResources.value.map(r => r.id);
    ElMessage.success(t('common.msg.updateSuccess'));
  }
}

function handleRemoveMemory(id: string) {
  mountedMemoryResources.value = mountedMemoryResources.value.filter(r => r.id !== id);
  form.mambo_memory_resource_ids = mountedMemoryResources.value.map(r => r.id);
}

function getMemoryTypeLabel(type: string | undefined): string {
  const labels: Record<string, string> = {
    file: 'File',
    system_prompt: 'System Prompt',
    submessage_template: 'Template',
  };
  return labels[type ?? ''] ?? type ?? 'Unknown';
}

async function fetchHitlTools(agentId: string) {
  hitlToolOptionsLoaded.value = false;
  try {
    hitlToolOptions.value = await getAgentHitlTools(agentId);
  } catch {
    hitlToolOptions.value = [];
  } finally {
    hitlToolOptionsLoaded.value = true;
  }
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

function buildMamboAgentParameters(): MamboAgentParameters | null {
  const params = {
    include_general_purpose: form.mambo_general_purpose,
    enable_planning: form.mambo_planning_enabled,
    enable_show: form.mambo_show_enabled,
    enable_memory: form.mambo_memory_enabled,
    enable_summarization: form.mambo_summary_enabled,
    memory_resource_ids: form.mambo_memory_enabled
      ? [...form.mambo_memory_resource_ids]
      : [] as string[],
    summarization_config: form.mambo_summary_enabled
      ? {
          trigger_type: form.mambo_summary_trigger_type,
          trigger_value: form.mambo_summary_trigger_value,
          keep_type: form.mambo_summary_keep_type,
          keep_value: form.mambo_summary_keep_value,
          offload_to_backend: form.mambo_summary_offload,
        }
      : null,
    security_review: form.mambo_security_review_enabled
      ? {
          enabled: true,
          model_id: form.mambo_security_review_model_id || null,
          system_prompt: form.mambo_security_review_system_prompt || null,
          review_tools: form.mambo_security_review_tools.length > 0 ? [...form.mambo_security_review_tools] : null,
        }
      : null,
    version_control: form.mambo_version_control_enabled ? {
      enabled: true,
      auto_snapshot: true,
    } : null,
    mcp_direct_tool_threshold: form.mambo_mcp_threshold,
  };
  return params;
}

async function handleSave() {
  if (!currentAgentId.value) return;
  isSaving.value = true;
  try {
    const resourcePromptList = mountedResources.value
      .filter(r => !(r as any)._deleted)
      .map(r => r.id);

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
    const finalBackendIds = (form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') ? [...form.backendIds] : [];

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
      subAgents: (form.AgentType === 'DeepAgent' || form.AgentType === 'Mambo') && form.subAgents.length > 0
        ? [...mountedSubAgents.value.filter(a => !(a as any)._deleted).map(a => a.id)]
        : [],

      backendIds: finalBackendIds,
      defaultBackendId: form.defaultBackendId,
      memoryResourceIds: form.AgentType === 'Mambo' && form.mambo_memory_enabled
        ? [...form.mambo_memory_resource_ids]
        : [],

      securityReviewConfig: form.AgentType === 'Mambo' && form.mambo_security_review_enabled
        ? {
            enabled: true,
            model_id: form.mambo_security_review_model_id || null,
            system_prompt: form.mambo_security_review_system_prompt || null,
            review_tools: form.mambo_security_review_tools.length > 0 ? [...form.mambo_security_review_tools] : null,
          }
        : null,

      // Mambo 专属参数
      agentParameters: form.AgentType === 'Mambo'
        ? buildMamboAgentParameters()
        : null,
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
.memory-type-hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
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

.mambo-fraction-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 12px 0;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
  border-radius: 4px;
  line-height: 1.4;
}

.stale-tools-warning {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  line-height: 1.5;
}

.deleted-tag {
  opacity: 0.5;
  border-style: dashed;
}
</style>

