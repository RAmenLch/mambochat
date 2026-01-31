<template>
  <div class="global-settings-manager">
    <div class="header">
      <h2>全局配置</h2>
      <!-- 顶部也可以显示保存状态，可选 -->
    </div>
    <div class="settings-form-container">
      <el-form :model="settingsForm" label-position="top" style="max-width: 600px">
        <el-form-item>
          <template #label>
            <span>全局默认模型</span>
            <el-tooltip
              effect="dark"
              content="此模型将用于新创建的会话，以及那些原有模型被删除的会话。"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select
            v-model="settingsForm.default_model_id"
            placeholder="请选择一个默认模型"
            style="width: 100%"
            clearable
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
            <span>生成标题模型</span>
            <el-tooltip
              effect="dark"
              content="专门用于自动生成会话标题的模型。如果未设置，将使用上方的全局默认模型。"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select
            v-model="settingsForm.title_generation_model_id"
            placeholder="请选择一个用于生成标题的模型"
            style="width: 100%"
            clearable
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

        <el-divider>编辑器与交互</el-divider>
        <el-form-item label="前端编辑器类型">
          <el-radio-group v-model="settingsForm.frontend_editor">
            <el-radio-button label="simple">普通文本框</el-radio-button>
            <el-radio-button label="monaco">Monaco 编辑器 (代码高亮)</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="发送消息快捷键">
          <el-select v-model="settingsForm.send_message_shortcut" style="width: 100%">
            <el-option label="Enter 发送 (Shift+Enter 换行)" value="enter" />
            <el-option label="Ctrl + Enter 发送 (Enter 换行)" value="ctrl_enter" />
          </el-select>
        </el-form-item>

        <el-divider>知识库默认参数</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item>
              <template #label>
                <span>默认切片大小</span>
                <el-tooltip content="新上传文件的默认切片字符数" placement="top">
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
                <span>默认重叠大小</span>
                <el-tooltip content="新上传文件的默认切片重叠字符数" placement="top">
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

        <el-divider>头像设置</el-divider>
        <div class="avatar-settings-section">
          <AvatarUploader
            title="用户头像"
            :avatar-url="globalSettings.user_avatar_url"
            :icon="User"
            :is-loading="isAvatarLoading.user"
            @upload="(file) => handleUploadAvatar('user', file)"
            @delete="() => handleDeleteAvatar('user')"
          />
          <AvatarUploader
            title="AI 助手头像"
            :avatar-url="globalSettings.ai_avatar_url"
            :icon="Cpu"
            :is-loading="isAvatarLoading.ai"
            @upload="(file) => handleUploadAvatar('ai', file)"
            @delete="() => handleDeleteAvatar('ai')"
          />
        </div>

        <el-divider>代理配置</el-divider>
        <el-form-item label="启用代理">
          <el-switch
            :model-value="settingsForm.proxy_enabled ?? false"
            @update:model-value="(val) => (settingsForm.proxy_enabled = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            content="全局启用代理后，可在各个服务商设置中独立开关"
            placement="top"
          >
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="代理 URL" v-if="settingsForm.proxy_enabled">
          <el-input
            v-model.trim="settingsForm.proxy_url"
            placeholder="例如: http://127.0.0.1:7890"
          />
        </el-form-item>
        <el-form-item label="代理测试" v-if="settingsForm.proxy_enabled">
          <div class="proxy-test-container">
            <el-input
              v-model.trim="proxyTestUrl"
              placeholder="测试链接, 如 https://www.google.com"
              class="proxy-test-input"
            />
            <el-button @click="handleTestProxy" :loading="isTestingProxy">测试代理</el-button>
          </div>
        </el-form-item>

        <el-divider>对话历史压缩</el-divider>
        <el-form-item>
          <template #label>
            <span>生成压缩历史 System Prompt</span>
            <el-tooltip
              effect="dark"
              content="用于指导 AI 如何进行对话历史压缩的系统指令。如果为空，将使用后端默认的 Prompt。"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="settingsForm.zip_history_system_prompt"
            type="textarea"
            :rows="5"
            placeholder="例如：请将以上对话内容浓缩为一段简洁的摘要，保留关键信息、问题和结论。"
          />
        </el-form-item>

        <el-divider>新会话默认参数</el-divider>

        <el-form-item>
          <template #label>
            <span>上下文消息数量</span>
            <el-tooltip
              effect="dark"
              content="新会话默认携带的最近历史消息数量。0 代表不限制（发送全部历史）。"
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

        <el-form-item label="Temperature (温度)">
          <el-slider
            :model-value="settingsForm.default_temperature ?? 1.0"
            @update:model-value="(val) => (settingsForm.default_temperature = val as number)"
            :min="0"
            :max="2"
            :step="0.1"
            show-input
          />
        </el-form-item>

        <el-form-item label="Top P">
          <el-slider
            :model-value="settingsForm.default_top_p ?? 1.0"
            @update:model-value="(val) => (settingsForm.default_top_p = val as number)"
            :min="0"
            :max="1"
            :step="0.01"
            show-input
          />
        </el-form-item>

        <el-form-item label="流式对话 (Stream)">
          <el-switch
            :model-value="settingsForm.default_stream ?? true"
            @update:model-value="(val) => (settingsForm.default_stream = val as boolean)"
          />
          <el-tooltip
            effect="dark"
            content="新会话默认是否开启流式对话。关闭后, AI将一次性返回完整回复, 可能会增加等待时间。"
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
              <span>正在保存设置...</span>
            </div>
            <div v-else-if="saveStatus === 'saved'" class="status-item saved">
              <el-icon><Check /></el-icon>
              <span>所有更改已保存</span>
            </div>
            <div v-else-if="saveStatus === 'error'" class="status-item error">
              <el-icon><Warning /></el-icon>
              <span>保存失败，请检查网络</span>
            </div>
          </transition>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, nextTick } from 'vue'
import { useProviderStore } from '@/stores/providerStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { QuestionFilled, User, Cpu, Loading, Check, Warning } from '@element-plus/icons-vue'
import type { GlobalSettingsUpdate } from '@/api/types'
import AvatarUploader from './AvatarUploader.vue'

type AvatarType = 'user' | 'ai'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const providerStore = useProviderStore()
const settingsStore = useSettingsStore()

const { groupedModels } = storeToRefs(providerStore)
const { globalSettings } = storeToRefs(settingsStore)

// 表单数据
const settingsForm = reactive<Omit<GlobalSettingsUpdate, 'user_avatar_url' | 'ai_avatar_url'>>({
  default_model_id: null,
  title_generation_model_id: null,
  last_selected_provider_id: null,
  default_max_context_messages: 0,
  default_temperature: 1.0,
  default_top_p: 1.0,
  default_stream: true,
  proxy_enabled: false,
  proxy_url: null,
  zip_history_system_prompt: null,
  frontend_editor: 'simple',
  kb_default_chunk_size: 500,
  kb_default_chunk_overlap: 50,
  send_message_shortcut: 'enter',
})

// 状态控制
const saveStatus = ref<SaveStatus>('idle')
const isTestingProxy = ref(false)
const proxyTestUrl = ref('https://www.google.com')
const isAvatarLoading = reactive({
  user: false,
  ai: false,
})

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
      zip_history_system_prompt: newSettings.zip_history_system_prompt,
      frontend_editor: newSettings.frontend_editor,
      kb_default_chunk_size: newSettings.kb_default_chunk_size,
      kb_default_chunk_overlap: newSettings.kb_default_chunk_overlap,
      send_message_shortcut: newSettings.send_message_shortcut,
    })

    // 在 DOM 更新循环结束后释放锁，确保 watch(settingsForm) 不会被此次赋值触发
    nextTick(() => {
      isSyncingFromStore.value = false
    })
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
    ElMessage.success('头像上传成功！')
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
    ElMessage.success('头像已删除。')
  } catch (error: unknown) {
    console.error(`Failed to delete ${type} avatar:`, error)
  } finally {
    isAvatarLoading[type] = false
  }
}

const handleTestProxy = async () => {
  if (!settingsForm.proxy_url) {
    ElMessage.warning('请输入代理 URL')
    return
  }
  if (!proxyTestUrl.value) {
    ElMessage.warning('请输入测试链接')
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
