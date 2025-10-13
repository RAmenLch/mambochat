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
            v-model="settingsForm.default_temperature"
            :min="0"
            :max="2"
            :step="0.1"
            show-input
          />
        </el-form-item>

        <el-form-item label="Top P">
          <el-slider
            v-model="settingsForm.default_top_p"
            :min="0"
            :max="1"
            :step="0.01"
            show-input
          />
        </el-form-item>

        <el-form-item label="流式对话 (Stream)">
           <el-switch v-model="settingsForm.default_stream" />
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

const providerStore = useProviderStore();
const { globalSettings, groupedModels } = storeToRefs(providerStore);

const settingsForm = reactive<GlobalSettingsUpdate>({
  default_model_id: null,
  last_selected_provider_id: null,
  default_max_context_messages: 0,
  default_temperature: 1.0,
  default_top_p: 1.0,
  default_stream: true,
});
const isSaving = ref(false);

onMounted(async () => {
  // 页面加载时获取最新设置
  await providerStore.fetchGlobalSettings();
});

// 当 store 中的数据加载或更新后，同步到本地表单
watch(globalSettings, (newSettings) => {
  // 使用 Object.assign 确保响应性
  Object.assign(settingsForm, newSettings);
}, { deep: true, immediate: true });

const handleSave = async () => {
  isSaving.value = true;
  try {
    await providerStore.saveGlobalSettings(settingsForm);
    ElMessage.success('全局设置已保存！');
  } catch (error: any) {
    const message = error?.response?.data?.detail || '保存失败，请稍后重试。';
    ElMessage.error(message);
  } finally {
    isSaving.value = false;
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
</style>
