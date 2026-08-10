<!-- frontend/mambo/src/components/settings/GlobalSettings.vue -->
<template>
  <div class="global-settings-manager">
    <div class="header">
      <h2>{{ t('settings.global.title') }}</h2>
      <!-- 顶部也可以显示保存状态，可选 -->
    </div>
    <div class="settings-form-container">
      <el-form :model="settingsForm" label-position="top" style="max-width: 600px">
        <!-- 语言设置 -->
        <el-form-item :label="t('settings.global.language')">
          <el-select v-model="settingsForm.language" style="width: 100%">
            <el-option label="简体中文" value="zh-CN" />
            <el-option label="English" value="en" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>{{ t('settings.global.defaultModel') }}</span>
            <el-tooltip
              effect="dark"
              :content="t('settings.global.defaultModelTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select
            ref="defaultModelSelectRef"
            v-model="settingsForm.default_model_id"
            :placeholder="t('settings.global.defaultModelPlaceholder')"
            style="width: 100%"
            clearable
            @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, defaultModelSelectRef)"
          >
            <el-option-group v-for="group in groupedModels" :key="group.label" :label="group.label">
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
            <span>{{ t('settings.global.titleModel') }}</span>
            <el-tooltip
              effect="dark"
              :content="t('settings.global.titleModelTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select
            ref="titleModelSelectRef"
            v-model="settingsForm.title_generation_model_id"
            :placeholder="t('settings.global.titleModelPlaceholder')"
            style="width: 100%"
            clearable
            @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, titleModelSelectRef)"
          >
            <el-option-group v-for="group in groupedModels" :key="group.label" :label="group.label">
              <el-option
                v-for="item in group.options"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </el-option-group>
          </el-select>
        </el-form-item>

        <el-divider>{{ t('settings.global.editorInteraction') }}</el-divider>
        <el-form-item :label="t('settings.global.frontendEditor')">
          <el-radio-group v-model="settingsForm.frontend_editor">
            <el-radio-button label="simple">{{ t('settings.global.editorSimple') }}</el-radio-button>
            <el-radio-button label="monaco">{{ t('settings.global.editorMonaco') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>{{ t('settings.global.messageDisplay') }}</span>
            <el-tooltip
              effect="dark"
              :content="t('settings.global.messageDisplayTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-radio-group v-model="settingsForm.message_display_mode">
            <el-radio-button label="stacked">{{ t('settings.global.messageDisplayStacked') }}</el-radio-button>
            <el-radio-button label="interleaved">{{ t('settings.global.messageDisplayInterleaved') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item :label="t('settings.global.sendShortcut')">
          <el-select v-model="settingsForm.send_message_shortcut" style="width: 100%">
            <el-option :label="t('settings.global.shortcutEnter')" value="enter" />
            <el-option :label="t('settings.global.shortcutCtrlEnter')" value="ctrl_enter" />
          </el-select>
        </el-form-item>

        <el-divider>{{ t('settings.global.kbParams') }}</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item>
              <template #label>
                <span>{{ t('settings.global.kbChunkSize') }}</span>
                <el-tooltip :content="t('settings.global.kbChunkSizeTip')" placement="top">
                  <el-icon class="label-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number
                v-model="settingsForm.kb_default_chunk_size"
                :min="100"
                :step="100"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item>
              <template #label>
                <span>{{ t('settings.global.kbChunkOverlap') }}</span>
                <el-tooltip :content="t('settings.global.kbChunkOverlapTip')" placement="top">
                  <el-icon class="label-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number
                v-model="settingsForm.kb_default_chunk_overlap"
                :min="0"
                :step="10"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider>{{ t('settings.global.avatarSettings') }}</el-divider>
        <div class="avatar-settings-section">
          <AvatarUploader
            :title="t('settings.avatar.userTitle')"
            :avatar-url="globalSettings.user_avatar_url"
            :icon="User"
            :is-loading="isAvatarLoading.user"
            @upload="(file) => handleUploadAvatar('user', file)"
            @delete="() => handleDeleteAvatar('user')"
          />
          <AvatarUploader
            :title="t('settings.avatar.aiTitle')"
            :avatar-url="globalSettings.ai_avatar_url"
            :icon="Cpu"
            :is-loading="isAvatarLoading.ai"
            @upload="(file) => handleUploadAvatar('ai', file)"
            @delete="() => handleDeleteAvatar('ai')"
          />
        </div>

        <el-divider>{{ t('settings.global.proxyConfig') }}</el-divider>
        <el-form-item :label="t('settings.global.enableProxy')">
          <el-switch
            :model-value="settingsForm.proxy_enabled ?? false"
            @update:model-value="(val: string | number | boolean) => (settingsForm.proxy_enabled = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.enableProxyTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item :label="t('settings.global.proxyUrl')" v-if="settingsForm.proxy_enabled">
          <el-input
            v-model.trim="settingsForm.proxy_url"
            :placeholder="t('settings.global.proxyUrlPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('settings.global.proxyTest')" v-if="settingsForm.proxy_enabled">
          <div class="proxy-test-container">
            <el-input
              v-model.trim="proxyTestUrl"
              :placeholder="t('settings.global.testUrlPlaceholder')"
              class="proxy-test-input"
            />
            <el-button @click="handleTestProxy" :loading="isTestingProxy">
              {{ t('settings.global.testProxyBtn') }}
            </el-button>
          </div>
        </el-form-item>

        <el-divider>{{ t('settings.global.webSearchConfig') }}</el-divider>
        <el-form-item :label="t('settings.global.webSearchDefaultMode')">
          <el-radio-group v-model="settingsForm.web_search_default_mode">
            <el-radio value="disable">{{ t('settings.global.webSearchModeDisabled') }}</el-radio>
            <el-radio value="direct_read">{{ t('settings.global.webSearchModeDirectRead') }}</el-radio>
            <el-radio value="search_and_read">{{ t('settings.global.webSearchModeSearchAndRead') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('settings.global.webSearchUseProxy')">
          <el-switch
            :model-value="settingsForm.web_search_use_proxy ?? false"
            @update:model-value="(val: string | number | boolean) => (settingsForm.web_search_use_proxy = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.webSearchUseProxyTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-divider>{{ t('settings.global.historyCompression') }}</el-divider>
        <el-form-item>
          <template #label>
            <span>{{ t('settings.global.compressionPrompt') }}</span>
            <el-tooltip
              effect="dark"
              :content="t('settings.global.compressionPromptTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="settingsForm.zip_history_system_prompt"
            type="textarea"
            :rows="5"
            :placeholder="t('settings.global.compressionPromptPlaceholder')"
          />
        </el-form-item>

        <el-divider>{{ t('settings.global.newChatParams') }}</el-divider>

        <el-form-item>
          <template #label>
            <span>{{ t('settings.global.contextMsgCount') }}</span>
            <el-tooltip
              effect="dark"
              :content="t('settings.global.contextMsgCountTip')"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="settingsForm.default_max_context_messages"
            :min="0"
            :step="2"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item :label="t('settings.global.temperature')">
          <el-slider
            :model-value="settingsForm.default_temperature ?? 1.0"
            @update:model-value="(val: number | number[]) => (settingsForm.default_temperature = (Array.isArray(val) ? val[0] : val))"
            :min="0"
            :max="2"
            :step="0.1"
            show-input
          />
        </el-form-item>

        <el-form-item :label="t('settings.global.topP')">
          <el-slider
            :model-value="settingsForm.default_top_p ?? 1.0"
            @update:model-value="(val: number | number[]) => (settingsForm.default_top_p = (Array.isArray(val) ? val[0] : val))"
            :min="0"
            :max="1"
            :step="0.01"
            show-input
          />
        </el-form-item>

        <el-form-item :label="t('settings.global.stream')">
          <el-switch
            :model-value="settingsForm.default_stream ?? true"
            @update:model-value="(val: string | number | boolean) => (settingsForm.default_stream = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.streamTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-form-item :label="t('settings.global.defaultEnableSuggest')">
          <el-switch
            :model-value="settingsForm.default_enable_suggest ?? false"
            @update:model-value="(val: string | number | boolean) => (settingsForm.default_enable_suggest = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.defaultEnableSuggestTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-form-item :label="t('settings.global.defaultEnableAskUser')">
          <el-switch
            :model-value="settingsForm.default_enable_ask_user ?? false"
            @update:model-value="(val: string | number | boolean) => (settingsForm.default_enable_ask_user = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.defaultEnableAskUserTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-form-item :label="t('settings.global.defaultMaxRetries')">
          <el-input-number
            :model-value="settingsForm.default_max_retries ?? 1"
            @update:model-value="(val: number | undefined) => (settingsForm.default_max_retries = val ?? 1)"
            :min="1"
            :max="20"
            :step="1"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.defaultMaxRetriesTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-form-item :label="t('settings.global.defaultTimeout')">
          <el-input-number
            :model-value="settingsForm.default_timeout ?? 60"
            @update:model-value="(val: number | undefined) => (settingsForm.default_timeout = val ?? 60)"
            :min="10"
            :max="600"
            :step="10"
          />
          <el-tooltip
            effect="dark"
            :content="t('settings.global.defaultTimeoutTip')"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <!-- 状态栏替代了保存按钮 -->
        <div class="status-bar">
          <transition name="fade" mode="out-in">
            <div v-if="saveStatus === 'saving'" class="status-item saving">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ t('settings.global.saving') }}</span>
            </div>
            <div v-else-if="saveStatus === 'saved'" class="status-item saved">
              <el-icon><Check /></el-icon>
              <span>{{ t('settings.global.saved') }}</span>
            </div>
            <div v-else-if="saveStatus === 'error'" class="status-item error">
              <el-icon><Warning /></el-icon>
              <span>{{ t('settings.global.saveError') }}</span>
            </div>
          </transition>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProviderStore } from '@/stores/providerStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { QuestionFilled, User, Cpu, Loading, Check, Warning } from '@element-plus/icons-vue'
import type { GlobalSettingsUpdate } from '@/api/types'
import AvatarUploader from './AvatarUploader.vue'
import { useModelSelectScroll } from '@/composables/useModelSelectScroll'

type AvatarType = 'user' | 'ai'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const { t, locale } = useI18n()
const providerStore = useProviderStore()
const settingsStore = useSettingsStore()

const { groupedModels } = storeToRefs(providerStore)
const { globalSettings } = storeToRefs(settingsStore)

// 表单数据
// 显式重写 frontend_editor / message_display_mode / web_search_default_mode 类型为 string，以解决 el-radio-group 不接受 null 的问题
const settingsForm = reactive<
  Omit<
    GlobalSettingsUpdate,
    'user_avatar_url' | 'ai_avatar_url' | 'frontend_editor' | 'message_display_mode' | 'web_search_default_mode'
  > & {
    frontend_editor: string
    message_display_mode: string
    web_search_default_mode: string
  }
>({
  default_model_id: null,
  title_generation_model_id: null,
  last_selected_provider_id: null,
  default_max_context_messages: 0,
  default_temperature: 1.0,
  default_top_p: 1.0,
  default_stream: true,
  proxy_enabled: false,
  proxy_url: null,
  web_search_default_mode: 'disable',
  web_search_use_proxy: false,
  zip_history_system_prompt: null,
  frontend_editor: 'simple',
  message_display_mode: 'interleaved',
  kb_default_chunk_size: 500,
  kb_default_chunk_overlap: 50,
  send_message_shortcut: 'enter',
  language: 'zh-CN', // 默认值
  default_enable_suggest: false,
  default_enable_ask_user: false,
  default_max_retries: 1,
  default_timeout: 60,
})

// 状态控制
const saveStatus = ref<SaveStatus>('idle')
const isTestingProxy = ref(false)
const proxyTestUrl = ref('https://www.google.com')
const isAvatarLoading = reactive({
  user: false,
  ai: false,
})

const defaultModelSelectRef = ref()
const titleModelSelectRef = ref()
const { scrollToTopIfStarred } = useModelSelectScroll()

// 同步锁：防止 Store -> Form -> Watch -> API -> Store 的死循环
const isSyncingFromStore = ref(false)

// 简单的防抖函数实现 (避免引入 lodash)
function debounce<T extends (...args: any[]) => any>(fn: T, delay: number) {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      fn(...args)
    }, delay)
  }
}

onMounted(async () => {
  await settingsStore.fetchGlobalSettings()
})

// 1. 监听 Store 变化，同步到 Form
watch(
  globalSettings,
  (newSettings) => {
    // 开启同步锁
    isSyncingFromStore.value = true

    Object.assign(settingsForm, {
      default_model_id: newSettings.default_model_id,
      title_generation_model_id: newSettings.title_generation_model_id,
      last_selected_provider_id: newSettings.last_selected_provider_id,
      default_max_context_messages: newSettings.default_max_context_messages,
      default_temperature: newSettings.default_temperature,
      default_top_p: newSettings.default_top_p,
      default_stream: newSettings.default_stream,
      proxy_enabled: newSettings.proxy_enabled,
      proxy_url: newSettings.proxy_url,
      web_search_default_mode: newSettings.web_search_default_mode ?? 'disable',
      web_search_use_proxy: newSettings.web_search_use_proxy ?? false,
      zip_history_system_prompt: newSettings.zip_history_system_prompt,
      // 确保赋值给 frontend_editor 的值不为 null
      frontend_editor: newSettings.frontend_editor ?? 'simple',
      message_display_mode: newSettings.message_display_mode ?? 'interleaved',
      kb_default_chunk_size: newSettings.kb_default_chunk_size,
      kb_default_chunk_overlap: newSettings.kb_default_chunk_overlap,
      send_message_shortcut: newSettings.send_message_shortcut,
      language: newSettings.language || 'zh-CN',
      default_enable_suggest: newSettings.default_enable_suggest ?? false,
      default_enable_ask_user: newSettings.default_enable_ask_user ?? false,
      default_max_retries: newSettings.default_max_retries ?? 1,
      default_timeout: newSettings.default_timeout ?? 60,
    })

    // 在 DOM 更新循环结束后释放锁，确保 watch(settingsForm) 不会被此次赋值触发
    nextTick(() => {
      isSyncingFromStore.value = false
    })

    // 同步语言设置到 i18n 实例
    if (newSettings.language && (newSettings.language === 'zh-CN' || newSettings.language === 'en')) {
      locale.value = newSettings.language
    }
  },
  { deep: true, immediate: true },
)

// 执行保存的逻辑
const performSave = async () => {
  saveStatus.value = 'saving'
  try {
    const settingsToSave: GlobalSettingsUpdate = {
      ...settingsForm,
      user_avatar_url: null, // 头像由单独接口处理
      ai_avatar_url: null,
    }
    await settingsStore.saveGlobalSettings(settingsToSave)
    saveStatus.value = 'saved'

    // 2秒后恢复空闲状态，或者保持 Saved 状态直到下次修改
    setTimeout(() => {
      if (saveStatus.value === 'saved') {
        // 可选：保持显示 "Saved" 或淡出
      }
    }, 2000)
  } catch (error: unknown) {
    console.error('Failed to save global settings:', error)
    saveStatus.value = 'error'
  }
}

// 创建防抖版本的保存函数 (1000ms 延迟，避免频繁请求)
const debouncedSave = debounce(performSave, 1000)

// 2. 监听 Form 变化，触发自动保存
watch(
  settingsForm,
  () => {
    // 如果正在从 Store 同步数据，则忽略此次变更
    if (isSyncingFromStore.value) return

    // 状态变更为正在输入/等待保存
    if (saveStatus.value !== 'saving') {
      saveStatus.value = 'saving' // 立即给予用户反馈
    }

    debouncedSave()
  },
  { deep: true },
)

const handleUploadAvatar = async (type: AvatarType, file: File) => {
  isAvatarLoading[type] = true
  try {
    await settingsStore.uploadAvatar(type, file)
    ElMessage.success(t('settings.global.avatarUploadSuccess'))
  } catch (error: unknown) {
    console.error(`Failed to upload ${type} avatar:`, error)
  } finally {
    isAvatarLoading[type] = false
  }
}

const handleDeleteAvatar = async (type: AvatarType) => {
  isAvatarLoading[type] = true
  try {
    await settingsStore.deleteAvatar(type)
    ElMessage.success(t('settings.global.avatarDeleteSuccess'))
  } catch (error: unknown) {
    console.error(`Failed to delete ${type} avatar:`, error)
  } finally {
    isAvatarLoading[type] = false
  }
}

const handleTestProxy = async () => {
  if (!settingsForm.proxy_url) {
    ElMessage.warning(t('settings.global.enterProxyUrl'))
    return
  }
  if (!proxyTestUrl.value) {
    ElMessage.warning(t('settings.global.enterTestUrl'))
    return
  }

  isTestingProxy.value = true
  try {
    const response = await settingsStore.testProxy({
      proxy_url: settingsForm.proxy_url,
      test_url: proxyTestUrl.value,
    })
    ElMessage({
      type: response.status === 'success' ? 'success' : 'error',
      message: response.message,
    })
  } catch (error: unknown) {
    console.error('Failed to test proxy:', error)
  } finally {
    isTestingProxy.value = false
  }
}
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.header h2 {
  margin: 0;
  font-size: 20px;
}
.settings-form-container {
  padding: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  position: relative; /* 为状态栏定位做准备 */
}
.label-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
}
.el-form-item .el-switch {
  margin-right: 8px;
}
.proxy-test-container {
  display: flex;
  width: 100%;
}
.proxy-test-input {
  margin-right: 10px;
}
.avatar-settings-section {
  display: flex;
  justify-content: flex-start;
  gap: 20px;
  margin-bottom: 22px;
}

/* 状态栏样式 */
.status-bar {
  margin-top: 20px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.status-item.saving {
  color: var(--el-text-color-secondary);
}

.status-item.saved {
  color: var(--el-color-success);
}

.status-item.error {
  color: var(--el-color-danger);
}

/* 简单的淡入淡出动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
