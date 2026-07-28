<template>
  <el-dialog
    :model-value="visible"
    :title="isEditMode ? t('settings.mcp.editTitle') : t('settings.mcp.addTitle')"
    width="600px"
    @update:model-value="handleUpdateVisible"
    @closed="handleClosed"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item :label="t('settings.mcp.columns.name')" prop="name">
        <el-input v-model="formData.name" :placeholder="t('settings.mcp.form.namePlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.description')" prop="description">
        <el-input v-model="formData.description" type="textarea" :placeholder="t('settings.mcp.form.descPlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.type')" prop="transportType">
        <el-radio-group v-model="formData.transportType" @change="handleTransportChange">
          <el-radio-button value="stdio">Stdio</el-radio-button>
          <el-radio-button value="sse">SSE</el-radio-button>
          <el-radio-button value="streamable_http">Streamable HTTP</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.enableStatus')" prop="isEnabled">
        <el-switch v-model="formData.isEnabled" />
      </el-form-item>

      <!-- Stdio 专属字段 -->
      <template v-if="formData.transportType === 'stdio'">
        <el-divider content-position="left">Stdio</el-divider>
        <el-form-item :label="t('settings.mcp.form.commandLabel')" prop="command">
          <el-input v-model="formData.command" :placeholder="t('settings.mcp.form.commandPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.argsLabel')">
          <div class="dynamic-list">
            <div v-for="(arg, index) in formData.argsList" :key="index" class="dynamic-row">
              <el-input v-model="formData.argsList[index]" :placeholder="t('settings.mcp.form.argPlaceholder')" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeArg(index)" />
            </div>
            <el-button type="primary" link :icon="Plus" @click="addArg">+</el-button>
          </div>
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.envLabel')">
          <div class="dynamic-list">
            <div v-for="(env, index) in formData.envList" :key="index" class="dynamic-row">
              <el-input v-model="env.key" :placeholder="t('settings.mcp.form.envKeyPlaceholder')" style="flex: 1" />
              <span class="separator">=</span>
              <el-input v-model="env.value" :placeholder="t('settings.mcp.form.envValuePlaceholder')" style="flex: 1" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeEnv(index)" />
            </div>
            <el-button type="primary" link :icon="Plus" @click="addEnv">+</el-button>
          </div>
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.cwdLabel')">
          <el-input v-model="formData.cwd" :placeholder="t('settings.mcp.form.cwdPlaceholder')" />
        </el-form-item>
      </template>

      <!-- SSE / Streamable HTTP 专属字段 -->
      <template v-if="formData.transportType === 'sse' || formData.transportType === 'streamable_http'">
        <el-divider content-position="left">{{ formData.transportType === 'streamable_http' ? 'Streamable HTTP' : 'SSE' }}</el-divider>
        <el-form-item :label="t('settings.mcp.form.urlLabel')" prop="url">
          <el-input v-model="formData.url" :placeholder="t('settings.mcp.form.urlPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.headersLabel')">
          <div class="dynamic-list">
            <div v-for="(header, index) in formData.headersList" :key="index" class="dynamic-row">
              <el-input v-model="header.key" :placeholder="t('settings.mcp.form.headerKeyPlaceholder')" style="flex: 1" />
              <span class="separator">:</span>
              <el-input v-model="header.value" :placeholder="t('settings.mcp.form.headerValuePlaceholder')" style="flex: 1" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeHeader(index)" />
            </div>
            <el-button type="primary" link :icon="Plus" @click="addHeader">+</el-button>
          </div>
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.timeoutLabel')">
          <el-input-number v-model="formData.timeout" :min="0.1" :step="1" :placeholder="t('settings.mcp.form.timeoutPlaceholder')" style="width: 100%" />
        </el-form-item>

        <el-form-item :label="t('settings.mcp.form.sseReadTimeoutLabel')">
          <el-input-number v-model="formData.sse_read_timeout" :min="0.1" :step="1" :placeholder="t('settings.mcp.form.sseReadTimeoutPlaceholder')" style="width: 100%" />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <div class="dialog-footer-wrapper">
        <div class="footer-left">
            <el-button
              :loading="isTestingConnection"
              :icon="Connection"
              @click="handleTestConnection"
            >
              {{ t('settings.mcp.testConnection') }}
            </el-button>
            <div v-if="testFeedback.status !== 'none'" class="test-feedback" :class="testFeedback.status">
              <el-icon v-if="testFeedback.status === 'success'"><CircleCheck /></el-icon>
              <el-icon v-else><CircleClose /></el-icon>
              <span :title="testFeedback.message">{{ testFeedback.shortMessage }}</span>
            </div>
        </div>
        <div class="footer-right">
          <el-button @click="handleCancel">{{ t('common.action.cancel') }}</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="isSubmitting">
            {{ t('common.action.confirm') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { Plus, Minus, Connection, CircleCheck, CircleClose } from '@element-plus/icons-vue';
import type { FormInstance, FormRules } from 'element-plus';
import { useI18n } from 'vue-i18n';
import type { McpServer, McpCreateRequest, McpTransportType } from '@/api/types';
import { useMcpStore } from '@/stores/mcpStore';

const { t } = useI18n();

const props = defineProps<{
  visible: boolean;
  initialData?: McpServer | null;
  isSubmitting?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'save', data: McpCreateRequest): void;
}>();

const mcpStore = useMcpStore();
const formRef = ref<FormInstance>();

// 测试连接状态
const isTestingConnection = ref(false);
const testFeedback = reactive({
  status: 'none' as 'none' | 'success' | 'error',
  shortMessage: '',
  message: ''
});

// 内部表单数据结构
interface LocalFormData {
  name: string;
  description: string;
  transportType: McpTransportType;
  isEnabled: boolean;
  command: string;
  argsList: string[];
  envList: { key: string; value: string }[];
  cwd: string;
  url: string;
  headersList: { key: string; value: string }[];
  timeout: number | null;
  sse_read_timeout: number | null;
}

const defaultFormData: LocalFormData = {
  name: '',
  description: '',
  transportType: 'stdio',
  isEnabled: true,
  command: '',
  argsList: [],
  envList: [],
  cwd: '',
  url: '',
  headersList: [],
  timeout: null,
  sse_read_timeout: null,
};

const formData = reactive<LocalFormData>({ ...defaultFormData });

const isEditMode = computed(() => !!props.initialData);

const rules = computed<FormRules>(() => {
  const commonRules = {
    name: [
      { required: true, message: () => t('settings.mcp.form.nameRequired'), trigger: 'blur' },
      { max: 64, message: () => t('settings.mcp.form.nameMaxLength'), trigger: 'blur' },
      { pattern: /^[a-zA-Z][a-zA-Z0-9_-]*$/, message: () => t('settings.mcp.form.namePattern'), trigger: 'blur' },
      {
        validator: (_rule: any, value: any, callback: any) => {
          if (value && value.includes('__')) {
            callback(new Error(t('settings.mcp.form.nameNoDoubleUnderscore')));
          } else {
            callback();
          }
        },
        trigger: 'blur',
      },
    ],
  };

  if (formData.transportType === 'stdio') {
    return {
      ...commonRules,
      command: [{ required: true, message: () => t('settings.mcp.form.commandRequired'), trigger: 'blur' }],
    };
  } else {
    return {
      ...commonRules,
      url: [{ required: true, message: () => t('settings.mcp.form.urlRequired'), trigger: 'blur' }],
    };
  }
});

// 监听 visible 和 initialData 变化以初始化表单
watch(
  () => [props.visible, props.initialData],
  ([newVisible]) => {
    if (newVisible) {
      // 重置测试状态
      testFeedback.status = 'none';
      testFeedback.shortMessage = '';
      testFeedback.message = '';

      if (props.initialData) {
        // 编辑模式：回填数据
        const data = props.initialData as McpServer;
        formData.name = data.name;
        formData.description = data.description || '';
        formData.transportType = data.transportType;
        formData.isEnabled = data.isEnabled;
        formData.command = data.command || '';
        formData.url = data.url || '';
        formData.cwd = data.cwd || '';
        formData.timeout = data.timeout ?? null;
        formData.sse_read_timeout = data.sse_read_timeout ?? null;

        // 转换 args
        formData.argsList = data.args ? [...data.args] : [];

        // 转换 env
        formData.envList = data.env
          ? Object.entries(data.env).map(([key, value]) => ({ key, value }))
          : [];

        // 转换 headers
        formData.headersList = data.headers
          ? Object.entries(data.headers).map(([key, value]) => ({ key, value }))
          : [];
      } else {
        // 新增模式：重置
        Object.assign(formData, JSON.parse(JSON.stringify(defaultFormData)));
      }
    }
  }
);

const handleTransportChange = () => {
  // 切换类型时清除校验结果
  formRef.value?.clearValidate();
};

const addArg = () => {
  formData.argsList.push('');
};

const removeArg = (index: number) => {
  formData.argsList.splice(index, 1);
};

const addEnv = () => {
  formData.envList.push({ key: '', value: '' });
};

const removeEnv = (index: number) => {
  formData.envList.splice(index, 1);
};

const addHeader = () => {
  formData.headersList.push({ key: '', value: '' });
};

const removeHeader = (index: number) => {
  formData.headersList.splice(index, 1);
};

const handleUpdateVisible = (val: boolean) => {
  emit('update:visible', val);
};

const handleCancel = () => {
  emit('update:visible', false);
};

const handleClosed = () => {
  formRef.value?.resetFields();
};

const handleSubmit = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      // 构造提交数据
      const requestData: McpCreateRequest = {
        name: formData.name,
        description: formData.description || null,
        transportType: formData.transportType,
        isEnabled: formData.isEnabled,
      };

      if (formData.transportType === 'stdio') {
        requestData.command = formData.command;
        // 过滤空参数
        const validArgs = formData.argsList.filter(a => a.trim() !== '');
        requestData.args = validArgs.length > 0 ? validArgs : null;

        // 转换 env 数组为对象
        const validEnv = formData.envList.filter(e => e.key.trim() !== '');
        if (validEnv.length > 0) {
          requestData.env = validEnv.reduce((acc, cur) => {
            acc[cur.key] = cur.value;
            return acc;
          }, {} as Record<string, string>);
        } else {
          requestData.env = null;
        }

        requestData.cwd = formData.cwd || null;
      } else {
        requestData.url = formData.url;

        // 转换 headers 数组为对象
        const validHeaders = formData.headersList.filter(h => h.key.trim() !== '');
        if (validHeaders.length > 0) {
          requestData.headers = validHeaders.reduce((acc, cur) => {
            acc[cur.key] = cur.value;
            return acc;
          }, {} as Record<string, string>);
        } else {
          requestData.headers = null;
        }

        requestData.timeout = formData.timeout ?? null;
        requestData.sse_read_timeout = formData.sse_read_timeout ?? null;
      }

      emit('save', requestData);
    }
  });
};

const handleTestConnection = async () => {
  isTestingConnection.value = true;
  testFeedback.status = 'none';

  try {
    // 构造当前表单的配置数据用于测试
    const configData: McpCreateRequest = {
      name: formData.name,
      description: formData.description || null,
      transportType: formData.transportType,
      isEnabled: formData.isEnabled,
    };

    if (formData.transportType === 'stdio') {
      configData.command = formData.command;
      const validArgs = formData.argsList.filter(a => a.trim() !== '');
      configData.args = validArgs.length > 0 ? validArgs : null;
      const validEnv = formData.envList.filter(e => e.key.trim() !== '');
      if (validEnv.length > 0) {
        configData.env = validEnv.reduce((acc, cur) => {
          acc[cur.key] = cur.value;
          return acc;
        }, {} as Record<string, string>);
      } else {
        configData.env = null;
      }
      configData.cwd = formData.cwd || null;
    } else {
      configData.url = formData.url;
      const validHeaders = formData.headersList.filter(h => h.key.trim() !== '');
      if (validHeaders.length > 0) {
        configData.headers = validHeaders.reduce((acc, cur) => {
          acc[cur.key] = cur.value;
          return acc;
        }, {} as Record<string, string>);
      } else {
        configData.headers = null;
      }
      configData.timeout = formData.timeout ?? null;
      configData.sse_read_timeout = formData.sse_read_timeout ?? null;
    }

    const response = await mcpStore.testConnectionWithConfig(configData);

    if (response.status === 'healthy') {
      testFeedback.status = 'success';
      testFeedback.shortMessage = t('settings.mcp.connectSuccess', { count: response.tools_count });
      testFeedback.message = t('settings.mcp.connectSuccessDetail');
    } else {
      testFeedback.status = 'error';
      testFeedback.shortMessage = t('settings.mcp.connectFailed');
      testFeedback.message = response.error || response.message || t('settings.mcp.connectFailedDetail');
    }
  } catch (error: any) {
    testFeedback.status = 'error';
    testFeedback.shortMessage = t('settings.mcp.connectFailed');
    testFeedback.message = error.message || t('settings.mcp.connectFailedDetail');
  } finally {
    isTestingConnection.value = false;
  }
};
</script>

<style scoped>
.dynamic-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.dynamic-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.separator {
  font-weight: bold;
  color: var(--el-text-color-secondary);
}

.dialog-footer-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.test-feedback {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.test-feedback.success {
  color: var(--el-color-success);
}

.test-feedback.error {
  color: var(--el-color-danger);
}
</style>
