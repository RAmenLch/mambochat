<!-- frontend/mambo/src/mobile/components/chat/ChatSettingsDrawer.vue -->
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
      <el-form v-if="chatData" :model="chatSettingsForm" label-position="top">
        <div class="form-section">
          <div class="form-section-title">基本信息</div>
          <el-form-item :label="$t('chat.settings.name')">
            <el-input
              v-model.trim="chatSettingsForm.name"
              :placeholder="$t('chat.settings.namePlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="$t('chat.settings.model')">
            <el-select
              ref="modelSelectRef"
              v-model="chatSettingsForm.aiModelId"
              :placeholder="$t('chat.settings.modelPlaceholder')"
              style="width: 100%"
              @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, modelSelectRef)"
            >
              <el-option-group
                v-for="group in filteredGroupedModels"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="item in group.options"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-option-group>
            </el-select>
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">对话设置</div>
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
              :rows="6"
              :placeholder="$t('chat.settings.systemPromptPlaceholder')"
            />
            <div v-if="mountedSystemResources.length > 0" class="mounted-resources-wrapper">
              <el-space wrap>
                <el-tag
                  v-for="resource in mountedSystemResources"
                  :key="resource.id"
                  closable
                  type="info"
                  @close="handleRemoveMountedResource(resource.id)"
                >
                  {{ resource.name }}
                </el-tag>
              </el-space>
            </div>
          </el-form-item>

          <el-form-item :label="$t('chat.settings.contextCount')">
            <el-input-number
              v-model="chatSettingsForm.modelParameters.max_context_messages"
              :min="0"
              :step="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item :label="$t('chat.settings.stream')">
            <el-switch v-model="chatSettingsForm.modelParameters.stream" />
          </el-form-item>
          <el-form-item :label="$t('chat.settings.enableSuggest')">
            <el-switch v-model="chatSettingsForm.modelParameters.enable_suggest" />
          </el-form-item>
          <el-form-item :label="$t('chat.settings.enableAskUser')">
            <el-switch v-model="chatSettingsForm.modelParameters.enable_ask_user" />
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">{{ $t('chat.settings.modelParams') }}</div>
          <el-form-item v-for="param in dynamicParameters" :key="param.key">
            <template #label>
              <div class="param-label-row">
                <span class="param-label-text">{{ param.label }}</span>
                <el-switch
                  :model-value="param.isEnabled"
                  @change="(isEnabled: string | number | boolean) => handleToggleParameter(param, isEnabled as boolean)"
                  size="small"
                />
              </div>
            </template>

            <div v-if="param.isEnabled" class="mobile-param-control">
              <el-slider
                v-if="param.type === 'number'"
                v-model="chatSettingsForm.modelParameters[param.key]"
                :min="!Array.isArray(param.limit) ? (param.limit?.min ?? 0) : 0"
                :max="!Array.isArray(param.limit) ? (param.limit?.max ?? 1) : 1"
                :step="
                  getSliderStep(
                    !Array.isArray(param.limit) ? (param.limit?.min ?? 0) : 0,
                    !Array.isArray(param.limit) ? (param.limit?.max ?? 1) : 1,
                  )
                "
                show-input
                input-size="small"
              />
              <el-input-number
                v-else-if="param.type === 'integer'"
                v-model="chatSettingsForm.modelParameters[param.key]"
                :min="!Array.isArray(param.limit) ? param.limit?.min : undefined"
                :max="!Array.isArray(param.limit) ? param.limit?.max : undefined"
                controls-position="right"
                style="width: 100%"
              />
              <el-select
                v-else-if="param.type === 'string' && Array.isArray(param.limit)"
                v-model="chatSettingsForm.modelParameters[param.key]"
                style="width: 100%"
              >
                <el-option v-for="opt in param.limit" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <el-switch
                v-else-if="param.type === 'boolean'"
                v-model="chatSettingsForm.modelParameters[param.key]"
              />
            </div>
          </el-form-item>
        </div>
      </el-form>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="emit('update:visible', false)" class="footer-btn">{{
          $t('common.action.cancel')
        }}</el-button>
        <el-button type="primary" @click="handleSaveSettings" class="footer-btn save-btn">{{
          $t('common.action.save')
        }}</el-button>
      </div>
    </template>
  </el-drawer>

  <ResourceSelectorDialog
    v-model:visible="promptDialogVisible"
    context="chat-settings"
    @mount-resources="handleMountResources"
    @mount-knowledge-base="handleMountKnowledgeBase"
  />
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSystemConfigStore } from '@/stores/systemConfigStore'
import { useProviderStore } from '@/stores/providerStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useChatListStore } from '@/stores/chatListStore'
import { getResourceDetails } from '@/api/resourceService'
import type { Chat, ChatUpdate, AIModel, Resource, LLMParameterDefinition } from '@/api/types'
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue'
import { useModelSelectScroll } from '@/composables/useModelSelectScroll'

interface GroupedModels {
  label: string
  options: AIModel[]
}

interface ChatSettingsForm {
  name: string | null
  aiModelId: string | null
  systemPrompt: string | null
  modelParameters: Record<string, any>
}

interface DynamicParameterUI {
  key: string
  label: string
  type: 'integer' | 'number' | 'string' | 'boolean'
  limit?: Array<string | number> | { min?: number; max?: number }
  isEnabled: boolean
  definition: LLMParameterDefinition
}

const props = defineProps<{
  visible: boolean
  chatData: Chat | null
  groupedModels: GroupedModels[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'save', settings: ChatUpdate): void
}>()

const { t } = useI18n()
const systemConfigStore = useSystemConfigStore()
const providerStore = useProviderStore()
const chatSessionStore = useChatSessionStore()
const chatListStore = useChatListStore()

const promptDialogVisible = ref(false)
const modelSelectRef = ref()
const { scrollToTopIfStarred } = useModelSelectScroll()
const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: {},
})
const mountedSystemResources = ref<Resource[]>([])

const handleDrawerClose = () => {
  emit('update:visible', false)
}

const filteredGroupedModels = computed(() => {
  return props.groupedModels
    .map((group) => ({
      label: group.label,
      options: group.options.filter((m) => m.model_type === 'chat'),
    }))
    .filter((group) => group.options.length > 0)
})

const dynamicParameters = computed((): DynamicParameterUI[] => {
  if (!props.chatData) return []
  const currentModel = providerStore.allModels.find((m) => m.id === chatSettingsForm.aiModelId)
  const supportedParameters = new Set(currentModel?.meta_config?.supported_parameters ?? [])
  const coreParameters = ['temperature', 'top_p']

  return systemConfigStore.llmParameters
    .filter(
      (paramDef) =>
        coreParameters.includes(paramDef.key) ||
        supportedParameters.has(paramDef.key) ||
        paramDef.default_activate,
    )
    .map((paramDef) => ({
      key: paramDef.key,
      label: paramDef.label,
      type: paramDef.type as 'integer' | 'number' | 'string' | 'boolean',
      limit: paramDef.limit,
      isEnabled: Object.prototype.hasOwnProperty.call(
        chatSettingsForm.modelParameters,
        paramDef.key,
      ),
      definition: paramDef,
    }))
})

watch(
  () => props.chatData,
  async (newVal) => {
    if (!newVal) return
    chatSettingsForm.name = newVal.name
    chatSettingsForm.aiModelId = newVal.aiModelId
    chatSettingsForm.systemPrompt = newVal.systemPrompt

    const params = newVal.modelParameters || {}
    chatSettingsForm.modelParameters = {
      ...JSON.parse(JSON.stringify(params)),
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
      enable_suggest: params.enable_suggest ?? false,
      enable_ask_user: params.enable_ask_user ?? false,
    }

    mountedSystemResources.value = []
    if (newVal.resource_prompt_list && newVal.resource_prompt_list.length > 0) {
      try {
        const promises = newVal.resource_prompt_list.map((id) => getResourceDetails(id))
        const results = await Promise.all(promises)
        mountedSystemResources.value = results.filter(
          (r) => r && (r.resourceType === 'system_prompt' || r.resourceType === 'submessage_template')
        ) as Resource[]
      } catch (e) {
        console.error(e)
      }
    }
  },
  { immediate: true, deep: true },
)

function getSliderStep(min: number, max: number): number {
  const range = max - min
  if (range <= 2) return 0.01
  if (range <= 20) return 0.1
  return 1
}

function handleToggleParameter(param: DynamicParameterUI, isEnabled: boolean) {
  const newParams = { ...chatSettingsForm.modelParameters }
  if (isEnabled) {
    newParams[param.key] = param.definition.default_value
  } else {
    delete newParams[param.key]
  }
  chatSettingsForm.modelParameters = newParams
}

function handleMountResources(resources: Resource[]) {
  resources.forEach((resource) => {
    if (!mountedSystemResources.value.some((r) => r.id === resource.id)) {
      mountedSystemResources.value.push(resource)
    }
  })
}

function handleRemoveMountedResource(resourceId: string) {
  mountedSystemResources.value = mountedSystemResources.value.filter((r) => r.id !== resourceId)
}

async function handleMountKnowledgeBase(resources: Resource[]) {
  if (!props.chatData) return
  const currentList = props.chatData.resource_prompt_list || []
  const newIds = resources.map(r => r.id).filter(id => !currentList.includes(id))

  if (newIds.length > 0) {
    const updatedList = [...currentList, ...newIds]
    await chatListStore.updateChatSettings(props.chatData.id, {
      resource_prompt_list: updatedList
    })
    ElMessage.success(`已启用知识库: ${resources.map(r => r.name).join(', ')}`)
  }
}

function handleSaveSettings() {
  if (!props.chatData) return
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning(t('chat.settings.namePlaceholder'))
    return
  }

  const finalModelParameters: Record<string, any> = {
    max_context_messages: chatSettingsForm.modelParameters.max_context_messages,
    stream: chatSettingsForm.modelParameters.stream,
    enable_suggest: chatSettingsForm.modelParameters.enable_suggest,
    enable_ask_user: chatSettingsForm.modelParameters.enable_ask_user,
  }

  for (const key in chatSettingsForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, key)) {
      if (['max_context_messages', 'stream'].includes(key)) continue
      finalModelParameters[key] = chatSettingsForm.modelParameters[key]
    }
  }

  const drawerResourceIds = mountedSystemResources.value.map((r) => r.id)
  const currentKbIds = chatSessionStore.systemPromptResources
    .filter(r => r.resourceType === 'knowledge_base')
    .map(r => r.id)

  const resourcePromptList = [...drawerResourceIds, ...currentKbIds]

  emit('save', {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: finalModelParameters,
    resource_prompt_list: resourcePromptList.length > 0 ? resourcePromptList : null,
  })
}
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
  padding: 0 10px 28px 10px;
}

.form-section {
  background: var(--color-background-soft);
  border-radius: 14px;
  padding: 16px 16px 4px 16px;
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.form-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  gap: 6px;
}

.form-section-title::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--el-color-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

.drawer-content :deep(.el-form-item__label) {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.drawer-content :deep(.el-input__wrapper),
.drawer-content :deep(.el-select .el-input__wrapper),
.drawer-content :deep(.el-input-number .el-input__wrapper) {
  border-radius: 10px;
  background-color: var(--el-bg-color);
  box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;
}

.drawer-content :deep(.el-textarea__inner) {
  border-radius: 12px;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  font-size: 14px;
  line-height: 1.6;
  padding: 14px;
}

.drawer-content :deep(.el-divider__text) {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
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

.param-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 12px;
}

.param-label-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.form-item-label-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.mounted-resources-wrapper {
  margin-top: 10px;
  background-color: var(--el-bg-color);
  padding: 10px 12px;
  border-radius: 10px;
  box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;
}

.mounted-resources-wrapper :deep(.el-tag) {
  border-radius: 8px;
  font-weight: 500;
}

.mobile-param-control {
  width: 100%;
  margin-top: 8px;
}

.mobile-param-control :deep(.el-slider .el-input-number) {
  width: 80px;
}

.mobile-param-control :deep(.el-slider__runway) {
  margin-right: 12px;
  height: 6px;
  border-radius: 3px;
}

.mobile-param-control :deep(.el-slider__bar) {
  height: 6px;
  border-radius: 3px;
}

.mobile-param-control :deep(.el-slider__button) {
  width: 20px;
  height: 20px;
}

.mobile-param-control > .el-input-number {
  width: 100%;
}

.drawer-content :deep(.el-switch) {
  --el-switch-on-color: var(--el-color-primary);
}

.drawer-content :deep(.el-input-number) {
  width: 100%;
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
.rs-overlay {
  z-index: 2100 !important;
}
</style>
