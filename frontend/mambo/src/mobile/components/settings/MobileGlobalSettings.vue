<!-- MobileGlobalSettings.vue — 移动端全局设置 -->
<template>
  <div class="mobile-global-settings">
    <div class="settings-body">
      <!-- 语言 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.language') }}</div>
        <el-select v-model="settingsForm.language" style="width: 100%" popper-class="mobile-popper">
          <el-option label="简体中文" value="zh-CN" />
          <el-option label="English" value="en" />
        </el-select>
      </div>

      <!-- 模型设置 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.defaultModel') }}</div>
        <el-select
          ref="defaultModelSelectRef"
          v-model="settingsForm.default_model_id"
          :placeholder="t('settings.global.defaultModelPlaceholder')"
          style="width: 100%" clearable popper-class="mobile-popper"
          @visible-change="(v: boolean) => scrollToTopIfStarred(v, defaultModelSelectRef)"
        >
          <el-option-group v-for="g in groupedModels" :key="g.label" :label="g.label">
            <el-option v-for="m in g.options" :key="m.id" :label="m.name" :value="m.id" />
          </el-option-group>
        </el-select>

        <div class="field-item" style="margin-top: 12px;">
          <label class="field-label">{{ t('settings.global.titleModel') }}</label>
          <el-select
            ref="titleModelSelectRef"
            v-model="settingsForm.title_generation_model_id"
            :placeholder="t('settings.global.titleModelPlaceholder')"
            style="width: 100%" clearable popper-class="mobile-popper"
            @visible-change="(v: boolean) => scrollToTopIfStarred(v, titleModelSelectRef)"
          >
            <el-option-group v-for="g in groupedModels" :key="g.label" :label="g.label">
              <el-option v-for="m in g.options" :key="m.id" :label="m.name" :value="m.id" />
            </el-option-group>
          </el-select>
        </div>
      </div>

      <!-- 编辑器与交互 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.editorInteraction') }}</div>

        <div class="field-item">
          <label class="field-label">{{ t('settings.global.frontendEditor') }}</label>
          <el-radio-group v-model="settingsForm.frontend_editor" size="small">
            <el-radio-button value="simple">{{ t('settings.global.editorSimple') }}</el-radio-button>
            <el-radio-button value="monaco">{{ t('settings.global.editorMonaco') }}</el-radio-button>
          </el-radio-group>
        </div>

        <div class="field-item">
          <label class="field-label">{{ t('settings.global.messageDisplay') }}</label>
          <el-radio-group v-model="settingsForm.message_display_mode" size="small">
            <el-radio-button value="stacked">{{ t('settings.global.messageDisplayStacked') }}</el-radio-button>
            <el-radio-button value="interleaved">{{ t('settings.global.messageDisplayInterleaved') }}</el-radio-button>
          </el-radio-group>
        </div>

        <div class="field-item">
          <label class="field-label">{{ t('settings.global.sendShortcut') }}</label>
          <el-select v-model="settingsForm.send_message_shortcut" style="width: 100%" popper-class="mobile-popper">
            <el-option :label="t('settings.global.shortcutEnter')" value="enter" />
            <el-option :label="t('settings.global.shortcutCtrlEnter')" value="ctrl_enter" />
          </el-select>
        </div>
      </div>

      <!-- 知识库 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.kbParams') }}</div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.kbChunkSize') }}</label>
          <el-input-number v-model="settingsForm.kb_default_chunk_size" :min="100" :step="100" controls-position="right" style="width:100%" />
        </div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.kbChunkOverlap') }}</label>
          <el-input-number v-model="settingsForm.kb_default_chunk_overlap" :min="0" :step="10" controls-position="right" style="width:100%" />
        </div>
      </div>

      <!-- 头像 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.avatarSettings') }}</div>
        <div class="avatar-row">
          <AvatarUploader
            :title="t('settings.avatar.userTitle')"
            :avatar-url="globalSettings.user_avatar_url"
            :icon="User"
            :is-loading="isAvatarLoading.user"
            @upload="(f: File) => handleUploadAvatar('user', f)"
            @delete="() => handleDeleteAvatar('user')"
          />
          <AvatarUploader
            :title="t('settings.avatar.aiTitle')"
            :avatar-url="globalSettings.ai_avatar_url"
            :icon="Cpu"
            :is-loading="isAvatarLoading.ai"
            @upload="(f: File) => handleUploadAvatar('ai', f)"
            @delete="() => handleDeleteAvatar('ai')"
          />
        </div>
      </div>

      <!-- 代理 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.proxyConfig') }}</div>
        <div class="field-row">
          <span class="field-label" style="margin-bottom:0">{{ t('settings.global.enableProxy') }}</span>
          <el-switch :model-value="settingsForm.proxy_enabled ?? false" @update:model-value="(v: string | number | boolean) => (settingsForm.proxy_enabled = v as boolean)" size="small" />
        </div>
        <template v-if="settingsForm.proxy_enabled">
          <div class="field-item" style="margin-top:8px">
            <label class="field-label">{{ t('settings.global.proxyUrl') }}</label>
            <input v-model.trim="settingsForm.proxy_url" class="native-input" :placeholder="t('settings.global.proxyUrlPlaceholder')" />
          </div>
          <div class="field-item">
            <label class="field-label">{{ t('settings.global.proxyTest') }}</label>
            <div class="proxy-row">
              <input v-model.trim="proxyTestUrl" class="native-input" style="flex:1" :placeholder="t('settings.global.testUrlPlaceholder')" />
              <button class="proxy-test-btn" @click="handleTestProxy" :disabled="isTestingProxy">{{ t('settings.global.testProxyBtn') }}</button>
            </div>
          </div>
        </template>
      </div>

      <!-- 网页搜索 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.webSearchConfig') }}</div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.webSearchDefaultMode') }}</label>
          <el-radio-group v-model="settingsForm.web_search_default_mode" size="small">
            <el-radio value="disable">{{ t('settings.global.webSearchModeDisabled') }}</el-radio>
            <el-radio value="direct_read">{{ t('settings.global.webSearchModeDirectRead') }}</el-radio>
            <el-radio value="search_and_read">{{ t('settings.global.webSearchModeSearchAndRead') }}</el-radio>
          </el-radio-group>
        </div>
        <div class="field-row">
          <span class="field-label" style="margin-bottom:0">{{ t('settings.global.webSearchUseProxy') }}</span>
          <el-switch :model-value="settingsForm.web_search_use_proxy ?? false" @update:model-value="(v: string | number | boolean) => (settingsForm.web_search_use_proxy = v as boolean)" size="small" />
        </div>
      </div>

      <!-- 历史压缩 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.historyCompression') }}</div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.compressionPrompt') }}</label>
          <textarea v-model="settingsForm.zip_history_system_prompt" class="native-textarea" :rows="4" :placeholder="t('settings.global.compressionPromptPlaceholder')"></textarea>
        </div>
      </div>

      <!-- 新对话默认参数 -->
      <div class="section-card">
        <div class="section-title">{{ t('settings.global.newChatParams') }}</div>

        <div class="field-item">
          <label class="field-label">{{ t('settings.global.contextMsgCount') }}</label>
          <el-input-number v-model="settingsForm.default_max_context_messages" :min="0" :step="2" controls-position="right" style="width:100%" />
        </div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.temperature') }}</label>
          <el-input-number v-model="settingsForm.default_temperature" :min="0" :max="2" :step="0.1" :precision="1" controls-position="right" style="width:100%" />
        </div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.topP') }}</label>
          <el-input-number v-model="settingsForm.default_top_p" :min="0" :max="1" :step="0.01" :precision="2" controls-position="right" style="width:100%" />
        </div>
        <div class="field-row">
          <span class="field-label" style="margin-bottom:0">{{ t('settings.global.stream') }}</span>
          <el-switch :model-value="settingsForm.default_stream ?? true" @update:model-value="(v: string | number | boolean) => (settingsForm.default_stream = v as boolean)" size="small" />
        </div>
        <div class="field-row">
          <span class="field-label" style="margin-bottom:0">{{ t('settings.global.defaultEnableSuggest') }}</span>
          <el-switch :model-value="settingsForm.default_enable_suggest ?? false" @update:model-value="(v: string | number | boolean) => (settingsForm.default_enable_suggest = v as boolean)" size="small" />
        </div>
        <div class="field-row">
          <span class="field-label" style="margin-bottom:0">{{ t('settings.global.defaultEnableAskUser') }}</span>
          <el-switch :model-value="settingsForm.default_enable_ask_user ?? false" @update:model-value="(v: string | number | boolean) => (settingsForm.default_enable_ask_user = v as boolean)" size="small" />
        </div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.defaultMaxRetries') }}</label>
          <el-input-number v-model="settingsForm.default_max_retries" :min="1" :max="20" :step="1" controls-position="right" style="width:100%" />
        </div>
        <div class="field-item">
          <label class="field-label">{{ t('settings.global.defaultTimeout') }}</label>
          <el-input-number v-model="settingsForm.default_timeout" :min="10" :max="600" :step="10" controls-position="right" style="width:100%" />
        </div>
      </div>

      <div class="body-spacer"></div>
    </div>

    <!-- 保存状态栏 -->
    <div class="save-bar">
      <transition name="fade" mode="out-in">
        <div v-if="saveStatus === 'saving'" class="status-item saving">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ t('settings.global.saving') }}</span>
        </div>
        <div v-else-if="saveStatus === 'saved'" class="status-item saved">
          <el-icon><Select /></el-icon>
          <span>{{ t('settings.global.saved') }}</span>
        </div>
        <div v-else-if="saveStatus === 'error'" class="status-item error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ t('settings.global.saveError') }}</span>
        </div>
        <div v-else class="status-item idle">
          <span>{{ t('settings.global.autoSave') }}</span>
        </div>
      </transition>
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
import { User, Cpu, Loading, Select, WarningFilled } from '@element-plus/icons-vue'
import type { GlobalSettingsUpdate } from '@/api/types'
import AvatarUploader from '@/components/settings/AvatarUploader.vue'
import { useModelSelectScroll } from '@/composables/useModelSelectScroll'

type AvatarType = 'user' | 'ai'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const { t, locale } = useI18n()
const providerStore = useProviderStore()
const settingsStore = useSettingsStore()
const { groupedModels } = storeToRefs(providerStore)
const { globalSettings } = storeToRefs(settingsStore)

const settingsForm = reactive<Omit<GlobalSettingsUpdate, 'user_avatar_url' | 'ai_avatar_url' | 'frontend_editor' | 'message_display_mode' | 'web_search_default_mode'> & { frontend_editor: string; message_display_mode: string; web_search_default_mode: string }>({
  default_model_id: null, title_generation_model_id: null, last_selected_provider_id: null,
  default_max_context_messages: 0, default_temperature: 1.0, default_top_p: 1.0,
  default_stream: true, proxy_enabled: false, proxy_url: null,
  web_search_default_mode: 'disable', web_search_use_proxy: false,
  zip_history_system_prompt: null,
  frontend_editor: 'simple', message_display_mode: 'interleaved',
  kb_default_chunk_size: 500, kb_default_chunk_overlap: 50, send_message_shortcut: 'enter',
  language: 'zh-CN', default_enable_suggest: false, default_enable_ask_user: false,
  default_max_retries: 1, default_timeout: 60,
})

const saveStatus = ref<SaveStatus>('idle')
const isTestingProxy = ref(false)
const proxyTestUrl = ref('https://www.google.com')
const isAvatarLoading = reactive({ user: false, ai: false })
const defaultModelSelectRef = ref()
const titleModelSelectRef = ref()
const { scrollToTopIfStarred } = useModelSelectScroll()
const isSyncingFromStore = ref(false)

function debounce<T extends (...args: any[]) => any>(fn: T, delay: number) {
  let t: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => { if (t) clearTimeout(t); t = setTimeout(() => fn(...args), delay) }
}

onMounted(async () => { await settingsStore.fetchGlobalSettings() })

watch(globalSettings, (s) => {
  isSyncingFromStore.value = true
  Object.assign(settingsForm, {
    default_model_id: s.default_model_id, title_generation_model_id: s.title_generation_model_id,
    last_selected_provider_id: s.last_selected_provider_id,
    default_max_context_messages: s.default_max_context_messages,
    default_temperature: s.default_temperature, default_top_p: s.default_top_p,
    default_stream: s.default_stream, proxy_enabled: s.proxy_enabled, proxy_url: s.proxy_url,
    web_search_default_mode: s.web_search_default_mode ?? 'disable', web_search_use_proxy: s.web_search_use_proxy ?? false,
    zip_history_system_prompt: s.zip_history_system_prompt,
    frontend_editor: s.frontend_editor ?? 'simple', message_display_mode: s.message_display_mode ?? 'interleaved',
    kb_default_chunk_size: s.kb_default_chunk_size, kb_default_chunk_overlap: s.kb_default_chunk_overlap,
    send_message_shortcut: s.send_message_shortcut, language: s.language || 'zh-CN',
    default_enable_suggest: s.default_enable_suggest ?? false, default_enable_ask_user: s.default_enable_ask_user ?? false,
    default_max_retries: s.default_max_retries ?? 1, default_timeout: s.default_timeout ?? 60,
  })
  nextTick(() => { isSyncingFromStore.value = false })
  if (s.language && (s.language === 'zh-CN' || s.language === 'en')) locale.value = s.language
}, { deep: true, immediate: true })

const performSave = async () => {
  saveStatus.value = 'saving'
  try {
    await settingsStore.saveGlobalSettings({ ...settingsForm, user_avatar_url: null, ai_avatar_url: null })
    saveStatus.value = 'saved'
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch { saveStatus.value = 'error' }
}
const debouncedSave = debounce(performSave, 1000)

watch(settingsForm, () => {
  if (isSyncingFromStore.value) return
  if (saveStatus.value !== 'saving') saveStatus.value = 'saving'
  debouncedSave()
}, { deep: true })

const handleUploadAvatar = async (type: AvatarType, file: File) => {
  isAvatarLoading[type] = true
  try { await settingsStore.uploadAvatar(type, file); ElMessage.success(t('settings.global.avatarUploadSuccess')) }
  catch { /* ignore */ } finally { isAvatarLoading[type] = false }
}
const handleDeleteAvatar = async (type: AvatarType) => {
  isAvatarLoading[type] = true
  try { await settingsStore.deleteAvatar(type); ElMessage.success(t('settings.global.avatarDeleteSuccess')) }
  catch { /* ignore */ } finally { isAvatarLoading[type] = false }
}
const handleTestProxy = async () => {
  if (!settingsForm.proxy_url) { ElMessage.warning(t('settings.global.enterProxyUrl')); return }
  if (!proxyTestUrl.value) { ElMessage.warning(t('settings.global.enterTestUrl')); return }
  isTestingProxy.value = true
  try {
    const r = await settingsStore.testProxy({ proxy_url: settingsForm.proxy_url, test_url: proxyTestUrl.value })
    ElMessage({ type: r.status === 'success' ? 'success' : 'error', message: r.message })
  } catch { /* ignore */ } finally { isTestingProxy.value = false }
}
</script>

<style scoped>
.mobile-global-settings { height: 100%; display: flex; flex-direction: column; background: var(--color-background); }

.settings-body { flex: 1; overflow-y: auto; padding: 12px 16px; -webkit-overflow-scrolling: touch; }
.body-spacer { height: 20px; }

/* ===== Section Card ===== */
.section-card {
  background: var(--color-background-soft); border-radius: 14px; padding: 16px;
  margin-bottom: 14px; border: 0.5px solid rgba(0,0,0,0.06); box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}
.section-title {
  font-size: 13px; font-weight: 700; color: var(--el-text-color-primary);
  margin-bottom: 12px; padding-bottom: 8px; border-bottom: 0.5px solid rgba(0,0,0,0.06);
  display: flex; align-items: center; gap: 6px;
}
.section-title::before { content: ''; display: inline-block; width: 3px; height: 14px; background: var(--el-color-primary); border-radius: 2px; flex-shrink: 0; }

.field-item { margin-bottom: 12px; }
.field-item:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.field-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.field-row + .field-row { border-top: 0.5px solid rgba(0,0,0,0.05); }

.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.native-textarea { width: 100%; padding: 10px 12px; font-size: 14px; font-family: inherit; line-height: 1.5; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; resize: vertical; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }

.avatar-row { display: flex; justify-content: flex-start; gap: 20px; }
.proxy-row { display: flex; gap: 8px; align-items: center; }
.proxy-test-btn { height: 40px; padding: 0 14px; font-size: 13px; font-weight: 500; color: #fff; background: var(--el-color-primary); border: none; border-radius: 10px; cursor: pointer; white-space: nowrap; }
.proxy-test-btn:disabled { opacity: 0.5; }
.proxy-test-btn:active { opacity: 0.8; }

/* ===== Save Bar ===== */
.save-bar {
  flex-shrink: 0; padding: 8px 16px; padding-bottom: max(8px, env(safe-area-inset-bottom));
  background: rgba(255,255,255,0.88); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-top: 0.5px solid rgba(0,0,0,0.08); text-align: center;
}
.status-item { display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; }
.status-item.saving { color: var(--el-text-color-secondary); }
.status-item.saved { color: var(--el-color-success); }
.status-item.error { color: var(--el-color-danger); }
.status-item.idle { color: var(--el-text-color-placeholder); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (prefers-color-scheme: dark) {
  .section-card { border-color: rgba(255,255,255,0.06); box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
  .section-title, .field-row+.field-row { border-color: rgba(255,255,255,0.06); }
  .save-bar { background: rgba(30,30,30,0.88); border-top-color: rgba(255,255,255,0.08); }
  .native-input, .native-textarea { box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset; }
  .native-input:focus, .native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
}
</style>
