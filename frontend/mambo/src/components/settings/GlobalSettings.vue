<template>
  <div class="global-settings-manager">
    <div class="header">
      <h2>全局配置</h2>
    </div>
    <div class="settings-form-container">
      <el-form :model="settingsForm" label-position="top" style="max-width: 600px;">
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
            <el-option-group
              v-for="group in groupedModels"
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
            <el-option-group
              v-for="group in groupedModels"
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

        <el-divider>头像设置</el-divider>
        <div class="avatar-settings-section">
          <AvatarUploader
            title="用户头像"
            :avatar-url="globalSettings.user_avatar_url"
            :icon="User"
            :is-loading="isAvatarLoading.user"
            @upload="file => handleUploadAvatar('user', file)"
            @delete="() => handleDeleteAvatar('user')"
          />
          <AvatarUploader
            title="AI 助手头像"
            :avatar-url="globalSettings.ai_avatar_url"
            :icon="Cpu"
            :is-loading="isAvatarLoading.ai"
            @upload="file => handleUploadAvatar('ai', file)"
            @delete="() => handleDeleteAvatar('ai')"
          />
        </div>

        <el-divider>代理配置</el-divider>
        <el-form-item label="启用代理">
           <el-switch
             :model-value="settingsForm.proxy_enabled ?? false"
             @update:model-value="val => settingsForm.proxy_enabled = val as boolean"
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
            style="width: 100%;"
          />
        </el-form-item>

        <el-form-item label="Temperature (温度)">
          <el-slider
            :model-value="settingsForm.default_temperature ?? 1.0"
            @update:model-value="val => settingsForm.default_temperature = val as number"
            :min="0"
            :max="2"
            :step="0.1"
            show-input
          />
        </el-form-item>

        <el-form-item label="Top P">
          <el-slider
            :model-value="settingsForm.default_top_p ?? 1.0"
            @update:model-value="val => settingsForm.default_top_p = val as number"
            :min="0"
            :max="1"
            :step="0.01"
            show-input
          />
        </el-form-item>

        <el-form-item label="流式对话 (Stream)">
           <el-switch
             :model-value="settingsForm.default_stream ?? true"
             @update:model-value="val => settingsForm.default_stream = val as boolean"
           />
           <el-tooltip
              effect="dark"
              content="新会话默认是否开启流式对话。关闭后, AI将一次性返回完整回复, 可能会增加等待时间。"
              placement="top"
            >
              <el-icon class="label-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
        </el-form-item>


        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="isSaving">
            保存设置
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { QuestionFilled, User, Cpu } from '@element-plus/icons-vue';
import type { GlobalSettingsUpdate } from '@/api/types';
import AvatarUploader from './AvatarUploader.vue';

type AvatarType = 'user' | 'ai';

const providerStore = useProviderStore();
const settingsStore = useSettingsStore();

const { groupedModels } = storeToRefs(providerStore);
const { globalSettings } = storeToRefs(settingsStore);

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
});

const isSaving = ref(false);
const isTestingProxy = ref(false);
const proxyTestUrl = ref('https://www.google.com');
const isAvatarLoading = reactive({
  user: false,
  ai: false,
});

onMounted(async () => {
  await settingsStore.fetchGlobalSettings();
});

watch(globalSettings, (newSettings) => {
  // 只同步表单相关的设置, 头像URL由 AvatarUploader 组件直接消费
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
  });
}, { deep: true, immediate: true });

const handleUploadAvatar = async (type: AvatarType, file: File) => {
  isAvatarLoading[type] = true;
  try {
    await settingsStore.uploadAvatar(type, file);
    ElMessage.success('头像上传成功！');
  } catch (error: unknown) {
    // 错误消息已由全局拦截器处理
    console.error(`Failed to upload ${type} avatar:`, error);
  } finally {
    isAvatarLoading[type] = false;
  }
};

const handleDeleteAvatar = async (type: AvatarType) => {
  isAvatarLoading[type] = true;
  try {
    await settingsStore.deleteAvatar(type);
    ElMessage.success('头像已删除。');
  } catch (error: unknown)
  {
    console.error(`Failed to delete ${type} avatar:`, error);
  } finally {
    isAvatarLoading[type] = false;
  }
};

const handleSave = async () => {
  isSaving.value = true;
  try {
    const settingsToSave: GlobalSettingsUpdate = { ...settingsForm, user_avatar_url: null, ai_avatar_url: null };
    await settingsStore.saveGlobalSettings(settingsToSave);
    ElMessage.success('全局设置已保存！');
  } catch (error: unknown) {
    console.error('Failed to save global settings:', error);
  } finally {
    isSaving.value = false;
  }
};

const handleTestProxy = async () => {
  if (!settingsForm.proxy_url) {
    ElMessage.warning('请输入代理 URL');
    return;
  }
  if (!proxyTestUrl.value) {
    ElMessage.warning('请输入测试链接');
    return;
  }

  isTestingProxy.value = true;
  try {
    const response = await settingsStore.testProxy({
      proxy_url: settingsForm.proxy_url,
      test_url: proxyTestUrl.value,
    });
    ElMessage({
      type: response.status === 'success' ? 'success' : 'error',
      message: response.message,
    });
  } catch (error: unknown) {
     console.error('Failed to test proxy:', error);
  } finally {
    isTestingProxy.value = false;
  }
};
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
  margin-bottom: 22px; /* el-form-item default margin-bottom */
}
</style>
