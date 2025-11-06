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


        <el-divider>新会话默认参数</el-divider>

        <el-form-item>
          <template #label>
            <span>上下文消息数量 (Context)</span>
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
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import type { GlobalSettingsUpdate } from '@/api/types';
import { isAxiosError } from 'axios';

const providerStore = useProviderStore();
const { globalSettings, groupedModels } = storeToRefs(providerStore);

const settingsForm = reactive<GlobalSettingsUpdate>({
  default_model_id: null,
  title_generation_model_id: null, // 新增：专门用于生成标题的模型ID
  last_selected_provider_id: null,
  default_max_context_messages: 0,
  default_temperature: 1.0,
  default_top_p: 1.0,
  default_stream: true,
  proxy_enabled: false,
  proxy_url: null,
});

const isSaving = ref(false);
const isTestingProxy = ref(false);
const proxyTestUrl = ref('https://www.google.com');

onMounted(async () => {
  await providerStore.fetchGlobalSettings();
});

watch(globalSettings, (newSettings) => {
  Object.assign(settingsForm, newSettings);
}, { deep: true, immediate: true });

const handleSave = async () => {
  isSaving.value = true;
  try {
    await providerStore.saveGlobalSettings(settingsForm);
    ElMessage.success('全局设置已保存！');
  } catch (error: unknown) {
    let message = '保存失败，请稍后重试。';
    if (isAxiosError(error) && error.response?.data?.detail) {
      message = error.response.data.detail;
    }
    ElMessage.error(message);
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
    const response = await providerStore.testProxy({
      proxy_url: settingsForm.proxy_url,
      test_url: proxyTestUrl.value,
    });
    ElMessage({
      type: response.status === 'success' ? 'success' : 'error',
      message: response.message,
    });
  } catch (error: unknown) {
     let message = '测试请求失败';
     if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail;
     }
     ElMessage.error(message);
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
</style>
