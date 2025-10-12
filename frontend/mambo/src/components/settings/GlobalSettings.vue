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
});
const isSaving = ref(false);

onMounted(async () => {
  // 页面加载时获取最新设置
  await providerStore.fetchGlobalSettings();
});

// 当 store 中的数据加载或更新后，同步到本地表单
watch(globalSettings, (newSettings) => {
  settingsForm.default_model_id = newSettings.default_model_id;
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
</style>
