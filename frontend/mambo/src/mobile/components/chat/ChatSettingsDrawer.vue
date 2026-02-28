<!-- frontend/mambo/src/mobile/components/chat/ChatSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    :title="$t('chat.settings.title')"
    direction="rtl"
    size="100%"
    :before-close="handleDrawerClose"
    class="mobile-settings-drawer"
  >
    <div class="drawer-content">
      <el-form v-if="chatData" :model="chatSettingsForm" label-position="top">
        <el-form-item :label="$t('chat.settings.name')">
          <el-input
            v-model.trim="chatSettingsForm.name"
            :placeholder="$t('chat.settings.namePlaceholder')"
          />
        </el-form-item>

        <el-form-item :label="$t('chat.settings.model')">
          <el-select
            v-model="chatSettingsForm.aiModelId"
            :placeholder="$t('chat.settings.modelPlaceholder')"
            style="width: 100%"
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
          <!-- 挂载资源预览区（仅展示，不支持拖拽） -->
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

        <el-divider>{{ $t('chat.settings.modelParams') }}</el-divider>

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

        <!-- 动态参数列表 -->
        <el-form-item v-for="param in dynamicParameters" :key="param.key">
          <template #label>
            <div class="param-label-row">
              <span class="param-label-text">{{ param.label }}</span>
              <el-switch
                :model-value="param.isEnabled"
                @change="(isEnabled) => handleToggleParameter(param, isEnabled as boolean)"
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
      </el-form>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="emit('update:visible', false)" class="footer-btn">{{
          $t('common.action.cancel')
        }}</el-button>
        <el-button type="primary" @click="handleSaveSettings" class="footer-btn">{{
          $t('common.action.save')
        }}</el-button>
      </div>
    </template>
  </el-drawer>

  <!-- 引用移动端的资源选择器 -->
  <ResourceSelectorDialog
    v-model:visible="promptDialogVisible"
    source="settings"
    @mount-resources="handleMountResources"
  />
</template>

<script setup lang="ts">
import { reactive, watch, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useSystemConfigStore } from '@/stores/systemConfigStore'
import { useProviderStore } from '@/stores/providerStore'
import { getResourceDetails } from '@/api/resourceService'
import type { Chat, ChatUpdate, AIModel, Resource, LLMParameterDefinition } from '@/api/types'
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue'

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

const promptDialogVisible = ref(false)
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

    // Copy params
    const params = newVal.modelParameters || {}
    chatSettingsForm.modelParameters = {
      ...JSON.parse(JSON.stringify(params)),
      max_context_messages: params.max_context_messages ?? 0,
      stream: params.stream ?? true,
      enable_suggest: params.enable_suggest ?? false,
    }

    mountedSystemResources.value = []
    if (newVal.resource_prompt_list && newVal.resource_prompt_list.length > 0) {
      try {
        const promises = newVal.resource_prompt_list.map((id) => getResourceDetails(id))
        mountedSystemResources.value = (await Promise.all(promises)).filter(
          (r) => !!r,
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
  }

  for (const key in chatSettingsForm.modelParameters) {
    if (Object.prototype.hasOwnProperty.call(chatSettingsForm.modelParameters, key)) {
      if (['max_context_messages', 'stream'].includes(key)) continue
      finalModelParameters[key] = chatSettingsForm.modelParameters[key]
    }
  }

  const resourcePromptList = mountedSystemResources.value.map((r) => r.id)

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
.drawer-content {
  padding: 0 10px 40px 10px;
}

.drawer-footer {
  display: flex;
  gap: 15px;
  padding-bottom: env(safe-area-inset-bottom);
}

.footer-btn {
  flex: 1;
}

.param-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 12px; /* 1. 修复：增加文本与开关的间距 */
}

.param-label-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-item-label-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.mounted-resources-wrapper {
  margin-top: 8px;
  background-color: var(--color-background-soft);
  padding: 8px;
  border-radius: 4px;
}

/* 2 & 3. 修复：控件容器样式 */
.mobile-param-control {
  width: 100%; /* 确保容器占满宽度，解决下拉框过短问题 */
  margin-top: 8px;
}

/* 2. 修复：滑块样式调整 */
/* 强制将滑块内部的输入框宽度缩小，防止挤压滑动条 */
.mobile-param-control :deep(.el-slider .el-input-number) {
  width: 80px;
}

.mobile-param-control :deep(.el-slider__runway) {
  margin-right: 12px;
}

/* 确保整数输入框不受影响（如果需要全宽） */
.mobile-param-control > .el-input-number {
  width: 100%;
}
</style>
