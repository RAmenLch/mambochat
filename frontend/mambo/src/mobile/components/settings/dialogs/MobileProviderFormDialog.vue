<!-- frontend/mambo/src/mobile/components/settings/dialogs/MobileProviderFormDialog.vue -->
<template>
  <el-drawer
    v-model="internalVisible"
    :title="isEditing ? t('provider.form.editTitle') : t('provider.form.addTitle')"
    direction="rtl"
    size="85%"
    :close-on-click-modal="false"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="mobile-form">
      <el-form-item :label="t('provider.form.name')" prop="name">
        <!-- 修复 1: 使用 el-autocomplete 提供推荐服务商 -->
        <el-autocomplete
          v-model="form.name"
          :fetch-suggestions="querySearchProviders"
          :placeholder="t('provider.form.namePlaceholder')"
          style="width: 100%"
          @select="handleProviderSelect"
          :trigger-on-focus="true"
        />
      </el-form-item>

      <el-form-item :label="t('provider.form.workerType')" prop="worker_type">
        <el-select v-model="form.worker_type" style="width: 100%">
          <el-option label="OpenAI Compatible" value="openai" />
          <el-option label="Google Gemini" value="google" />
          <el-option label="DeepSeek" value="deepseek" />
          <el-option label="Anthropic" value="anthropic" />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('provider.form.apiHost')" prop="apiHost">
        <el-input v-model="form.apiHost" :placeholder="t('provider.form.apiHostPlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('provider.form.apiKey')" prop="apiKey">
        <el-input
          v-model="form.apiKey"
          type="password"
          show-password
          :placeholder="t('provider.form.apiKeyPlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('provider.form.enableProxy')">
        <div class="switch-row">
          <el-switch v-model="form.use_proxy" :disabled="!isProxyGloballyEnabled" />
          <span class="switch-label" v-if="!isProxyGloballyEnabled">
            <el-icon><Warning /></el-icon> {{ t('provider.form.proxyTip') }}
          </span>
        </div>
      </el-form-item>

      <el-button
        type="primary"
        :loading="isTesting"
        @click="handleTestConnection"
        style="width: 100%; margin-bottom: 20px;"
        plain
      >
        {{ t('provider.form.testConnection') }}
      </el-button>
    </el-form>

    <template #footer>
      <el-button @click="internalVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitForm" :loading="isSubmitting">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Warning } from '@element-plus/icons-vue';
import { useProviderStore } from '@/stores/providerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSystemConfigStore } from '@/stores/systemConfigStore'; // 引入 SystemConfigStore
import { storeToRefs } from 'pinia';
import type { AIProviderWithModels, AIProviderUpdate, ProviderWorkerType, ProviderWithModelsCreate } from '@/api/types';
import { isAxiosError } from 'axios'; // 引入错误类型判断

// 定义常量
const API_KEY_PLACEHOLDER = '********';

// Autocomplete 建议项类型
interface AutocompleteSuggestion {
  value: string;
}

const props = defineProps<{
  visible: boolean;
  providerData: AIProviderWithModels | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'submitted'): void;
}>();

const { t } = useI18n();
const providerStore = useProviderStore();
const settingsStore = useSettingsStore();
const systemConfigStore = useSystemConfigStore(); // 初始化 Store
const { globalSettings } = storeToRefs(settingsStore);

const formRef = ref<FormInstance>();
const isSubmitting = ref(false);
const isTesting = ref(false);

// 修复核心：使用计算属性代理 v-model
const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const isEditing = computed(() => !!props.providerData);
const isProxyGloballyEnabled = computed(() => globalSettings.value.proxy_enabled === true);

const form = reactive({
  name: '',
  apiHost: '',
  apiKey: '',
  worker_type: 'openai' as ProviderWorkerType,
  use_proxy: false
});

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('provider.form.namePlaceholder'), trigger: 'blur' }],
  apiHost: [{ required: true, message: t('provider.form.apiHostPlaceholder'), trigger: 'blur' }],
  apiKey: [{
    // 编辑模式下，如果值为占位符，视为有效（未修改密码）
    validator: (rule: any, value: string, callback: any) => {
      if (!isEditing.value && !value) {
        callback(new Error(t('provider.form.apiKeyPlaceholder')));
      } else if (isEditing.value && value === API_KEY_PLACEHOLDER) {
        callback();
      } else if (!value) {
         callback(new Error(t('provider.form.apiKeyPlaceholder')));
      } else {
        callback();
      }
    },
    trigger: 'blur',
  }]
}));

watch(() => props.visible, (val) => {
  if (val) {
    if (props.providerData) {
      // 编辑模式
      form.name = props.providerData.name;
      form.apiHost = props.providerData.apiHost;
      form.apiKey = API_KEY_PLACEHOLDER; // 使用常量
      form.worker_type = props.providerData.worker_type;
      form.use_proxy = props.providerData.use_proxy;
    } else {
      // 新增模式
      formRef.value?.resetFields();
      Object.assign(form, {
        name: '',
        apiHost: '',
        apiKey: '',
        worker_type: 'openai',
        use_proxy: false
      });
    }
  }
});

// 修复 1: 实现服务商推荐逻辑
const querySearchProviders = (queryString: string, cb: (results: AutocompleteSuggestion[]) => void) => {
  const allProviders = systemConfigStore.defaultProviders;
  const results = queryString
    ? allProviders.filter(p =>
        p.name.toLowerCase().includes(queryString.toLowerCase())
      )
    : allProviders;
  cb(results.map(p => ({ value: p.name })));
};

// --- 修复开始 ---
// 修改参数类型为 Record<string, any> 以匹配 Element Plus 的类型定义
const handleProviderSelect = (item: Record<string, any>) => {
  // 此时 item.value 是安全的，因为我们在 querySearchProviders 中保证了结构
  const selectedProvider = systemConfigStore.defaultProviders.find(p => p.name === item.value);
  if (selectedProvider) {
    form.apiHost = selectedProvider.apiHost;
    form.worker_type = selectedProvider.worker_type;
  }
};
// --- 修复结束 ---

// 修复 2: 完善测试连接逻辑，解决 401 问题
const handleTestConnection = async () => {
  if (!form.apiHost) {
    ElMessage.warning(t('provider.form.testWarningHost'));
    return;
  }

  isTesting.value = true;
  try {
    let res;
    // 如果是编辑模式且 API Key 未修改（显示为占位符），则使用 Provider ID 进行测试
    if (isEditing.value && form.apiKey === API_KEY_PLACEHOLDER && props.providerData) {
      res = await providerStore.testConnectionForProvider(props.providerData.id, form.apiHost, form.use_proxy);
    } else {
      // 否则使用输入的 API Key 进行测试
      if (!form.apiKey) {
        ElMessage.warning(t('provider.form.testWarningKey'));
        isTesting.value = false;
        return;
      }
      res = await providerStore.testConnection({ apiHost: form.apiHost, apiKey: form.apiKey }, form.use_proxy);
    }

    const msg = res.status === 'success' ? t('provider.form.testSuccess') : (res.message || t('provider.form.testFailed'));
    ElMessage({ type: res.status === 'success' ? 'success' : 'error', message: msg });
  } catch (error: unknown) {
    // 增强错误处理
    if (isAxiosError(error)) {
      ElMessage.error(error?.response?.data?.detail || t('provider.form.testFailed'));
    } else {
      ElMessage.error(t('provider.form.testFailed'));
    }
  } finally {
    isTesting.value = false;
  }
};

const submitForm = async () => {
  await formRef.value?.validate(async (valid) => {
    if (valid) {
      isSubmitting.value = true;
      try {
        if (isEditing.value && props.providerData) {
          // 更新
          const updateData: AIProviderUpdate = {
            name: form.name,
            apiHost: form.apiHost,
            worker_type: form.worker_type,
            use_proxy: form.use_proxy
          };
          // 只有当 API Key 不是占位符时才更新 Key
          if (form.apiKey !== API_KEY_PLACEHOLDER) {
            updateData.apiKey = form.apiKey;
          }
          await providerStore.updateProvider(props.providerData.id, updateData);
          ElMessage.success(t('provider.form.updateSuccess'));
        } else {
          // 新增
          const createData: ProviderWithModelsCreate = {
            name: form.name,
            apiHost: form.apiHost,
            apiKey: form.apiKey,
            worker_type: form.worker_type,
            use_proxy: form.use_proxy,
            models: []
          };
          await providerStore.addProviderWithModels(createData);
          ElMessage.success(t('provider.form.createSuccess'));
        }
        emit('submitted');
        internalVisible.value = false;
      } catch (e) {
        ElMessage.error(t('common.error.operationFailed'));
      } finally {
        isSubmitting.value = false;
      }
    }
  });
};
</script>

<style scoped>
.mobile-form {
  padding: 0 10px;
}
.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.switch-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
